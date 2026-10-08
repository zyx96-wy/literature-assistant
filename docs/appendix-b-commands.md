# 附录 B：命令速查

版本：v0.7
日期：2026-09-27
所属：文献管理助手 PRD
主文档：[PRD_v0.7.md](../PRD_v0.7.md)

---

> 本附录是命令速查手册，按使用场景组织，供开发与验收时查阅。

## B.1 环境与路径

```bash
PY=python  # 或可用的 python3
```

- Skill 根目录 = 数据根目录（`KA_HOME` 默认即 skill 根目录）
- 脚本位于 `scripts/`
- 命令输出均为 UTF-8 JSON
- 解析 PDF 前确认 `pypdf` 已安装

---

## B.2 文献入库

```bash
# 文件入库（txt / md / pdf）
$PY scripts/knowledge_base.py add --file <path> [--title 标题 --authors 作者 --year 年份 --venue 期刊]

# 疑似重复经用户确认「仍要入库」后重提交
$PY scripts/knowledge_base.py add --file <path> --force-similar

# arXiv 链接入库
$PY scripts/knowledge_base.py add --url https://arxiv.org/abs/2401.00100

# 列出全部文献
$PY scripts/knowledge_base.py list
```

---

## B.3 检索与问答

```bash
# 检索
$PY scripts/knowledge_base.py search "查询词" --top 5 [--doc lit_001]

# 单篇问答
$PY scripts/knowledge_base.py ask "问题" --doc lit_001

# 多篇定向问答
$PY scripts/knowledge_base.py ask "问题" --docs lit_001,lit_006

# 项目内问答
$PY scripts/knowledge_base.py ask "问题" --project proj_001

# 意图自动判断 + 执行前亮牌
$PY scripts/knowledge_base.py intent "对比A和B" [--docs lit_001,lit_006]

# 一键综述流水线
$PY scripts/knowledge_base.py review --topic "检索增强 架构 生成" --docs lit_001,lit_002,lit_003 --confirm
```

---

## B.4 文献速读与深解析

```bash
# 结构化摘要（主旨 / 核心方法 / 结论）
$PY scripts/knowledge_base.py fields --doc lit_001

# 原文片段定位
$PY scripts/knowledge_base.py locate --doc lit_001 --fragment "原文片段"

# 深解析：章节骨架
$PY scripts/deep_parse.py outline --doc lit_001

# 深解析：读原文
$PY scripts/deep_parse.py dump --doc lit_001 [--pid 5 | --from 3 --to 8 | --section "3.2" | --kw "BLEU"] [--max-chars 6000]

# 深解析：生成待填骨架
$PY scripts/deep_parse.py template --doc lit_001 [--out skeleton.json]

# 深解析：入库
$PY scripts/deep_parse.py set --doc lit_001 --json-file payload.json [--force]

# 深解析：查看
$PY scripts/deep_parse.py show --doc lit_001

# 深解析：重新校验引用
$PY scripts/deep_parse.py verify --doc lit_001

# 深解析：全库进度
$PY scripts/deep_parse.py status

# 深解析：清除
$PY scripts/deep_parse.py clear --doc lit_001 [--field 字段名]
```

---

## B.5 阅读与翻译

```bash
# 生成阅读页
$PY scripts/knowledge_base.py page --doc lit_001

# 生成工作台首页
$PY scripts/knowledge_base.py page --home

# 生成问答与溯源页
$PY scripts/knowledge_base.py page --qa

# 生成笔记总览
$PY scripts/knowledge_base.py page --notes

# 翻译：优先用 --pid
$PY scripts/knowledge_base.py translate --doc lit_001 --pid 3 --text "中文译文"

# 翻译：带核心词汇
$PY scripts/knowledge_base.py translate --doc lit_001 --pid 3 --text "中文译文" \
    --vocab "transformer,变换器架构,名词;attention,注意力机制,名词"

# 术语表：查看
$PY scripts/knowledge_base.py glossary --doc lit_001

# 术语表：重新抽取
$PY scripts/knowledge_base.py glossary --doc lit_001 --build

# 术语表：批量修正
$PY scripts/knowledge_base.py glossary --doc lit_001 --set-json '[{"term":"PPO","meaning":"近端策略优化"}]'
$PY scripts/knowledge_base.py glossary --doc lit_001 --json-file glossary.json
```

---

## B.6 笔记与划线

