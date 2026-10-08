# 附录 A：数据结构

版本：v0.7
日期：2026-09-27
所属：文献管理助手 PRD
主文档：[PRD_v0.7.md](../PRD_v0.7.md)

---

> 本附录定义全部数据结构。A.1–A.23 为原始定义，A.24–A.29 为 v0.7 从主文档 9.16–9.21 并入的模块字段定义。

## A.0 四个库

本系统有四个库，各管各的，不要混淆：

| 库 | 装什么 | 用途 | 路径 |
|---|---|---|---|
| **文献库** | 上传的原文 | 保存原始文件 | `data/literature_meta/` |
| **分段库** | 分段后的片段 + 向量 | 用于检索 | `data/chunks/`（或 Dify 内部） |
| **笔记库** | 所有笔记（默认） | 沉淀、总览 | `data/note_snapshots/` |
| **知识库** | 被收藏的论断 + 来源 | 复用、驱动问答/综述 | `data/qa_knowledge.json` |

**关键**：
- 「知识库」只留给收藏的论断，不装文献
- Dify 把「分段库」叫「知识库」，是它的问题
- 本 PRD 里，「知识库」= 收藏的论断

**知识库里的六类知识单元**：

| 类型 | 来源 |
|---|---|
| 问答知识 | 收藏的问答答案 |
| 笔记知识 | 收藏的笔记 |
| 速读知识 | 收藏的速读字段 |
| 综述知识 | 收藏的综述论点 |
| 术语知识 | 收藏的术语卡片 |
| 模型知识 | 收藏的模型卡片 |

**进知识库三条件**：可复用、可追溯、可组合。

---

## A.1 数据存储总览
所有数据存本地 `data/` 目录，不上传。

```
data/
├── users/                    # 用户目录
│   ├── users.json            # 用户注册表
│   └── <user>/               # 各用户数据
├── literature_meta/          # 文献元数据
│   └── lit_XXX.json
├── note_snapshots/           # 笔记 / 划线快照
│   └── lit_XXX.json
├── notes_index.json          # 笔记总索引
├── qa_history.json           # 问答历史
├── qa_knowledge.json         # 知识库（收藏知识条目）
├── reading_log.json          # 阅读进度
├── translate_queue.json      # 翻译队列
├── translate_jobs/           # 翻译作业文件
│   └── job_<doc>_p<pid>.txt
├── note_queue.json           # 笔记队列（预留）
├── highlight_queue.json      # 划线队列（预留）
├── tags.json                 # 标签注册表
├── usage_log.json            # API 用量
├── api_status.json           # API 状态
└── .purged/                  # 彻底删除隔离区
```

---

## A.2 文献元数据

**路径**：`data/literature_meta/lit_XXX.json`

**结构**：

```json
{
  "doc_id": "lit_001",
  "title": "论文标题",
  "authors": ["作者1", "作者2"],
  "year": 2024,
  "venue": "期刊 / 会议",
  "source": "pdf | txt | md | arxiv",
  "source_url": "https://arxiv.org/abs/2401.00100",
  "md5": "文件指纹",
  "status": "unread | read",
  "deleted": false,
  "deleted_at": null,
  "tags": ["方法", "实验"],
  "chunks": [
    {
      "pid": 1,
      "section": "1. 引言",
      "text": "段落原文",
      "translation": "译文（可选）"
    }
  ],
  "notes": [
    {
      "note_id": "note_001",
      "pid": 3,
      "versions": [
        {
          "version": "v1",
          "created_at": "2026-09-01T14:30:00",
          "content": "笔记内容",
          "status": "active"
        }
      ],
      "current_version": "v1",
      "related_notes": [],
      "status": "active"
    }
  ],
  "translations": {
    "3": "第3段译文",
    "5": "第5段译文"
  },
  "created_at": "2026-09-01T10:00:00",
  "updated_at": "2026-09-10T20:45:00"
}
```

---

## A.3 笔记版本链

