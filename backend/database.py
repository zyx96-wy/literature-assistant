# -*- coding: utf-8 -*-
"""
SQLite 数据库层：存文档元数据 + 解析字段
"""
import sqlite3
import json
import os
from config.settings import BASE_DIR

DB_PATH = os.path.join(BASE_DIR, 'backend', 'data', 'app.db')
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS docs (
            id TEXT PRIMARY KEY,
            title TEXT,
            meta TEXT,
            text TEXT,
            paragraphs TEXT,
            fields TEXT,
            deleted INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS notes (
            id TEXT PRIMARY KEY,
            doc_id TEXT,
            pid INTEGER,
            quote TEXT,
            status TEXT DEFAULT 'active',
            current_version TEXT,
            versions TEXT,
            related TEXT,
            project_id TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_notes_doc ON notes(doc_id)')
    conn.commit()
    conn.close()
    print(f'✅ 数据库已初始化：{DB_PATH}')


def insert_doc_with_paragraphs(doc_id, title, meta, text, paragraphs, fields):
    """存文档 + 阅读段落 + 字段"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        '''INSERT OR REPLACE INTO docs
           (id, title, meta, text, paragraphs, fields, deleted)
           VALUES (?, ?, ?, ?, ?, ?, 0)''',
        (
            doc_id, title, meta, text,
            json.dumps(paragraphs, ensure_ascii=False),
            json.dumps(fields, ensure_ascii=False)
        )
    )
    conn.commit()
    conn.close()


def get_all_docs():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT id, title, meta, deleted FROM docs WHERE deleted = 0 ORDER BY created_at DESC')
    rows = c.fetchall()
    conn.close()
    return [{'id': r[0], 'title': r[1], 'meta': r[2], 'deleted': bool(r[3])} for r in rows]


def get_doc(doc_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT id, title, meta, text, paragraphs, fields FROM docs WHERE id = ?', (doc_id,))
    r = c.fetchone()
    conn.close()
    if not r:
        return None
    return {
        'id': r[0],
        'title': r[1],
        'meta': r[2],
        'text': r[3],
        'paragraphs': json.loads(r[4]) if r[4] else [],
        'fields': json.loads(r[5]) if r[5] else {}
    }