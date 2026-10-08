# -*- coding: utf-8 -*-
"""
SQLite 数据库层：存文档元数据 + 解析字段 + 笔记 + 综述
"""
import sqlite3
import json
import os
import re
import uuid
from config.settings import BASE_DIR

DB_PATH = os.path.join(BASE_DIR, 'backend', 'data', 'app.db')
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


def _connect():
    """统一的连接入口，方便将来换路径 / 加配置"""
    return sqlite3.connect(DB_PATH)


def init_db():
    conn = _connect()
    c = conn.cursor()

    # ---- docs：文献元数据 + 阅读段落 + 深解析字段 ----
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

    # ---- notes：笔记（版本链）----
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
    c.execute('CREATE INDEX IF NOT EXISTS idx_notes_status ON notes(status)')

    # ---- reviews：综述（独立于 notes / 知识库）----
    c.execute('''
        CREATE TABLE IF NOT EXISTS reviews (
            id TEXT PRIMARY KEY,
            topic TEXT NOT NULL,
            scope TEXT NOT NULL,
            project_id TEXT,
            status TEXT DEFAULT 'awaiting_review',
            points TEXT,
            deleted INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_reviews_project ON reviews(project_id)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_reviews_deleted ON reviews(deleted)')

    # ---- messages：问答历史（多轮对话用）----
    c.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            sources TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id)')

    # ---- projects：项目（PRD 9.20：总库是超集，项目是子集）----
    c.execute('''
        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            archived INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # ---- project_docs：项目内文献（移除 ≠ 删除，总库保留）----
    c.execute('''
        CREATE TABLE IF NOT EXISTS project_docs (
            project_id TEXT NOT NULL,
            doc_id TEXT NOT NULL,
            added_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (project_id, doc_id)
        )
    ''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_project_docs_doc ON project_docs(doc_id)')

    # 项目名唯一（只约束未归档项目；存量若有重名则建索引失败，由应用层兜底校验）
    try:
        c.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_projects_name '
                  'ON projects(name) WHERE archived = 0')
    except Exception as e:
        print(f'⚠️ 未建立项目名唯一索引（存量可能存在重名，改由应用层校验）：{e}')

    # ---- tags：标签（独立表，支持颜色 / 改名 / 删除）----
    # kind: topic = 主题关键词（可多个）；status = 状态（互斥，一篇文献只能有一个）
    c.execute('''
        CREATE TABLE IF NOT EXISTS tags (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            name_norm TEXT NOT NULL,
            kind TEXT DEFAULT 'topic',
            color TEXT,
            sort INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    c.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_tags_name_norm ON tags(name_norm)')

    # ---- doc_tags：文献 × 标签（多对多）----
    c.execute('''
        CREATE TABLE IF NOT EXISTS doc_tags (
            doc_id TEXT NOT NULL,
            tag_id TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (doc_id, tag_id)
        )
    ''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_doc_tags_tag ON doc_tags(tag_id)')

    # ---- knowledge：知识库（论断 + 可溯源来源）----
    # source_pid 是 split_for_reading 产出的「阅读段号 ¶N」，不是检索块号
    c.execute('''
        CREATE TABLE IF NOT EXISTS knowledge (
            id TEXT PRIMARY KEY,
            claim TEXT NOT NULL,
            source_type TEXT DEFAULT 'manual',
            source_doc_id TEXT,
            source_pid INTEGER,
            source_quote TEXT,
            source_note_id TEXT,
            source_session_id TEXT,
            tags TEXT,
            project_id TEXT,
            status TEXT DEFAULT 'active',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_knowledge_status ON knowledge(status)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_knowledge_doc ON knowledge(source_doc_id)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_knowledge_note ON knowledge(source_note_id)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_knowledge_project ON knowledge(project_id)')

    conn.commit()
    _seed_tags()
    conn.close()
    print(f'✅ 数据库已初始化：{DB_PATH}')


# ============================================================
# projects
# ============================================================

def _project_name_taken(name: str, exclude_id: str = None) -> bool:
    """项目名是否已被占用（只跟未归档项目比；排除 exclude_id 自身，供改名用）"""
    conn = _connect()
    if exclude_id:
        row = conn.execute(
            'SELECT 1 FROM projects WHERE name = ? AND archived = 0 AND id <> ?',
            (name, exclude_id)
        ).fetchone()
    else:
        row = conn.execute(
            'SELECT 1 FROM projects WHERE name = ? AND archived = 0', (name,)
        ).fetchone()
    conn.close()
    return row is not None


def create_project(name: str, project_id: str = None) -> dict:
    name = (name or '').strip()
    if not name:
        raise ValueError('项目名不能为空')
    if _project_name_taken(name):
        raise ValueError(f'项目名已存在：{name}')
    project_id = project_id or ('proj_' + uuid.uuid4().hex[:8])
    conn = _connect()
    c = conn.cursor()
    c.execute(
        'INSERT INTO projects (id, name) VALUES (?, ?)', (project_id, name)
    )
    conn.commit()
    conn.close()
    return get_project(project_id)


def get_project(project_id: str):
    conn = _connect()
    conn.row_factory = sqlite3.Row
    r = conn.execute('SELECT * FROM projects WHERE id = ?', (project_id,)).fetchone()
    conn.close()
    return dict(r) if r else None


def get_all_projects(include_archived: bool = False):
    conn = _connect()
    conn.row_factory = sqlite3.Row
    sql = 'SELECT * FROM projects'
    if not include_archived:
        sql += ' WHERE archived = 0'
    sql += ' ORDER BY created_at'
    rows = conn.execute(sql).fetchall()
    out = []
    for r in rows:
        p = dict(r)
        p['docs'] = get_project_docs(p['id'])
        out.append(p)
    conn.close()
    return out


def update_project(project_id: str, name: str = None, archived: int = None):
    conn = _connect()
    c = conn.cursor()
    sets, vals = [], []
    if name is not None:
        name = (name or '').strip()
        if not name:
            conn.close()
            raise ValueError('项目名不能为空')
        if _project_name_taken(name, exclude_id=project_id):
            conn.close()
            raise ValueError(f'项目名已存在：{name}')
        sets.append('name = ?')
        vals.append(name)
    if archived is not None:
        sets.append('archived = ?')
        vals.append(archived)
    if not sets:
        conn.close()
        return get_project(project_id)
    sets.append('updated_at = CURRENT_TIMESTAMP')
    vals.append(project_id)
    c.execute(f'UPDATE projects SET {", ".join(sets)} WHERE id = ?', vals)
    conn.commit()
    conn.close()
    return get_project(project_id)


def delete_project(project_id: str):
    """彻底删除项目（不动文献本身，只解绑）"""
    conn = _connect()
    c = conn.cursor()
    c.execute('DELETE FROM project_docs WHERE project_id = ?', (project_id,))
    c.execute('DELETE FROM projects WHERE id = ?', (project_id,))
    conn.commit()
    conn.close()


def get_project_docs(project_id: str) -> list:
    conn = _connect()
    rows = conn.execute(
        'SELECT doc_id FROM project_docs WHERE project_id = ? ORDER BY added_at',
        (project_id,)
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]


def add_doc_to_project(project_id: str, doc_id: str) -> bool:
    """返回 True=新增，False=已存在"""
    conn = _connect()
    c = conn.cursor()
    exist = c.execute(
        'SELECT 1 FROM project_docs WHERE project_id = ? AND doc_id = ?',
        (project_id, doc_id)
    ).fetchone()
    if exist:
        conn.close()
        return False
    c.execute(
        'INSERT INTO project_docs (project_id, doc_id) VALUES (?, ?)',
        (project_id, doc_id)
    )
    conn.commit()
    conn.close()
    return True


def remove_doc_from_project(project_id: str, doc_id: str):
    conn = _connect()
    c = conn.cursor()
    c.execute(
        'DELETE FROM project_docs WHERE project_id = ? AND doc_id = ?',
        (project_id, doc_id)
    )
    conn.commit()
    conn.close()


# ============================================================
# docs
# ============================================================

def insert_doc_with_paragraphs(doc_id, title, meta, text, paragraphs, fields):
    """存文档 + 阅读段落 + 字段"""
    conn = _connect()
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


def get_all_docs(tag: str = None):
    """文献列表。带 tag 参数时只返回打了该标签的文献（传标签 id 或名字都行）。"""
    conn = _connect()
    c = conn.cursor()
    c.execute('SELECT id, title, meta, deleted FROM docs WHERE deleted = 0 ORDER BY created_at DESC')
    rows = c.fetchall()
    tmap = _doc_tags_map(conn)
    conn.close()
    out = [{
        'id': r[0], 'title': r[1], 'meta': r[2], 'deleted': bool(r[3]),
        'tags': tmap.get(r[0], [])
    } for r in rows]
    if tag:
        keep = set(get_docs_by_tag(tag))
        out = [d for d in out if d['id'] in keep]
    return out


def get_doc(doc_id):
    conn = _connect()
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


def soft_delete_doc(doc_id):
    """软删除文献：docs.deleted = 1"""
    conn = _connect()
    c = conn.cursor()
    c.execute('UPDATE docs SET deleted = 1 WHERE id = ?', (doc_id,))
    conn.commit()
    conn.close()


def restore_doc(doc_id):
    """恢复软删的文献：docs.deleted = 0"""
    conn = _connect()
    c = conn.cursor()
    c.execute('UPDATE docs SET deleted = 0 WHERE id = ?', (doc_id,))
    conn.commit()
    conn.close()


def purge_doc(doc_id):
    """彻底删除：从 docs 表删记录。Chroma 的删除在 api.py 里做（要拿 vs）。"""
    conn = _connect()
    c = conn.cursor()
    c.execute('DELETE FROM docs WHERE id = ?', (doc_id,))
    conn.commit()
    conn.close()


def get_deleted_docs():
    """回收站：列出已软删的文献"""
    conn = _connect()
    c = conn.cursor()
    c.execute('SELECT id, title, meta FROM docs WHERE deleted = 1 ORDER BY created_at DESC')
    rows = c.fetchall()
    tmap = _doc_tags_map(conn)
    conn.close()
    return [{'id': r[0], 'title': r[1], 'meta': r[2],
             'tags': tmap.get(r[0], [])} for r in rows]

# ============================================================
# reviews（综述）
# ============================================================


def insert_review(topic, scope, project_id=None, points=None, status='awaiting_review'):
    """
    新建综述。

    :param topic: 综述主题
    :param scope: doc_id 列表
    :param project_id: 所属项目，None = 全库综述
    :param points: 论点数组（生成阶段写入；空壳阶段允许 None）
    :param status: awaiting_review | reviewed | archived
    :return: 新综述 id
    """
    rid = 'rev_' + str(uuid.uuid4())[:8]
    conn = _connect()
    c = conn.cursor()
    c.execute(
        '''INSERT INTO reviews
           (id, topic, scope, project_id, status, points, deleted)
           VALUES (?, ?, ?, ?, ?, ?, 0)''',
        (
            rid, topic,
            json.dumps(scope or [], ensure_ascii=False),
            project_id, status,
            json.dumps(points or [], ensure_ascii=False)
        )
    )
    conn.commit()
    conn.close()
    return rid


def _row_to_review(r):
    return {
        'id': r[0],
        'topic': r[1],
        'scope': json.loads(r[2]) if r[2] else [],
        'project_id': r[3],
        'status': r[4],
        'points': json.loads(r[5]) if r[5] else [],
        'deleted': bool(r[6]),
        'created_at': r[7],
        'updated_at': r[8]
    }


def get_all_reviews(project_id=None, include_deleted=False):
    """
    列出综述。

    :param project_id: 只列某个项目的综述；None = 全库 + 所有项目
    :param include_deleted: 是否包含已软删
    """
    conn = _connect()
    c = conn.cursor()
    sql = ('SELECT id, topic, scope, project_id, status, points, deleted, created_at, updated_at '
           'FROM reviews WHERE 1=1')
    params = []
    if not include_deleted:
        sql += ' AND deleted = 0'
    if project_id is not None:
        sql += ' AND project_id = ?'
        params.append(project_id)
    sql += ' ORDER BY updated_at DESC'
    c.execute(sql, params)
    rows = c.fetchall()
    conn.close()
    return [_row_to_review(r) for r in rows]


def get_review(rid):
    conn = _connect()
    c = conn.cursor()
    c.execute(
        'SELECT id, topic, scope, project_id, status, points, deleted, created_at, updated_at '
        'FROM reviews WHERE id = ?', (rid,)
    )
    r = c.fetchone()
    conn.close()
    if not r:
        return None
    return _row_to_review(r)


def update_review(rid, **fields):
    """
    更新综述的可变字段。
    允许：topic / scope / project_id / status / points
    """
    allowed = {'topic', 'scope', 'project_id', 'status', 'points'}
    sets, params = [], []
    for k, v in fields.items():
        if k not in allowed:
            continue
        if k in ('scope', 'points'):
            v = json.dumps(v, ensure_ascii=False)
        sets.append(f'{k} = ?')
        params.append(v)
    if not sets:
        return False
    sets.append('updated_at = CURRENT_TIMESTAMP')
    params.append(rid)
    conn = _connect()
    c = conn.cursor()
    c.execute(f'UPDATE reviews SET {", ".join(sets)} WHERE id = ?', params)
    conn.commit()
    conn.close()
    return True


def soft_delete_review(rid):
    conn = _connect()
    c = conn.cursor()
    c.execute('UPDATE reviews SET deleted = 1, updated_at = CURRENT_TIMESTAMP WHERE id = ?', (rid,))
    conn.commit()
    conn.close()


def restore_review(rid):
    conn = _connect()
    c = conn.cursor()
    c.execute('UPDATE reviews SET deleted = 0, updated_at = CURRENT_TIMESTAMP WHERE id = ?', (rid,))
    conn.commit()
    conn.close()


def purge_review(rid):
    """彻底删除（不可恢复）。只应由「二次确认」的接口调用。"""
    conn = _connect()
    c = conn.cursor()
    c.execute('DELETE FROM reviews WHERE id = ?', (rid,))
    conn.commit()
    conn.close()

# ============================================================
# notes（笔记）
# ============================================================


def insert_note(note_id, doc_id, pid, quote, versions, related=None, project_id=None):
    """新建笔记"""
    conn = _connect()
    c = conn.cursor()
    c.execute(
        '''INSERT INTO notes
           (id, doc_id, pid, quote, status, versions, related, project_id)
           VALUES (?, ?, ?, ?, 'active', ?, ?, ?)''',
        (
            note_id, doc_id, pid, quote,
            json.dumps(versions, ensure_ascii=False),
            related, project_id
        )
    )
    conn.commit()
    conn.close()


def get_note(note_id):
    conn = _connect()
    c = conn.cursor()
    c.execute(
        'SELECT id, doc_id, pid, quote, status, versions, related, project_id, created_at, updated_at '
        'FROM notes WHERE id = ?', (note_id,)
    )
    r = c.fetchone()
    conn.close()
    if not r:
        return None
    return {
        'id': r[0],
        'doc': r[1],          # 前端叫 doc
        'pid': r[2],
        'quote': r[3],
        'status': r[4],
        'versions': json.loads(r[5]) if r[5] else [],
        'related': r[6],
        'project_id': r[7],
        'created_at': r[8],
        'updated_at': r[9]
    }


def get_notes_by_doc(doc_id):
    """某篇文献的所有 active 笔记"""
    conn = _connect()
    c = conn.cursor()
    c.execute(
        'SELECT id, doc_id, pid, quote, status, versions, related, project_id, created_at, updated_at '
        'FROM notes WHERE doc_id = ? AND status = "active" ORDER BY created_at DESC',
        (doc_id,)
    )
    rows = c.fetchall()
    conn.close()
    return [{
        'id': r[0], 'doc': r[1], 'pid': r[2], 'quote': r[3],
        'status': r[4],
        'versions': json.loads(r[5]) if r[5] else [],
        'related': r[6], 'project_id': r[7],
        'created_at': r[8], 'updated_at': r[9]
    } for r in rows]


def get_all_notes():
    """全部 active 笔记（笔记总览页用）"""
    conn = _connect()
    c = conn.cursor()
    c.execute(
        'SELECT id, doc_id, pid, quote, status, versions, related, project_id, created_at, updated_at '
        'FROM notes WHERE status = "active" ORDER BY created_at DESC'
    )
    rows = c.fetchall()
    conn.close()
    return [{
        'id': r[0], 'doc': r[1], 'pid': r[2], 'quote': r[3],
        'status': r[4],
        'versions': json.loads(r[5]) if r[5] else [],
        'related': r[6], 'project_id': r[7],
        'created_at': r[8], 'updated_at': r[9]
    } for r in rows]


def update_note(note_id, **fields):
    """更新笔记的 versions / status / related"""
    allowed = {'versions', 'status', 'related', 'quote'}
    sets, params = [], []
    for k, v in fields.items():
        if k not in allowed:
            continue
        if k == 'versions':
            v = json.dumps(v, ensure_ascii=False)
        sets.append(f'{k} = ?')
        params.append(v)
    if not sets:
        return False
    sets.append('updated_at = CURRENT_TIMESTAMP')
    params.append(note_id)
    conn = _connect()
    c = conn.cursor()
    c.execute(f'UPDATE notes SET {", ".join(sets)} WHERE id = ?', params)
    conn.commit()
    conn.close()
    return True


def soft_delete_note(note_id):
    """软删除笔记"""
    conn = _connect()
    c = conn.cursor()
    c.execute('UPDATE notes SET status = "deleted", updated_at = CURRENT_TIMESTAMP WHERE id = ?', (note_id,))
    conn.commit()
    conn.close()

# ============================================================
# messages（问答历史）
# ============================================================

def insert_message(session_id, role, content, sources=None):
    """存一条消息（user 或 assistant）"""
    mid = 'msg_' + str(uuid.uuid4())[:8]
    conn = _connect()
    c = conn.cursor()
    c.execute(
        '''INSERT INTO messages (id, session_id, role, content, sources)
           VALUES (?, ?, ?, ?, ?)''',
        (mid, session_id, role, content,
         json.dumps(sources, ensure_ascii=False) if sources else None)
    )
    conn.commit()
    conn.close()
    return mid


def get_recent_user_questions(session_id, limit=3):
    """取最近 N 轮的「用户问题」（不取答案，防幻觉累积）"""
    conn = _connect()
    c = conn.cursor()
    c.execute(
        '''SELECT content FROM messages
           WHERE session_id = ? AND role = 'user'
           ORDER BY created_at DESC LIMIT ?''',
        (session_id, limit)
    )
    rows = c.fetchall()
    conn.close()
    # 取出来是倒序（最新的在前），反转成正序
    return [r[0] for r in reversed(rows)]


def get_messages_by_session(session_id):
    """取某 session 的所有消息（用于展示历史）"""
    conn = _connect()
    c = conn.cursor()
    c.execute(
        '''SELECT id, role, content, sources, created_at
           FROM messages WHERE session_id = ?
           ORDER BY created_at ASC''',
        (session_id,)
    )
    rows = c.fetchall()
    conn.close()
    return [{
        'id': r[0], 'role': r[1], 'content': r[2],
        'sources': json.loads(r[3]) if r[3] else [],
        'created_at': r[4]
    } for r in rows]


# ============================================================
# tags（独立表） + doc_tags（文献 × 标签）
# ============================================================

TAG_PALETTE = ['#378ADD', '#1D9E75', '#BA7517', '#7F77DD',
               '#D85A30', '#D4537E', '#639922', '#888780']

# 预置标签：(名字, kind, 颜色)。kind: topic=主题关键词（可多个），status=状态（互斥）
SEED_TAGS = [
    ('未读', 'status', '#888780'),
    ('已读', 'status', '#639922'),
    ('大模型', 'topic', '#378ADD'),
    ('RAG', 'topic', '#1D9E75'),
    ('调优', 'topic', '#BA7517'),
    ('多读', 'topic', '#7F77DD'),
    ('没看懂', 'topic', '#D85A30'),
]


def _norm_tag_name(name: str) -> str:
    """归一化：去掉所有空白 + 转小写。'RAG' / 'rag ' / 'R A G' 视为同一个标签。"""
    return re.sub(r'\s+', '', (name or '').strip()).lower()


def _seed_tags():
    """预置常用标签；已存在（按 name_norm 判定）则跳过。"""
    for name, kind, color in SEED_TAGS:
        try:
            create_tag(name, kind=kind, color=color)
        except Exception as e:
            print(f'⚠️ 预置标签「{name}」失败：{e}')


def _row_to_tag(r) -> dict:
    return {
        'id': r['id'],
        'name': r['name'],
        'kind': r['kind'] or 'topic',
        'color': r['color'] or TAG_PALETTE[0],
        'sort': r['sort'] or 0,
        'doc_count': r['doc_count'] if 'doc_count' in r.keys() else 0,
        'created_at': r['created_at'],
        'updated_at': r['updated_at'],
    }


def _ensure_tag(conn, name, kind=None, color=None) -> dict:
    """按名字取标签，不存在就创建。走调用方传入的连接，避免嵌套连接互相锁表。"""
    nn = _norm_tag_name(name)
    if not nn:
        raise ValueError('标签名不能为空')
    display = re.sub(r'\s+', '', (name or '').strip())
    conn.row_factory = sqlite3.Row
    row = conn.execute('SELECT * FROM tags WHERE name_norm = ?', (nn,)).fetchone()
    if row:
        return dict(row)
    # 兜底：万一上游传的是标签 id（tag_xxx），别把它当成一个新标签名建出来
    if display.startswith('tag_'):
        by_id = conn.execute('SELECT * FROM tags WHERE id = ?', (display,)).fetchone()
        if by_id:
            return dict(by_id)
    if kind is None:
        status_names = {_norm_tag_name(n) for n, k, _ in SEED_TAGS if k == 'status'}
        kind = 'status' if nn in status_names else 'topic'
    if not color:
        n = conn.execute('SELECT COUNT(*) FROM tags').fetchone()[0]
        color = TAG_PALETTE[n % len(TAG_PALETTE)]
    tid = 'tag_' + uuid.uuid4().hex[:8]
    conn.execute(
        'INSERT INTO tags (id, name, name_norm, kind, color) VALUES (?, ?, ?, ?, ?)',
        (tid, display, nn, kind, color)
    )
    conn.commit()
    return dict(conn.execute('SELECT * FROM tags WHERE id = ?', (tid,)).fetchone())


def create_tag(name: str, kind: str = None, color: str = None) -> dict:
    conn = _connect()
    try:
        return _ensure_tag(conn, name, kind=kind, color=color)
    finally:
        conn.close()


def get_all_tags() -> list:
    conn = _connect()
    conn.row_factory = sqlite3.Row
    rows = conn.execute('''
        SELECT t.*, (SELECT COUNT(*) FROM doc_tags dt WHERE dt.tag_id = t.id) AS doc_count
        FROM tags t ORDER BY t.sort, t.created_at
    ''').fetchall()
    conn.close()
    return [_row_to_tag(r) for r in rows]


def get_tag(tag_id: str):
    conn = _connect()
    conn.row_factory = sqlite3.Row
    r = conn.execute('SELECT * FROM tags WHERE id = ?', (tag_id,)).fetchone()
    conn.close()
    return dict(r) if r else None


def get_tag_by_name(name: str):
    conn = _connect()
    conn.row_factory = sqlite3.Row
    r = conn.execute('SELECT * FROM tags WHERE name_norm = ?',
                     (_norm_tag_name(name),)).fetchone()
    conn.close()
    return dict(r) if r else None


def update_tag(tag_id: str, name: str = None, color: str = None,
               kind: str = None, sort: int = None):
    if not get_tag(tag_id):
        raise ValueError(f'标签不存在：{tag_id}')
    conn = _connect()
    c = conn.cursor()
    sets, vals = [], []
    if name is not None:
        display = re.sub(r'\s+', '', (name or '').strip())
        nn = _norm_tag_name(display)
        if not nn:
            conn.close()
            raise ValueError('标签名不能为空')
        clash = c.execute('SELECT id FROM tags WHERE name_norm = ? AND id <> ?',
                          (nn, tag_id)).fetchone()
        if clash:
            conn.close()
            raise ValueError(f'标签名已存在：{display}')
        sets += ['name = ?', 'name_norm = ?']
        vals += [display, nn]
    if color is not None:
        sets.append('color = ?')
        vals.append(color)
    if kind is not None:
        sets.append('kind = ?')
        vals.append(kind)
    if sort is not None:
        sets.append('sort = ?')
        vals.append(sort)
    if sets:
        sets.append('updated_at = CURRENT_TIMESTAMP')
        vals.append(tag_id)
        c.execute('UPDATE tags SET ' + ', '.join(sets) + ' WHERE id = ?', vals)
        conn.commit()
    conn.close()
    return get_tag(tag_id)


def delete_tag(tag_id: str) -> dict:
    t = get_tag(tag_id)
    if not t:
        raise ValueError(f'标签不存在：{tag_id}')
    conn = _connect()
    c = conn.cursor()
    affected = c.execute('SELECT COUNT(*) FROM doc_tags WHERE tag_id = ?',
                         (tag_id,)).fetchone()[0]
    c.execute('DELETE FROM doc_tags WHERE tag_id = ?', (tag_id,))
    c.execute('DELETE FROM tags WHERE id = ?', (tag_id,))
    conn.commit()
    conn.close()
    return {'id': tag_id, 'name': t['name'], 'affected_docs': affected}


def _doc_tags_map(conn=None) -> dict:
    """一次查出全部文献的标签，避免 N+1"""
    own = conn is None
    conn = conn or _connect()
    conn.row_factory = sqlite3.Row
    rows = conn.execute('''
        SELECT dt.doc_id, t.id, t.name, t.kind, t.color
        FROM doc_tags dt JOIN tags t ON t.id = dt.tag_id
        ORDER BY t.sort, t.created_at
    ''').fetchall()
    out = {}
    for r in rows:
        out.setdefault(r['doc_id'], []).append({
            'id': r['id'], 'name': r['name'],
            'kind': r['kind'] or 'topic', 'color': r['color'] or TAG_PALETTE[0]
        })
    if own:
        conn.close()
    return out


def get_doc_tags(doc_id: str) -> list:
    return _doc_tags_map().get(doc_id, [])


def set_doc_tags(doc_id: str, names: list) -> list:
    """覆盖式设置某篇文献的标签（传名字数组；不存在的自动创建；状态类互斥只留最后一个）"""
    conn = _connect()
    c = conn.cursor()
    if not c.execute('SELECT 1 FROM docs WHERE id = ?', (doc_id,)).fetchone():
        conn.close()
        raise ValueError(f'文献不存在：{doc_id}')
    cleaned, seen = [], set()
    for n in (names or []):
        nn = _norm_tag_name(n)
        if not nn or nn in seen:
            continue
        seen.add(nn)
        cleaned.append(re.sub(r'\s+', '', str(n).strip()))
    pairs = []
    for display in cleaned:
        t = _ensure_tag(conn, display)
        pairs.append((t['id'], t['kind']))
    status_ids = [tid for tid, k in pairs if k == 'status']
    final = [tid for tid, k in pairs if k != 'status']
    if status_ids:
        final.append(status_ids[-1])
    c.execute('DELETE FROM doc_tags WHERE doc_id = ?', (doc_id,))
    c.executemany('INSERT OR IGNORE INTO doc_tags (doc_id, tag_id) VALUES (?, ?)',
                  [(doc_id, tid) for tid in final])
    conn.commit()
    conn.close()
    return get_doc_tags(doc_id)


def get_docs_by_tag(tag: str) -> list:
    """按标签（传 id 或名字都行）取文献 id 列表"""
    conn = _connect()
    c = conn.cursor()
    t = c.execute('SELECT id FROM tags WHERE id = ? OR name_norm = ?',
                  (tag, _norm_tag_name(tag))).fetchone()
    if not t:
        conn.close()
        return []
    rows = c.execute('SELECT doc_id FROM doc_tags WHERE tag_id = ?', (t[0],)).fetchall()
    conn.close()
    return [r[0] for r in rows]


# ============================================================
# knowledge（知识库：论断 + 可溯源来源）
# ============================================================

def _clean_tag_list(tags) -> list:
    out, seen = [], set()
    for t in (tags or []):
        s = re.sub(r'\s+', ' ', str(t)).strip()
        if not s:
            continue
        key = _norm_tag_name(s)
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out


def _row_to_knowledge(r) -> dict:
    return {
        'id': r['id'],
        'claim': r['claim'],
        'source_type': r['source_type'] or 'manual',
        'source_doc_id': r['source_doc_id'],
        'source_pid': r['source_pid'],
        'source_quote': r['source_quote'],
        'source_note_id': r['source_note_id'],
        'source_session_id': r['source_session_id'],
        'tags': json.loads(r['tags']) if r['tags'] else [],
        'project_id': r['project_id'],
        'status': r['status'] or 'active',
        'created_at': r['created_at'],
        'updated_at': r['updated_at'],
    }


def get_all_knowledge(tag: str = None, doc_id: str = None, project_id: str = None,
                      include_deleted: bool = False) -> list:
    conn = _connect()
    conn.row_factory = sqlite3.Row
    sql = 'SELECT * FROM knowledge WHERE 1 = 1'
    vals = []
    if not include_deleted:
        sql += " AND status = 'active'"
    if doc_id:
        sql += ' AND source_doc_id = ?'
        vals.append(doc_id)
    if project_id:
        sql += ' AND project_id = ?'
        vals.append(project_id)
    sql += ' ORDER BY created_at DESC'
    rows = conn.execute(sql, vals).fetchall()
    conn.close()
    out = [_row_to_knowledge(r) for r in rows]
    if tag:
        key = _norm_tag_name(tag)
        out = [k for k in out
               if any(_norm_tag_name(t) == key for t in (k['tags'] or []))]
    return out


def get_knowledge(kid: str):
    conn = _connect()
    conn.row_factory = sqlite3.Row
    r = conn.execute('SELECT * FROM knowledge WHERE id = ?', (kid,)).fetchone()
    conn.close()
    return _row_to_knowledge(r) if r else None


def create_knowledge(claim: str, source_type: str = 'manual', source_doc_id: str = None,
                     source_pid: int = None, source_quote: str = None,
                     source_note_id: str = None, source_session_id: str = None,
                     tags: list = None, project_id: str = None,
                     knowledge_id: str = None, dedupe: bool = True) -> dict:
    """新建知识条目。dedupe=True 时，同一来源重复收藏会走「更新」而不是再插一条。"""
    claim = (claim or '').strip()
    if not claim:
        raise ValueError('论断内容不能为空')
    conn = _connect()
    c = conn.cursor()
    if dedupe:
        row = None
        if source_note_id:
            row = c.execute(
                "SELECT id FROM knowledge WHERE source_note_id = ? AND status = 'active'",
                (source_note_id,)).fetchone()
        elif source_session_id:
            row = c.execute(
                "SELECT id FROM knowledge WHERE source_session_id = ? AND claim = ? "
                "AND status = 'active'", (source_session_id, claim)).fetchone()
        if row:
            conn.close()
            # 只覆盖「这次真正传了」的字段，避免重复收藏时把已有标签/溯源清掉
            upd = {'claim': claim}
            if tags:
                upd['tags'] = tags
            if source_quote:
                upd['source_quote'] = source_quote
            if source_pid:
                upd['source_pid'] = source_pid
            if source_doc_id:
                upd['source_doc_id'] = source_doc_id
            if project_id:
                upd['project_id'] = project_id
            return update_knowledge(row[0], **upd)
    kid = knowledge_id or ('kb_' + uuid.uuid4().hex[:8])
    c.execute(
        '''INSERT INTO knowledge (id, claim, source_type, source_doc_id, source_pid,
           source_quote, source_note_id, source_session_id, tags, project_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        (kid, claim, source_type or 'manual', source_doc_id, source_pid,
         source_quote, source_note_id, source_session_id,
         json.dumps(_clean_tag_list(tags), ensure_ascii=False) if tags else None,
         project_id)
    )
    conn.commit()
    conn.close()
    return get_knowledge(kid)


def update_knowledge(kid: str, claim: str = None, tags: list = None,
                     project_id: str = None, source_quote: str = None,
                     source_pid: int = None, source_doc_id: str = None) -> dict:
    if not get_knowledge(kid):
        raise ValueError(f'知识条目不存在：{kid}')
    conn = _connect()
    c = conn.cursor()
    sets, vals = [], []
    if claim is not None:
        claim = claim.strip()
        if not claim:
            conn.close()
            raise ValueError('论断内容不能为空')
        sets.append('claim = ?')
        vals.append(claim)
    if tags is not None:
        sets.append('tags = ?')
        vals.append(json.dumps(_clean_tag_list(tags), ensure_ascii=False))
    if project_id is not None:
        sets.append('project_id = ?')
        vals.append(project_id)
    if source_quote is not None:
        sets.append('source_quote = ?')
        vals.append(source_quote)
    if source_pid is not None:
        sets.append('source_pid = ?')
        vals.append(source_pid)
    if source_doc_id is not None:
        sets.append('source_doc_id = ?')
        vals.append(source_doc_id)
    if sets:
        # SQLite 的 DEFAULT CURRENT_TIMESTAMP 只在 INSERT 生效，UPDATE 必须显式写
        sets.append('updated_at = CURRENT_TIMESTAMP')
        vals.append(kid)
        c.execute('UPDATE knowledge SET ' + ', '.join(sets) + ' WHERE id = ?', vals)
        conn.commit()
    conn.close()
    return get_knowledge(kid)


def soft_delete_knowledge(kid: str) -> dict:
    if not get_knowledge(kid):
        raise ValueError(f'知识条目不存在：{kid}')
    conn = _connect()
    conn.execute("UPDATE knowledge SET status = 'deleted', "
                 "updated_at = CURRENT_TIMESTAMP WHERE id = ?", (kid,))
    conn.commit()
    conn.close()
    return {'status': 'deleted', 'id': kid}