**位置**：`literature_meta/lit_XXX.json` 的 `notes` 字段

**结构**：

```json
{
  "note_id": "note_001",
  "pid": 12,
  "current_version": "v3",
  "versions": [
    {
      "version": "v1",
      "created_at": "2026-09-01T14:30:00",
      "content": "这个方法像 Transformer",
      "status": "active"
    },
    {
      "version": "v2",
      "created_at": "2026-09-05T09:12:00",
      "content": "其实就是 Transformer 的变体",
      "status": "active"
    },
    {
      "version": "v3",
      "created_at": "2026-09-10T20:45:00",
      "content": "但训练目标不同",
      "status": "active"
    }
  ],
  "related_notes": ["note_002"],
  "status": "active"
}
```

**关键字段**：

| 字段 | 类型 | 说明 |
|---|---|---|
| `note_id` | string | 笔记 ID，格式 `note_XXX` |
| `pid` | number | 段落号 |
| `current_version` | string | 当前显示版本 |
| `versions` | array | 版本链，只追加不覆盖 |
| `versions[].version` | string | 版本号 |
| `versions[].created_at` | string | 版本创建时间 |
| `versions[].content` | string | 版本内容 |
| `versions[].status` | string | `active` / `deleted` |
| `related_notes` | array | 同一段落的关联笔记 |
| `status` | string | 整条笔记状态 |

---

## A.4 笔记快照

**路径**：`data/note_snapshots/lit_XXX.json`

**结构**：

```json
{
  "doc_id": "lit_001",
  "updated_at": "2026-09-10T20:45:00",
  "notes": [
    {
      "note_id": "note_001",
      "pid": 3,
      "type": "note | hl | hl-sent",
      "content": "笔记内容 或 划线文本",
      "sentences": ["句子1", "句子2"],
      "created_at": "2026-09-01T14:30:00",
      "updated_at": "2026-09-10T20:45:00"
    }
  ]
}
```

**关键字段**：

| 字段 | 类型 | 说明 |
|---|---|---|
| `doc_id` | string | 文献 ID |
| `updated_at` | string | 快照更新时间 |
| `notes` | array | 笔记 + 划线列表 |
| `notes[].type` | string | `note` / `hl`（整段划线）/ `hl-sent`（句子划线） |
| `notes[].sentences` | array | 句子级划线文本 |

**权威性**：快照是权威版本，localStorage 只是缓存，冲突以快照为准。

---

## A.5 笔记总索引

**路径**：`data/notes_index.json`

**结构**：

```json
{
  "version": 1,
  "notes": [
    {
      "note_id": "note_001",
      "doc_id": "lit_001",
      "pid": 3,
      "section": "3.2",
      "content": "笔记内容",
      "created_at": "2026-09-01T14:30:00",
      "updated_at": "2026-09-10T20:45:00"
    }
  ]
}
```

**用途**：跨文献检索、综述时对照「我当时的看法」。

---

## A.6 问答历史

**路径**：`data/qa_history.json`

**结构**：

```json
{
  "version": 1,
  "history": [
    {
      "qid": "qa_001",
      "question": "问题",
      "answer": "答案",
      "mode": "single | cross | docs",
      "doc": "lit_001",
      "docs": ["lit_001", "lit_006"],
      "sources": [
        {
          "doc_id": "lit_001",
          "pid": 12,
          "location": "3.2节第2段",
          "snippet": "原文片段"
        }
      ],
      "from_kb": false,
      "favorite": false,
      "kid": null,
      "created_at": "2026-09-10T20:45:00"
    }
  ]
}
```

**关键字段**：

| 字段 | 类型 | 说明 |
|---|---|---|
| `qid` | string | 问答 ID |
| `question` | string | 问题 |
| `answer` | string | 答案 |
| `mode` | string | `single` / `cross` / `docs` |
| `doc` | string | 单篇问答的文献 ID |
| `docs` | array | 多篇定向问答的文献 ID |
| `sources` | array | 来源列表 |
| `from_kb` | boolean | 是否来自知识库 |
| `favorite` | boolean | 是否收藏 |
| `kid` | string | 关联的知识条目 ID |
| `created_at` | string | 创建时间 |

