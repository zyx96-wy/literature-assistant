# -*- coding: utf-8 -*-
"""
重建工具：用新 prompt 重跑深解析 + 重灌检索块
==============================================

用途：
  - 换了 deep_parse 的 prompt（比如要求字段写得更详细）后，重跑已有文献的 fields
  - 换了 pdf_parser 后，重灌 Chroma 检索块（阅读段落也一并重建）
  - 删冗余文献（同时清 SQLite + Chroma + PDF）

用法：
    python backend/redeep.py --dry-run                 # 只看会做什么，不动数据
    python backend/redeep.py --delete lit_xxx          # 删一篇（SQLite + Chroma + PDF）
    python backend/redeep.py --id lit_xxx              # 只重跑某一篇
    python backend/redeep.py                           # 重跑全部（先备份 app.db）
    python backend/redeep.py --no-vectors              # 跳过检索块重灌（省 embedding）
    python backend/redeep.py --no-parse                # 跳过深解析（只重灌检索块）

会调用 DashScope：
  - deep_parse：每篇 1 次或多次 LLM 调用
  - 检索块重灌：每篇若干次 embedding
执行前会自动把 app.db 备份为 app.db.bak
"""
import argparse
import json
import os
import shutil
import sqlite3
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(ROOT, 'backend', 'data', 'app.db')
RAW_DIR = os.path.join(ROOT, 'data', 'raw')


def _vs():
    from core.vector_store import load_vectorstore
    return load_vectorstore()


def _chunks_of(vs, doc_id):
    """取该 doc 在 Chroma 里的所有块 id"""
    try:
        got = vs._collection.get(where={'doc_id': doc_id})
        return got.get('ids') or []
    except Exception as e:
        print(f'   ⚠ 读取向量库失败：{e}')
        return []


def backup(db_path):
    if not os.path.exists(db_path):
        return None
    bak = db_path + '.bak'
    shutil.copy2(db_path, bak)
    return bak


def do_delete(conn, doc_id, dry_run):
    cur = conn.cursor()
    row = cur.execute('SELECT id, title FROM docs WHERE id = ?', (doc_id,)).fetchone()
    if not row:
        print(f'❌ 库里没有 {doc_id}')
        return
    print(f'删除文献：{doc_id}  {row[1][:44]}')

    ids = _chunks_of(_vs(), doc_id)
    print(f'   Chroma 检索块：{len(ids)} 个')
    if dry_run:
        print('   [dry-run] 不执行删除')
        return
    if ids:
        try:
            _vs()._collection.delete(ids=ids)
            print(f'   ✅ 已从向量库删除 {len(ids)} 个块')
        except Exception as e:
            print(f'   ❌ 向量库删除失败：{e}')
    cur.execute('DELETE FROM docs WHERE id = ?', (doc_id,))
    conn.commit()
    print('   ✅ 已从 SQLite 删除')

    # 顺手删 PDF
    pdf = os.path.join(RAW_DIR, f'{doc_id}.pdf')
    if os.path.exists(pdf):
        try:
            os.remove(pdf)
            print('   ✅ 已删 PDF')
        except Exception as e:
            print(f'   ⚠️ PDF 删除失败：{e}')


