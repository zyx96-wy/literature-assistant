# 数据流：前端和后端的分工

## 核心原则

前端和后端处理文档的方式**刻意不同**，因为目的不同：

| | 后端 | 前端 |
|---|---|---|
| 目的 | RAG 检索召回 | 人眼阅读 |
| 分段 | `split_for_rag`，可句中切、可重叠 | `split_for_reading`，整句、不重叠 |
| 存储 | Chroma 向量库 | SQLite `paragraphs` 字段 |
| 编号 | 无 | ¶N（段落号，用于溯源） |

## 数据流图

PDF 上传
  ↓
parse_pdf（按坐标分栏，双栏不串行）
  ↓
  ├─ split_for_rag → Chroma 向量库 → 问答检索用
  │
  └─ split_for_reading → SQLite paragraphs → 阅读页渲染用
                          ↓
  





**关键点**：
- `parse_pdf` 只调用一次，两条路共用全文
- `split_for_rag` 的产物**只进 Chroma**，前端永远不读它
- `split_for_reading` 的产物**只进 SQLite**，检索永远不读它
- `deep_parse` 同时用全文和阅读段落：全文给 LLM 看，阅读段落给 quote 校验用

---

## 3. 存储分工

| 存储 | 存什么 | 谁写 | 谁读 |
|---|---|---|---|
| Chroma `chroma_db/` | RAG 检索块 + 向量 | `/api/upload` | `/api/ask` |
| SQLite `docs` 表 | 文档元数据 + 全文 + 阅读段落 + 深解析字段 | `/api/upload` | `/api/docs`、`/api/docs/{id}` |
| SQLite `notes` 表 | 笔记（版本链） | **（尚无 API）** | **（尚无 API）** |
| `data/raw/` | 原始 PDF | `/api/upload` | `resegment.py`、`redeep.py` |

**注意 `notes` 表**：表结构已经建好（`database.py` 的 `init_db`），但**没有任何 API 读写它**。前端笔记用的是内存数组 `DB.notes`，刷新就丢。

---

## 4. 功能真实性对照表

判断标准：

- **真** = 数据从 PDF 来，经过解析，落到存储，前端或后端有一方在用
- **半真** = 数据源是真的，但展示形式是前端拼装
- **假** = 页面上显示的内容和任何 PDF 无关，是代码里手写的字符串
- **未实现** = 前后端都没有

### 4.1 真的（数据链路完整）

| 功能 | 前端 | 后端 | 数据源 | 说明 |
|---|---|---|---|---|
| 文献上传 | `uploadDoc()` | `POST /api/upload` | PDF → Chroma + SQLite | 完整链路 |
| 文献列表 | `loadDocsFromAPI()` | `GET /api/docs` | SQLite `docs` | 完整链路 |
| 阅读页 | `renderReader()` | `GET /api/docs/{id}` | SQLite `paragraphs` | 读的是 `split_for_reading` 结果 |
| 速读页 | `renderSummary()` | `GET /api/docs/{id}` | SQLite `fields` | 读的是 `deep_parse` 结果 |
| 问答 | `sendMsg()` | `POST /api/ask` | Chroma 检索 | 多路检索 + 范围过滤 |
| 拖拽限定范围 | `qaScope` | `scope` 参数 | — | 亮牌范围 == 实际检索范围 |
| 字段溯源 | `renderSummary()` | `deep_parse` | SQLite `fields.quote` | quote 逐字校验，`verified` 标记 |

### 4.2 半真（真数据 + 前端拼装）

| 功能 | 数据源 | 拼装方式 | 说明 |
|---|---|---|---|
| 组会面板 | `d.fields` 的核心方法/关键步骤/创新点 | 前端 `renderMeetingPanel()` 拼 | 数据真，展示形式是拼的 |
| 复现清单 | `d.fields` 的实验设置/评估指标/局限性 | 前端 `REPRO_MAP` 映射 | 数据真，映射规则是前端定的 |

**这两个不算假**，因为数据源是 `deep_parse` 的真实产出。但要在 UI 上标清楚「内容来自深解析字段，未做补全」。

### 4.3 假的（页面显示与 PDF 无关）

| 功能 | 假在哪 | 应该怎么改 |
|---|---|---|
| 单篇球球问答 | `cbSend()` 答案写死「We use BERT as the encoder...」 | 改成调 `/api/ask`，scope=当前 doc |
| 项目问答 | `projAsk()` 答案写死 | 改成调 `/api/ask`，scope=项目内 doc_ids |
| 综述生成 | `runReview()` 论点 1/2/3 写死，`lit_001 ¶3` 是编的 | 要么接后端，要么 UI 标注「Demo 演示」 |
| 对比分析 | `runCompare()` 表格写死 | 同上 |
| 查词 | `cardData` 只有 3 个词条写死 | 接术语库，或标注「示例」 |
| 笔记 CRUD | `DB.notes` 内存数组 | 接 `notes` 表的 API |
| 知识库 | `DB.knowledge` 内存数组 | 新建表 + API |
| 项目 | `DB.projects` 内存数组 | 新建表 + API |
| 标签 | `DB.docs.tags` 内存字段 | 新建表 + API |
| 软删/恢复 | `softDelete()` 只改内存 | 接 `/api/docs/{id}/delete` |