---

## A.7 知识库

**路径**：`data/qa_knowledge.json`

**结构**：

```json
{
  "version": 1,
  "knowledge": [
    {
      "kid": "kb_001",
      "claim": "RAG 适合知识更新频繁的场景",
      "source": {
        "doc_id": "lit_003",
        "pid": 12,
        "section": "3.2",
        "quote": "原文片段"
      },
      "type": "qa | note | summary | review | term | comparison",
      "tags": ["RAG", "知识更新"],
      "related": ["kb_002"],
      "created_at": "2026-09-10T20:45:00",
      "updated_at": "2026-09-10T20:45:00"
    }
  ]
}
```

**关键字段**：

| 字段 | 类型 | 说明 |
|---|---|---|
| `kid` | string | 知识条目 ID |
| `claim` | string | 论断 |
| `source` | object | 来源（文献 / 段落 / 引用） |
| `type` | string | 来源类型 |
| `tags` | array | 标签 |
| `related` | array | 关联知识条目 |
| `created_at` | string | 创建时间 |
| `updated_at` | string | 更新时间 |

**知识定义**：可复用、可追溯、可组合的论断 + 来源。

---

## A.8 用户注册表

**路径**：`data/users/users.json`

**结构**：

```json
{
  "version": 1,
  "current_user": "default",
  "users": [
    {
      "user_id": "default",
      "name": "默认用户",
      "created_at": "2026-09-22T10:00:00",
      "data_dir": "data/users/default"
    }
  ]
}
```

**关键字段**：

| 字段 | 类型 | 说明 |
|---|---|---|
| `current_user` | string | 当前用户 ID |
| `users` | array | 用户列表 |
| `users[].user_id` | string | 用户 ID |
| `users[].name` | string | 用户名 |
| `users[].created_at` | string | 创建时间 |
| `users[].data_dir` | string | 数据目录 |

---

## A.9 用户目录结构

```
data/
├── users/
│   ├── users.json          # 用户注册表
│   ├── default/            # 默认用户数据
│   │   ├── literature_meta/
│   │   ├── note_snapshots/
│   │   ├── qa_history.json
│   │   ├── qa_knowledge.json
│   │   ├── reading_log.json
│   │   ├── projects/
│   │   └── ...
│   └── user_002/           # 第二个用户
│       └── ...
```

**规则**：每个用户独立目录，切换用户 = 切换 `data_dir`。

---

## A.10 项目元数据

**路径**：`data/users/<user>/projects/<project_id>.json`

**结构**：

```json
{
  "project_id": "proj_001",
  "name": "我的论文 XXX",
  "description": "...",
  "docs": ["lit_001", "lit_002", "lit_003"],
  "notes": ["note_001", "note_002"],
  "knowledge": ["kb_001"],
  "reviews": ["review_001"],
  "status": "active | archived",
  "created_at": "2026-09-22T10:00:00",
  "updated_at": "2026-09-22T20:45:00"
}
```

**关键字段**：

| 字段 | 类型 | 说明 |
|---|---|---|
| `project_id` | string | 项目 ID |
| `name` | string | 项目名 |
| `docs` | array | 项目内文献 ID |
| `notes` | array | 项目笔记 ID |
| `knowledge` | array | 项目知识条目 ID |
| `reviews` | array | 项目综述 ID |
| `status` | string | `active` / `archived` |

**规则**：项目只是引用，不复制文献；移除 ≠ 删除。

---

## A.11 模型卡片

**路径**：`data/cards/models.json`

**结构**：