```bash
# 添加笔记（--pid 优先）
$PY scripts/note_manager.py add --doc lit_001 --pid 3 --note "笔记内容"

# 添加笔记（按原文片段定位）
$PY scripts/note_manager.py add --doc lit_001 --fragment "原文片段" --note "笔记内容"

# 添加笔记（英文三联对照）
$PY scripts/note_manager.py add --doc lit_001 --section "2. 方法" --paragraph 3 --note "..." \
    [--original "English text" --translation "译文"]

# 列出笔记
$PY scripts/note_manager.py list [--doc lit_001 | --all]

# 删除笔记
$PY scripts/note_manager.py delete --note note_001

# 导出 CSV
$PY scripts/note_manager.py export-csv [--doc lit_001] [--out 路径]

# 导入 CSV
$PY scripts/note_manager.py import-csv --file notes.csv
```

---

## B.7 问答与知识库

```bash
# 相似问题优先返回收藏
$PY scripts/knowledge_base.py qa --match "问题"

# 存一条问答历史
$PY scripts/knowledge_base.py qa --save --json-file qa_payload.json

# 收藏为知识条目
$PY scripts/knowledge_base.py qa --favorite qa_001

# 删问答历史（不连带知识条目）
$PY scripts/knowledge_base.py qa --delete qa_001

# 删历史并连带删知识条目
$PY scripts/knowledge_base.py qa --delete qa_001 --kid kb_001

# 仅删知识条目
$PY scripts/knowledge_base.py qa --delete-knowledge kb_001

# 消费操作队列
$PY scripts/knowledge_base.py qa --apply-file qa_actions.json

# 列出问答历史
$PY scripts/knowledge_base.py qa --list

# 列出收藏知识库
$PY scripts/knowledge_base.py qa --list-knowledge
```

---

## B.8 阅读时间记忆

```bash
# 最近阅读会话
$PY scripts/knowledge_base.py reading --recent 5

# 某篇上次读到哪
$PY scripts/knowledge_base.py reading --where lit_003

# 汇总停留时长
$PY scripts/knowledge_base.py reading --stats --days 7

# 导入阅读进度（file:// 兜底）
$PY scripts/knowledge_base.py reading --import-file reading_log_import.json
```

---

## B.9 标签管理

```bash
# 打标签
$PY scripts/knowledge_base.py tag --doc lit_001 --add 实验 --add 方法

# 摘标签
$PY scripts/knowledge_base.py tag --doc lit_001 --remove 实验

# 查看当前标签
$PY scripts/knowledge_base.py tag --doc lit_001

# 全局改名（先报影响清单）
$PY scripts/knowledge_base.py tag --from 旧标签 --to 新标签

# 全局改名（二次确认后执行）
$PY scripts/knowledge_base.py tag --from 旧标签 --to 新标签 --confirm

# 全局删除（先报影响篇数）
$PY scripts/knowledge_base.py tag --delete 某标签

# 全局删除（二次确认后执行）
$PY scripts/knowledge_base.py tag --delete 某标签 --confirm

# 手动改色
$PY scripts/knowledge_base.py tag --name 某标签 --color 3
```

---

## B.10 删除与恢复

```bash
# 软删除
$PY scripts/knowledge_base.py delete --doc lit_001

# 恢复
$PY scripts/knowledge_base.py restore --doc lit_001

# 彻底删除：只打印影响清单
$PY scripts/knowledge_base.py purge --doc lit_001

# 彻底删除：二次确认后执行
$PY scripts/knowledge_base.py purge --doc lit_001 --confirm
```

---

## B.11 对比与报告

```bash
# 对比表
$PY scripts/comparison_table.py --docs lit_001 lit_002 --focus "主题关键词"

# 总览报告
$PY scripts/generate_reports.py summary

# 综述报告
$PY scripts/generate_reports.py review --content review.md --refs refs.json --title "标题" [--format md]
```

---

## B.12 项目命令

```bash
# 新建项目
$PY scripts/knowledge_base.py project --new "我的论文 XXX"

# 列出项目
$PY scripts/knowledge_base.py project --list

# 查看项目
$PY scripts/knowledge_base.py project --show proj_001

# 托入文献
$PY scripts/knowledge_base.py project --add-doc lit_001 --to proj_001

# 移除文献（总库保留）
$PY scripts/knowledge_base.py project --remove-doc lit_001 --from proj_001

# 项目内问答
$PY scripts/knowledge_base.py ask "问题" --project proj_001

# 项目内综述
$PY scripts/knowledge_base.py review --topic "主题" --project proj_001 --confirm

# 归档项目
$PY scripts/knowledge_base.py project --archive proj_001

# 恢复项目
$PY scripts/knowledge_base.py project --restore proj_001

# 导出项目
$PY scripts/knowledge_base.py project --export proj_001

# 删除项目（软删，文献保留）
$PY scripts/knowledge_base.py project --delete proj_001
```

---

## B.13 用户命令