### 4.4 未实现

| 功能 | PRD 位置 | 说明 |
|---|---|---|
| 多轮对话 | 9.4 | `/ask` 无 `session_id`，无 history |
| Agent tool calling | 19.13 | Dify 里的 AGENT 节点未配置策略 |
| 综述引用密度 / 争议标注 | 7.1 | 后端无实现 |
| 桥接服务 | 9.15 | 无 |
| 翻译队列 | 9.7 | 无 |
| 用户体系 | 9.21 | 无 |

---

## 5. 三条数据链路（面试时重点讲）

### 链路一：上传 → 阅读（前端真）
 
用户上传 PDF
→ parse_pdf 按坐标分栏
→ split_for_reading 整句分段
→ 存 SQLite paragraphs
→ 前端 renderReader 渲染 ¶N
→ 用户划选 → 笔记锚定到 ¶N
deep_parse → SQLite fields → 速读页/组会/复现用


**证明什么**：你懂「阅读段落不能句中切」这个约束，并且实现了双栏 PDF 的正确解析。

### 链路二：上传 → 检索（后端真）
用户上传 PDF
→ parse_pdf 同一份全文
→ split_for_rag 切碎 + 重叠
→ 进 Chroma 向量库
→ 用户提问 → multi_retrieval 多路召回
→ 过滤 References + 去重
→ LLM 生成答案


**证明什么**：你懂 RAG 检索块和阅读段的区别，并且实现了多路检索（对应 PRD 附录 F 的发现 F1）。

### 链路三：上传 → 深解析（溯源真）

用户上传 PDF
→ parse_pdf 同一份全文
→ split_for_reading 得到带 ¶N 的段落
→ deep_parse 按段落编号喂 LLM
→ LLM 返回 {text, pid, quote}
→ Python 侧归一化后逐字比对 quote
→ 命中 → verified=true，落库
→ 未命中 → verified=false，不伪装


**证明什么**：你懂「引用必须可追溯」，并且实现了逐字校验 + 三级回退定位（精确→邻近±2段→全文）。

---

## 6. 已知问题（诚实清单）

| # | 问题 | 影响 | 优先级 |
|---|---|---|---|
| 1 | `SEED_DOCS` 离线示例与真实数据混在同一屏 | 面试官可能误以为是真实数据 | P0 |
| 2 | 前端笔记/知识库/项目/标签全是内存数组 | 刷新即丢，后端表存在但无 API | P0 |
| 3 | 综述/对比/球球/项目问答写死 | 页面看起来像真的，实际是假的 | P0 |
| 4 | `notes` 表已建但无 API | 前端有完整 UI，后端空着 | P1 |
| 5 | 多轮对话完全未实现 | 五个能力标签之一为空 | P1 |
| 6 | Dify 工作流意图分类（6 类）与 PRD（5 类）不一致 | 面试会被问 | P1 |
| 7 | `core/` 旧代码未删 | 面试官会问「为什么有两套」 | P1 |
| 8 | `settings.py` 的 `CHUNK_OVERLAP=50`、`RETRIEVAL_K=4` 与 PRD（80、8）不一致 | 数字对不上 | P1 |
| 9 | Dify API Key 硬编码在 `test_eval.py` | 安全风险 | P0（立即处理） |
| 10 | 段落文本未转义（`renderReader` 的 `${p}`） | XSS 风险 | P2 |

---

## 7. 下一步（按优先级）

1. **吊销 `test_eval.py` 里泄露的 Dify Key**
2. **处理 `SEED_DOCS`**：删除，或加明显「离线示例」标识
3. **写 `notes` 表的 API**（`GET/POST/PUT/DELETE /api/notes`），让前端笔记落库
4. **把写死的功能标注清楚**：综述/对比/球球/项目问答，要么接后端，要么 UI 加「Demo 演示」水印
5. **删 `core/` 旧代码**，或移进 `archive/`
6. **对齐 `settings.py` 和 PRD 的数字**
7. **补多轮对话**（`session_id` + `messages` 表 + prompt 拼最近 3 轮）
8. **配 Dify 的 AGENT 节点**

---

## 附：这份文件怎么用

- **面试时**：打开这份文件，先讲第 1 节（两套分段的设计），再讲第 5 节（三条链路），最后讲第 6 节（已知问题）。**主动说问题比被问出来强。**
- **自己改代码时**：第 4 节的表就是 TODO 列表，按第 7 节的优先级改。
- **README 里**：加一行 `架构与数据流见 [docs/architecture.md](docs/architecture.md)`。