```json
{
  "version": 1,
  "cards": [
    {
      "card_id": "model_001",
      "name": "BERT",
      "type": "预训练语言模型",
      "source": {
        "doc_id": "lit_003",
        "pid": 5,
        "quote": "we use BERT as the encoder"
      },
      "core_idea": "双向 Transformer 编码器",
      "related_docs": ["lit_003", "lit_007"],
      "related_terms": ["Transformer", "Self-Attention"],
      "origin": "literature | builtin | user_import"
    }
  ]
}
```

**关键字段**：

| 字段 | 类型 | 说明 |
|---|---|---|
| `card_id` | string | 卡片 ID |
| `name` | string | 模型名 |
| `type` | string | 模型类型 |
| `source` | object | 来源（文献 / 段落 / 引用） |
| `core_idea` | string | 核心思想 |
| `related_docs` | array | 相关文献 |
| `related_terms` | array | 相关术语 |
| `origin` | string | 来源层级 |

---

## A.12 术语卡片

**路径**：`data/cards/terms.json`

**结构**：

```json
{
  "version": 1,
  "cards": [
    {
      "card_id": "term_001",
      "term": "Attention",
      "translation": "注意力机制",
      "explanation": "...",
      "source": {
        "doc_id": "lit_003",
        "pid": 5,
        "quote": "..."
      },
      "related_terms": ["Transformer", "Self-Attention"],
      "origin": "literature | builtin | user_import"
    }
  ]
}
```

**关键字段**：

| 字段 | 类型 | 说明 |
|---|---|---|
| `card_id` | string | 卡片 ID |
| `term` | string | 术语 |
| `translation` | string | 译名 |
| `explanation` | string | 解释 |
| `source` | object | 来源 |
| `related_terms` | array | 相关术语 |
| `origin` | string | 来源层级 |

---

## A.13 内置术语库 / 模型库

**路径**：`data/builtin/terms.json` / `data/builtin/models.json`

**结构**：

```json
{
  "version": 1,
  "type": "term | model",
  "entries": [
    {
      "term": "Attention",
      "translation": "注意力机制",
      "explanation": "...",
      "source": "builtin",
      "related_terms": ["Transformer", "Self-Attention"]
    }
  ]
}
```

**关键字段**：

| 字段 | 类型 | 说明 |
|---|---|---|
| `type` | string | `term` / `model` |
| `entries` | array | 条目列表 |
| `source` | string | `builtin` |

**规则**：内置库只读，用户可禁用，不可修改。

---

## A.14 用户导入库

**路径**：`data/users/<user>/user_libraries/terms.json` / `models.json`

**结构**：与内置库一致，`source` 改为 `user_import`。

**规则**：用户负责来源，助手不保证准确。

## A.15 阅读进度

**路径**：`data/reading_log.json`

**结构**：

```json
{
  "version": 1,
  "sessions": [
    {
      "id": "session_001",
      "doc": "lit_001",
      "start": "2026-09-10T20:00:00",
      "end": "2026-09-10T20:30:00",
      "last_pid": 12,
      "duration": 1800,
      "updated_at": "2026-09-10T20:30:00"
    }
  ]
}
```

**关键字段**：

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | string | 会话 ID |
| `doc` | string | 文献 ID |
| `start` | string | 开始时间 |
| `end` | string | 结束时间 |
| `last_pid` | number | 最后停留段落 |
| `duration` | number | 停留时长（秒） |
| `updated_at` | string | 最后更新时间 |

**规则**：
- 刷新 30 分钟内延续同一 session
- `duration` 只累计「页面可见 + 有活动」的时间
- `duration < 10` 不算阅读

---

## A.16 翻译队列

**路径**：`data/translate_queue.json`

**结构**：

```json
{
  "version": 1,
  "queue": [
    {
      "doc": "lit_001",
      "pid": 3,
      "text": "原文",
      "glossary": ["术语1", "术语2"],
      "status": "pending | processing | done | failed",
      "reason": null,
      "created_at": "2026-09-10T20:45:00"
    }
  ]
}
```

**状态流转**：

```
pending → processing → done
                    ↘ failed
```

---

## A.17 翻译作业文件