```bash
# 列出用户
$PY scripts/knowledge_base.py user --list

# 查看当前用户
$PY scripts/knowledge_base.py user --current

# 新建用户
$PY scripts/knowledge_base.py user --new "用户名"

# 切换用户
$PY scripts/knowledge_base.py user --switch user_002

# 删除用户（二次确认）
$PY scripts/knowledge_base.py user --delete user_002
$PY scripts/knowledge_base.py user --delete user_002 --confirm
```

---

## B.14 复现模式命令

```bash
# 生成复现清单
$PY scripts/knowledge_base.py reproduce --doc lit_001

# 导出复现清单
$PY scripts/knowledge_base.py reproduce --doc lit_001 --export md

# 查看缺口汇总
$PY scripts/knowledge_base.py reproduce --doc lit_001 --gaps
```

---

## B.15 查词命令

```bash
# 查模型
$PY scripts/knowledge_base.py lookup --model "BERT" --doc lit_003

# 查术语
$PY scripts/knowledge_base.py lookup --term "Attention" --doc lit_003

# 查看卡片
$PY scripts/knowledge_base.py card --show model_001

# 收藏卡片为知识
$PY scripts/knowledge_base.py card --favorite model_001

# 列出模型卡片
$PY scripts/knowledge_base.py card --list-models

# 列出术语卡片
$PY scripts/knowledge_base.py card --list-terms
```

---

## B.16 外部知识库命令

```bash
# 查看内置术语库
$PY scripts/knowledge_base.py builtin --terms

# 查看内置模型库
$PY scripts/knowledge_base.py builtin --models

# 禁用内置库
$PY scripts/knowledge_base.py builtin --disable terms

# 导入用户术语库
$PY scripts/knowledge_base.py library --import terms.json --type term

# 导入用户模型库
$PY scripts/knowledge_base.py library --import models.json --type model

# 列出用户导入库
$PY scripts/knowledge_base.py library --list

# 删除用户导入库
$PY scripts/knowledge_base.py library --delete terms.json
```

---

## B.17 桥接与 Worker

```bash
# 桥接服务
$PY scripts/bridge_server.py --port 8787

# Worker：常驻轮询
$PY scripts/translate_worker.py --interval 30

# Worker：只扫一轮
$PY scripts/translate_worker.py --once
```

---

## B.18 数据文件速查

| 文件 | 用途 |
|---|---|
| `data/users/users.json` | 用户注册表 |
| `data/users/<user>/` | 各用户数据目录 |
| `data/users/<user>/projects/` | 项目元数据 |
| `data/cards/models.json` | 模型卡片 |
| `data/cards/terms.json` | 术语卡片 |
| `data/builtin/terms.json` | 内置术语库 |
| `data/builtin/models.json` | 内置模型库 |
| `data/literature_meta/lit_XXX.json` | 文献元数据 |
| `data/note_snapshots/lit_XXX.json` | 笔记 / 划线快照 |
| `data/notes_index.json` | 笔记总索引 |
| `data/qa_history.json` | 问答历史 |
| `data/qa_knowledge.json` | 知识库 |
| `data/reading_log.json` | 阅读进度 |
| `data/translate_queue.json` | 翻译队列 |
| `data/translate_jobs/job_*.txt` | 翻译作业文件 |
| `data/note_queue.json` | 笔记队列（预留） |
| `data/highlight_queue.json` | 划线队列（预留） |
| `data/tags.json` | 标签注册表 |
| `data/usage_log.json` | API 用量 |
| `data/api_status.json` | API 状态 |
| `data/.purged/` | 彻底删除隔离区 |

---

## B.19 常见错误码

| 错误码 | 含义 |
|---|---|
| `DUPLICATE_FILE` | 同文件 MD5 命中 |
| `DUPLICATE_TITLE` | 同标题命中 |
| `SIMILAR_SUSPECT` | 正文高度相似，只提示不拦截 |
| `VERIFY_FAILED` | 深解析引用校验失败 |
| `QUOTE_WRONG_PID` | 引用位置标错，给建议 pid |
| `QUOTE_NOT_FOUND` | 原文找不到这句 |
| `BAD_DOCS` | 引用找不到 / 已软删 / 已彻底删除 |
| `AMBIGUOUS_PARAGRAPH` | 段号在多个章节重复 |
| `needs_confirmation` | 需要用户确认 |
| `needs_decision` | 需要用户决定 |
| `purge_incomplete` | 彻底删除未完成 |
| `quarantined_files` | 文件被隔离到 `.purged/` |
| `USER_SWITCH_FAILED` | 用户切换失败 |
| `PROJECT_NOT_FOUND` | 项目不存在 |
| `DOC_NOT_IN_PROJECT` | 文献不在项目内 |
| `CARD_NOT_FOUND` | 卡片不存在 |
| `LIBRARY_CONFLICT` | 外部库冲突 |