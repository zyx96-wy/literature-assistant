# -*- coding: utf-8 -*-
"""
重新分段工具（修存量数据）
==========================

背景：早期版本的两处问题会让阅读页看起来是「半句在上一段、半句在下一段」：
  1. parse_pdf 用 get_text('text', sort=True)，双栏 PDF 会把左右栏拼进同一行
  2. split_for_reading 用 RecursiveCharacterTextSplitter 按字符数硬切（800），
     切点落在哪里完全随机，句中被切断是常态

本脚本对库里已有的文献重建**阅读段落**（不涉及检索块，检索块另外处理）。

用法：
    python backend/resegment.py                 # 重建全部文献的阅读段落（先自动备份）
    python backend/resegment.py --id lit_xxx    # 只处理某一篇
    python backend/resegment.py --dry-run       # 只看效果，不写库
    python backend/resegment.py --with-rag      # 连检索块一起重建（会调 embedding API）

注意：
  - 执行前会自动把 app.db 备份为 app.db.bak
  - 「从 PDF 重解析」需要 data/raw/{id}.pdf 存在 + 已安装 pymupdf
    找不到 PDF 时退化为「用库里现有 text 重新切分」，此时栏序问题无法修复，
    脚本会明确标注 degraded=1
"""
import argparse
import json
import os
import shutil
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'app.db')
RAW_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'raw')


def _load_parsers():
    """延迟导入：本机没装 pymupdf / langchain 时给出明确提示，"""
    try:
        from backend.pdf_parser import (parse_pdf, join_lines_text,
                                        split_for_reading, split_for_rag)
        return parse_pdf, join_lines_text, split_for_reading, split_for_rag
    except Exception as e:
        print(f'❌ 无法导入 pdf_parser：{e}')
        print('   请先安装依赖： pip install pymupdf langchain-text-splitters')
        sys.exit(1)


def _locate(quote, pid, paragraphs):
    """复用深解析的定位逻辑：精确 → 邻近±2 → 全文"""
    try:
        from backend.deep_parse import _locate_quote, _norm
        return _locate_quote(quote, pid, paragraphs)
    except Exception:
        return None


def backup(db_path):
    if not os.path.exists(db_path):
        return None
    bak = db_path + '.bak'
    shutil.copy2(db_path, bak)
    return bak


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--id', default=None, help='只处理指定文献 id')
    ap.add_argument('--dry-run', action='store_true', help='只打印效果，不写库')
    ap.add_argument('--with-rag', action='store_true', help='同时重建检索块（会调 embedding API）')
    args = ap.parse_args()

    parse_pdf, join_lines_text, split_for_reading, split_for_rag = _load_parsers()

    if not os.path.exists(DB_PATH):
        print(f'❌ 找不到数据库：{DB_PATH}')
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    if args.id:
        cur.execute('SELECT id, title, text, paragraphs, fields FROM docs WHERE id = ?', (args.id,))
    else:
        cur.execute('SELECT id, title, text, paragraphs, fields FROM docs')
    rows = cur.fetchall()
    print(f'待处理文献：{len(rows)} 篇\n')

    if not args.dry_run:
        bak = backup(DB_PATH)
        print(f'已备份数据库 → {bak}\n')

    for r in rows:
        doc_id, title = r['id'], r['title']
        pdf_path = os.path.join(RAW_DIR, f'{doc_id}.pdf')

        degraded = False
        text = r['text'] or ''
        lines = None          # 行列表 [(y,x0,size,text)...]，带坐标才能走行距判段
        if os.path.exists(pdf_path):
            try:
                new_lines = parse_pdf(pdf_path)
                # parse_pdf 返回行列表，必须先拼成文本再比长度；
                # 直接 len(list) 比的是行数，和字符数不是一个量纲，会误判成「解析异常」而退化
                new_text = join_lines_text(new_lines)
                if new_text and len(new_text) > len(text) * 0.5:
                    lines = new_lines
                    text = new_text
                    src = f'PDF 重解析（{os.path.basename(pdf_path)}）'
                else:
                    degraded = True
                    src = 'PDF 解析结果异常，退化用库内 text'
            except Exception as e:
                degraded = True
                src = f'PDF 解析失败（{e}），退化用库内 text'
        else:
            degraded = True
            src = '无原始 PDF，退化用库内 text（栏序问题无法修复）'

        old_ps = json.loads(r['paragraphs']) if r['paragraphs'] else []
        # 有行列表 → 行距判段（还原自然段落）；否则退化成纯文本判段
        new_ps = split_for_reading(lines if lines else text)

        # 旧段落里「非句末结尾」的比例 —— 用来量化改善
        def bad_ratio(ps):
            if not ps:
                return 0.0
            b = sum(1 for p in ps if p.strip()[-1:] not in '。！？；….!?;')
            return b / len(ps)

        print('─' * 68)
        print(f'{doc_id}  {title[:44]}')
        print(f'   来源      : {src}')
        print(f'   段落数    : {len(old_ps)} → {len(new_ps)}')
        print(f'   非句末结尾: {bad_ratio(old_ps):.0%} → {bad_ratio(new_ps):.0%}')
        print(f'   平均段长  : {sum(len(p) for p in old_ps) // max(1, len(old_ps))} → '
              f'{sum(len(p) for p in new_ps) // max(1, len(new_ps))}')

        if args.dry_run:
            for p in new_ps[:3]:
                print(f'      ¶ {p[:78]}')
            continue

        # 字段溯源重定位：有 quote 就重新定位，没有就如实标记未通过
        fields = json.loads(r['fields']) if r['fields'] else {}
        relocated = 0
        for k, v in fields.items():
            if not isinstance(v, dict):
                continue
            q = (v.get('quote') or '').strip()
            if q:
                # _locate 返回 (pid, match) 元组，必须取 [0]；
                # 且 (None, None) 是非空元组、truthy —— 不解包判断会把「定位失败」当成成功
                old_pid = v.get('pid')
                if not isinstance(old_pid, int):   # 历史脏数据：pid 被存成过 list
                    old_pid = 1
                hit = _locate(q, old_pid, new_ps)
                if hit and hit[0]:
                    v['loc'] = f'¶{hit[0]}'
                    v['pid'] = hit[0]
                    v['verified'] = True
                    relocated += 1
                    continue
            v['verified'] = False      # 段落号变了，无法证明 → 不许装作已验证
        print(f'   字段溯源  : 重新定位 {relocated} 项，其余标记为未通过（不伪造）')

        cur.execute(
            'UPDATE docs SET text = ?, paragraphs = ?, fields = ? WHERE id = ?',
            (text, json.dumps(new_ps, ensure_ascii=False),
             json.dumps(fields, ensure_ascii=False), doc_id)
        )
        conn.commit()

        if args.with_rag:
            print('   ⚠ --with-rag 需要重建向量库，请改为重新上传该文献（脚本不替你调 embedding API）')

    conn.close()
    print('\n完成。')
    if degraded:
        print('注意：有文献退化为「用库内 text 重切」，双栏错乱仍在。'
              '把原始 PDF 放到 data/raw/{id}.pdf 后重跑可彻底修复。')


if __name__ == '__main__':
    main()