**路径**：`data/translate_jobs/job_<doc>_p<pid>.txt`

**内容**：

```
原文：
...

术语表：
- term1: 释义1
- term2: 释义2

命令：
python scripts/knowledge_base.py translate --doc lit_001 --pid 3 --text-file data/_zh_lit_001_p3.txt --auto-glossary
```

---

## A.18 标签注册表

**路径**：`data/tags.json`

**结构**：

```json
{
  "version": 1,
  "tags": {
    "方法": {"color": 1},
    "实验": {"color": 2}
  }
}
```

**用途**：标签颜色映射，工作台筛选。

---

## A.19 API 用量

**路径**：`data/usage_log.json`

**结构**：

```json
{
  "version": 1,
  "usage": {
    "2026-09-10": {
      "calls": 12,
      "input_tokens": 15000,
      "output_tokens": 8000,
      "cost_usd": 0.35
    }
  }
}
```

**规则**：按日期分桶，新的一天自动重置。

---

## A.20 API 状态

**路径**：`data/api_status.json`

**结构**：

```json
{
  "mode": "api | manual | budget_exhausted",
  "recent_ok": true,
  "reason": null,
  "updated_at": "2026-09-10T20:45:00"
}
```

**用途**：阅读页提示自动翻译 / 降级 / 失败。

---

## A.21 队列修剪规则

| 队列 | 保留 | 说明 |
|---|---|---|
| `translate_queue` | 消费后即清 | Worker 消费清除 |
| `translate_jobs` | 消费后即删 | 写回译文后删除 |
| `note_queue` | 72 小时 / 200 条 | 预留，自动修剪 |
| `highlight_queue` | 72 小时 / 200 条 | 预留，自动修剪 |
| `usage_log` | 长期保留 | 不自动清理 |
| `reading_log` | 长期保留 | 不自动清理 |
| `qa_history` | 长期保留 | 不自动清理 |

---

## A.22 软删除语义

| 操作 | 行为 |
|---|---|
| `delete` | 打 `deleted:true` + `deleted_at`，文件 / 笔记 / 问答 / 划线全保留 |
| `restore` | 去掉标记，文献及全部关联数据回来 |
| `purge` | 先打印影响清单，二次确认后级联删除 |
| purge 失败 | 隔离到 `data/.purged/`，报 `quarantined_files` |

**软删除后**：
- `list` / `search` / `ask` / `qa --match` 自动排除
- 问答历史来源卡显示「原文已删除」
- Agent 不再引用该文献原文

---

## A.23 知识定义

**知识 = 可复用、可追溯、可组合的论断 + 来源。**

| 条件 | 说明 |
|---|---|
| 可复用 | 不只服务一次问答，以后还能用 |
| 可追溯 | 能点回原文 / 来源 |
| 可组合 | 能和其他知识单元一起支撑综述、写作、问答 |

**能进知识库**：问答答案、笔记、速读字段、综述论点、术语、对比结论。
**不能进知识库**：纯对话、原始 PDF。
---

---

## A.24 – A.29 补充结构定义

> 来源：PRD v0.6 第 9.16–9.21 节中的字段定义部分，于 v0.7 整理时并入本附录。

## A.24 知识单元结构

```json
{
  "kid": "kb_001",
  "claim": "RAG 适合知识更新频繁的场景",
  "source": {
    "doc_id": "lit_003",
    "pid": 12,
    "section": "3.2",
    "quote": "原文片段"
  },
  "type": "qa | note | summary | review | term | comparison",
  "created_at": "2026-09-10T20:45:00",
  "tags": ["RAG", "知识更新"],
  "related": ["kb_002", "kb_005"]
}
```

---

## A.25 知识库三层结构

```
知识单元（最小单位：论断 + 来源 + 时间 + 标签）
  ↑
知识集合（按主题 / 文献 / 标签组织）
  ↑
知识库（全局，可检索、可复用）
```

---

## A.26 卡片结构

**模型卡片**：