def rebuild_one(conn, doc_id, title, with_vectors, with_parse, dry_run):
    """
    重跑一篇：
      1. 从 PDF 重解析（如果有原始 PDF）
      2. 重新分段（行距判段）
      3. 重灌检索块（可选）
      4. 重跑深解析（可选）
      5. 更新 SQLite
    """
    from backend.pdf_parser import (parse_pdf, join_lines_text,
                                    split_for_reading, split_for_rag)
    from backend.deep_parse import deep_parse

    print('─' * 68)
    print(f'{doc_id}  {title[:44]}')

    pdf_path = os.path.join(RAW_DIR, f'{doc_id}.pdf')
    if not os.path.exists(pdf_path):
        print(f'   ❌ 找不到 PDF：{pdf_path}，跳过（无法重建段落）')
        return

    if dry_run:
        print(f'   [dry-run] 将：PDF 重解析 → 重分段 → '
              f'{"重灌检索块 " if with_vectors else ""}'
              f'{"重跑深解析" if with_parse else ""}')
        return

    # 1. 重解析 PDF（行列表）
    try:
        lines = parse_pdf(pdf_path)
        text = join_lines_text(lines)
    except Exception as e:
        print(f'   ❌ PDF 解析失败：{e}')
        return

    # 2. 重分段
    try:
        paragraphs = split_for_reading(lines)
    except Exception as e:
        print(f'   ❌ 分段失败：{e}')
        return
    print(f'   段落数：{len(paragraphs)}')

    # 3. 重灌检索块
    if with_vectors:
        try:
            from backend.pdf_parser import strip_references
            text_for_rag = strip_references(text)
            chunks = split_for_rag(text_for_rag)
            vs = _vs()
            old = _chunks_of(vs, doc_id)
            # 顺序很重要：必须先把新块写进去，成功后再删旧块。
            # 反过来的话，一旦 embedding 配额耗尽（DashScope 403）导致 add 失败，
            # 旧块已经被删、新块又没进来，这篇文献的检索块就归零，问答彻底召回不到它。
            from langchain_core.documents import Document
            vs.add_documents([
                Document(page_content=c, metadata={'doc_id': doc_id, 'source': title})
                for c in chunks
            ])
            if old:
                vs._collection.delete(ids=old)
            print(f'   检索块：{len(old)} → {len(chunks)}')
        except Exception as e:
            print(f'   ⚠️ 检索块重灌失败（旧块已保留，段落不受影响）：{e}')
            print(f'   ⚠️ 这篇的检索块没更新；若下面整批都失败，检索块可能为空，问答将召回不到内容。')

    # 4. 重跑深解析
    fields = None
    if with_parse:
        try:
            t0 = time.time()
            fields = deep_parse(text, paragraphs=paragraphs)
            ok = sum(1 for v in fields.values() if isinstance(v, dict) and v.get('verified'))
            total = sum(1 for v in fields.values() if isinstance(v, dict))
            avg_len = (sum(len(v['text']) for v in fields.values()
                           if isinstance(v, dict) and v.get('text'))
                       // max(1, total)) if total else 0
            print(f'   深解析：{ok}/{total} 通过校验，平均 {avg_len} 字/字段（{time.time()-t0:.1f}s）')
        except Exception as e:
            print(f'   ❌ 深解析失败：{e}')
            return

    # 5. 落库
    cur = conn.cursor()
    if fields is not None:
        cur.execute(
            'UPDATE docs SET text = ?, paragraphs = ?, fields = ? WHERE id = ?',
            (text, json.dumps(paragraphs, ensure_ascii=False),
             json.dumps(fields, ensure_ascii=False), doc_id)
        )
    else:
        cur.execute(
            'UPDATE docs SET text = ?, paragraphs = ? WHERE id = ?',
            (text, json.dumps(paragraphs, ensure_ascii=False), doc_id)
        )
    conn.commit()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--id', default=None)
    ap.add_argument('--delete', default=None, metavar='DOC_ID')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--no-vectors', action='store_true', help='跳过检索块重灌')
    ap.add_argument('--no-parse', action='store_true', help='跳过深解析')
    args = ap.parse_args()

    if not os.path.exists(DB_PATH):
        print(f'❌ 找不到数据库：{DB_PATH}')
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    if args.delete:
        print('=== 删除模式 ===')
        do_delete(conn, args.delete, args.dry_run)
        conn.close()
        return

    with_vectors = not args.no_vectors
    with_parse = not args.no_parse

    if args.id:
        rows = conn.execute(
            'SELECT id, title FROM docs WHERE id = ?', (args.id,)).fetchall()
    else:
        rows = conn.execute('SELECT id, title FROM docs').fetchall()

    print(f'=== 重建模式：{len(rows)} 篇 '
          f'/ 检索块={"开" if with_vectors else "关"} '
          f'/ 深解析={"开" if with_parse else "关"} ===')
    if not args.dry_run:
        print(f'已备份数据库 → {backup(DB_PATH)}\n')

    for r in rows:
        try:
            rebuild_one(conn, r['id'], r['title'],
                        with_vectors, with_parse, args.dry_run)
        except Exception as e:
            print(f'   ❌ {r["id"]} 失败：{e}')

    conn.close()
    print('\n完成。')


if __name__ == '__main__':
    main()
