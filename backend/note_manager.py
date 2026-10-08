"""
笔记快照管理器。

PRD 9.8 的定位：**快照是权威版本，SQLite 只是索引**。
所以每次笔记增删改之后，都要把该文献的笔记整体重写到
`data/note_snapshots/lit_XXX.json`，并刷新 `data/notes_index.json`。

这样做的好处：
  1. 笔记是纯 JSON，可直接 git 版本管理 / 手动编辑 / 迁移
  2. 桥接服务（bridge_server.py）读快照即可，不必碰 SQLite
  3. 数据库被误删时，笔记仍可从快照恢复

不做字符级定位，只到段落级（PRD 9.8「不做」）。
"""

import os
import json
import re
from datetime import datetime

from config.settings import BASE_DIR
from backend.database import get_notes_by_doc, get_all_notes

SNAPSHOT_DIR = os.path.join(BASE_DIR, 'data', 'note_snapshots')
INDEX_PATH = os.path.join(SNAPSHOT_DIR, 'notes_index.json')

# 快照 schema 版本：结构变更时 +1，便于将来做迁移
SNAPSHOT_VERSION = 1


def _ensure_dir():
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)


def snapshot_path(doc_id: str) -> str:
    return os.path.join(SNAPSHOT_DIR, f'{doc_id}.json')


def _split_sentences(text: str) -> list:
    """句子级切分。只用于快照的 sentences 字段（句子级划线的定位粒度）。"""
    if not text:
        return []
    parts = re.split(r'(?<=[。！？；…!?;])\s*', text.strip())
    return [p.strip() for p in parts if p.strip()]


def _note_to_snapshot_item(n: dict) -> dict:
    """
    一条笔记 → 快照条目。

    content 取「当前生效版本」，versions 保留完整版本链（导出带版本链时用）。
    已软删的笔记不进快照。
    """
    versions = n.get('versions') or []
    active = [v for v in versions if v.get('status') == 'active']
    current = (active[-1] if active else (versions[-1] if versions else {}))

    content = (current.get('c') or '').strip()
    return {
        'note_id': n.get('id'),
        'pid': n.get('pid'),
        'type': 'note',
        'quote': n.get('quote') or '',
        'content': content,
        'sentences': _split_sentences(content),
        'related_notes': [n['related']] if n.get('related') else [],
        'versions': [
            {'v': v.get('v'), 't': v.get('t'), 'c': v.get('c'), 'status': v.get('status')}
            for v in versions
        ],
        'status': n.get('status', 'active'),
        'created_at': n.get('created_at'),
        'updated_at': n.get('updated_at'),
    }


def write_snapshot(doc_id: str) -> dict:
    """把某篇文献的笔记整体重写为快照文件。返回快照内容。"""
    _ensure_dir()
    notes = get_notes_by_doc(doc_id)
    items = [_note_to_snapshot_item(n) for n in notes]

    snap = {
        'schema_version': SNAPSHOT_VERSION,
        'doc_id': doc_id,
        'updated_at': datetime.now().isoformat(timespec='seconds'),
        'count': len(items),
        'notes': items,
    }

    path = snapshot_path(doc_id)
    tmp = path + '.tmp'
    # 先写临时文件再原子替换：写一半崩了不会留下坏快照
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(snap, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    return snap


def rebuild_index() -> dict:
    """重建全库索引：每篇文献有多少笔记、什么时候更新的。"""
    _ensure_dir()
    all_notes = get_all_notes()

    by_doc = {}
    for n in all_notes:
        by_doc.setdefault(n.get('doc'), []).append(n)

    docs = {}
    for doc_id, notes in by_doc.items():
        versions = sum(len(n.get('versions') or []) for n in notes)
        docs[doc_id] = {
            'doc_id': doc_id,
            'note_count': len(notes),
            'version_count': versions,
            'snapshot': f'data/note_snapshots/{doc_id}.json',
            'updated_at': max((n.get('updated_at') or '') for n in notes),
        }

    index = {
        'schema_version': SNAPSHOT_VERSION,
        'updated_at': datetime.now().isoformat(timespec='seconds'),
        'doc_count': len(docs),
        'note_count': len(all_notes),
        'docs': docs,
    }

    tmp = INDEX_PATH + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    os.replace(tmp, INDEX_PATH)
    return index


def sync(doc_id: str) -> dict:
    """笔记变更后调用：写该篇快照 + 刷新索引。"""
    snap = write_snapshot(doc_id)
    rebuild_index()
    return snap


def sync_all() -> dict:
    """全量重建（初始化 / 数据修复时用）。"""
    _ensure_dir()
    for n in get_all_notes():
        write_snapshot(n.get('doc'))
    return rebuild_index()


def read_snapshot(doc_id: str) -> dict | None:
    path = snapshot_path(doc_id)
    if not os.path.exists(path):
        return None
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def export_markdown(doc_id: str = None) -> str:
    """导出 Markdown（带版本链）。PRD 9.8 的 P1 能力。"""
    if doc_id:
        snaps = [read_snapshot(doc_id)]
    else:
        _ensure_dir()
        snaps = []
        for fn in sorted(os.listdir(SNAPSHOT_DIR)):
            if fn.endswith('.json') and fn != 'notes_index.json':
                with open(os.path.join(SNAPSHOT_DIR, fn), encoding='utf-8') as f:
                    snaps.append(json.load(f))

    out = ['# 笔记导出', '']
    for s in snaps:
        if not s:
            continue
        out.append(f"## {s.get('doc_id')}")
        out.append('')
        for n in s.get('notes', []):
            loc = f"¶{n.get('pid')}"
            out.append(f"### {n.get('note_id')} · {loc}")
            if n.get('quote'):
                out.append(f"> {n['quote']}")
            out.append('')
            out.append(n.get('content') or '（空）')
            if len(n.get('versions', [])) > 1:
                out.append('')
                out.append('<details><summary>版本链</summary>')
                out.append('')
                for v in n['versions']:
                    flag = '' if v.get('status') == 'active' else '（已删除）'
                    out.append(f"- **{v.get('v')}** · {v.get('t')}{flag}")
                    out.append(f"  {v.get('c')}")
                out.append('')
                out.append('</details>')
            out.append('')
    return '\n'.join(out)


if __name__ == '__main__':
    import sys
    if '--export' in sys.argv:
        doc = None
        for a in sys.argv:
            if a.startswith('--doc='):
                doc = a.split('=', 1)[1]
        print(export_markdown(doc))
    else:
        idx = sync_all()
        print(f"✅ 快照已重建：{idx['doc_count']} 篇 / {idx['note_count']} 条笔记")
        print(f"   目录：{SNAPSHOT_DIR}")