```json
{
  "card_id": "model_001",
  "name": "BERT",
  "type": "预训练语言模型",
  "source": {
    "doc_id": "lit_003",
    "pid": 5,
    "quote": "we use BERT as the encoder"
  },
  "core_idea": "双向 Transformer 编码器",
  "related_docs": ["lit_003", "lit_007"],
  "related_terms": ["Transformer", "Self-Attention"],
  "origin": "literature | user_import"
}
```

**术语卡片**：

```json
{
  "card_id": "term_001",
  "term": "Attention",
  "translation": "注意力机制",
  "explanation": "...",
  "source": {
    "doc_id": "lit_003",
    "pid": 5,
    "quote": "..."
  },
  "related_terms": ["Transformer", "Self-Attention"],
  "origin": "literature | user_import"
}
```

---

## A.27 数据结构

**内置术语库**：`data/builtin/terms.json`

```json
{
  "version": 1,
  "type": "term",
  "entries": [
    {
      "term": "Attention",
      "translation": "注意力机制",
      "explanation": "...",
      "source": "builtin",
      "related_terms": ["Transformer", "Self-Attention"]
    }
  ]
}
```
**内置模型库**：`data/builtin/models.json`

```json
{
  "version": 1,
  "type": "model",
  "entries": [
    {
      "name": "BERT",
      "type": "预训练语言模型",
      "core_idea": "双向 Transformer 编码器",
      "source": "builtin",
      "related_terms": ["Transformer", "Self-Attention"]
    }
  ]
}
```

---

## A.28 数据结构

**项目元数据**：`data/projects/<project_id>.json`

```json
{
  "project_id": "proj_001",
  "name": "我的论文 XXX",
  "description": "...",
  "docs": ["lit_001", "lit_002", "lit_003"],
  "notes": ["note_001", "note_002"],
  "knowledge": ["kb_001"],
  "reviews": ["review_001"],
  "status": "active | archived",
  "created_at": "2026-09-22T10:00:00",
  "updated_at": "2026-09-22T20:45:00"
}
```
**关键字段**：

| 字段 | 类型 | 说明 |
|---|---|---|
| `project_id` | string | 项目 ID |
| `name` | string | 项目名 |
| `docs` | array | 项目内文献 ID |
| `notes` | array | 项目笔记 ID |
| `knowledge` | array | 项目知识条目 ID |
| `reviews` | array | 项目综述 ID |
| `status` | string | `active` / `archived` |

---

## A.29 数据结构

```
data/
├── users/
│ ├── users.json # 用户注册表
│ ├── default/ # 默认用户数据
│ │ ├── literature_meta/
│ │ ├── note_snapshots/
│ │ ├── qa_history.json
│ │ ├── qa_knowledge.json
│ │ ├── reading_log.json
│ │ └── ...
│ └── user_002/ # 第二个用户
│ └── ...

```

`users.json`：

```json
{
  "version": 1,
  "current_user": "default",
  "users": [
    {
      "user_id": "default",
      "name": "默认用户",
      "created_at": "2026-09-22T10:00:00",
      "data_dir": "data/users/default"
    }
  ]
}
```

**关键字段**：

| 字段 | 类型 | 说明 |
|---|---|---|
| `current_user` | string | 当前用户 ID |
| `users` | array | 用户列表 |
| `users[].user_id` | string | 用户 ID |
| `users[].name` | string | 用户名 |
| `users[].created_at` | string | 创建时间 |
| `users[].data_dir` | string | 数据目录 |

---

---

## A.24 – A.29 补充结构定义

> 来源：PRD v0.6 第 9.16–9.21 节中的字段定义部分，于 v0.7 整理时并入本附录。

## A.24 知识单元结构

```json
{
  "kid": "kb_001",
  "claim": "RAG 适合知识更新频繁的场景",
  "source": {
    "doc_id": "lit_003",
    "pid": 12,
    "section": "3.2",
    "quote": "原文片段"
  },
  "type": "qa | note | summary | review | term | comparison",
  "created_at": "2026-09-10T20:45:00",
  "tags": ["RAG", "知识更新"],
  "related": ["kb_002", "kb_005"]
}
```

---

## A.25 知识库三层结构

```
知识单元（最小单位：论断 + 来源 + 时间 + 标签）
  ↑
知识集合（按主题 / 文献 / 标签组织）
  ↑
知识库（全局，可检索、可复用）
```

---

## A.26 卡片结构

**模型卡片**：

```json
{
  "card_id": "model_001",
  "name": "BERT",
  "type": "预训练语言模型",
  "source": {
    "doc_id": "lit_003",
    "pid": 5,
    "quote": "we use BERT as the encoder"
  },
  "core_idea": "双向 Transformer 编码器",
  "related_docs": ["lit_003", "lit_007"],
  "related_terms": ["Transformer", "Self-Attention"],
  "origin": "literature | user_import"
}
```

**术语卡片**：

```json
{
  "card_id": "term_001",
  "term": "Attention",
  "translation": "注意力机制",
  "explanation": "...",
  "source": {
    "doc_id": "lit_003",
    "pid": 5,
    "quote": "..."
  },
  "related_terms": ["Transformer", "Self-Attention"],
  "origin": "literature | user_import"
}
```

---

## A.27 数据结构

**内置术语库**：`data/builtin/terms.json`

```json
{
  "version": 1,
  "type": "term",
  "entries": [
    {
      "term": "Attention",
      "translation": "注意力机制",
      "explanation": "...",
      "source": "builtin",
      "related_terms": ["Transformer", "Self-Attention"]
    }
  ]
}
```
**内置模型库**：`data/builtin/models.json`

```json
{
  "version": 1,
  "type": "model",
  "entries": [
    {
      "name": "BERT",
      "type": "预训练语言模型",
      "core_idea": "双向 Transformer 编码器",
      "source": "builtin",
      "related_terms": ["Transformer", "Self-Attention"]
    }
  ]
}
```

---

## A.28 数据结构

**项目元数据**：`data/projects/<project_id>.json`

```json
{
  "project_id": "proj_001",
  "name": "我的论文 XXX",
  "description": "...",
  "docs": ["lit_001", "lit_002", "lit_003"],
  "notes": ["note_001", "note_002"],
  "knowledge": ["kb_001"],
  "reviews": ["review_001"],
  "status": "active | archived",
  "created_at": "2026-09-22T10:00:00",
  "updated_at": "2026-09-22T20:45:00"
}
```
**关键字段**：

| 字段 | 类型 | 说明 |
|---|---|---|
| `project_id` | string | 项目 ID |
| `name` | string | 项目名 |
| `docs` | array | 项目内文献 ID |
| `notes` | array | 项目笔记 ID |
| `knowledge` | array | 项目知识条目 ID |
| `reviews` | array | 项目综述 ID |
| `status` | string | `active` / `archived` |

---

## A.29 数据结构

```
data/
├── users/
│ ├── users.json # 用户注册表
│ ├── default/ # 默认用户数据
│ │ ├── literature_meta/
│ │ ├── note_snapshots/
│ │ ├── qa_history.json
│ │ ├── qa_knowledge.json
│ │ ├── reading_log.json
│ │ └── ...
│ └── user_002/ # 第二个用户
│ └── ...

```

`users.json`：

```json
{
  "version": 1,
  "current_user": "default",
  "users": [
    {
      "user_id": "default",
      "name": "默认用户",
      "created_at": "2026-09-22T10:00:00",
      "data_dir": "data/users/default"
    }
  ]
}
```

**关键字段**：

| 字段 | 类型 | 说明 |
|---|---|---|
| `current_user` | string | 当前用户 ID |
| `users` | array | 用户列表 |
| `users[].user_id` | string | 用户 ID |
| `users[].name` | string | 用户名 |
| `users[].created_at` | string | 创建时间 |
| `users[].data_dir` | string | 数据目录 |

---
