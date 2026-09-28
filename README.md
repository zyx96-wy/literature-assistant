# literature-assistant

> 对话驱动的私有知识库 + 文献笔记助手

上传文献后，用自然语言完成**检索、速读、对比、问答、翻译、笔记、综述、复现**等任务。所有数据持久化在本地 JSON 文件中，跨会话可用，零外部服务依赖。

## 一句话定位

> 对话驱动的私有知识库 + 文献笔记助手，让每一次阅读都变成可复用的知识资产。

## 参考组合

> Zotero 的数据结构 + Elicit 的流程透明度 + Consensus 的共识度量输出 + 笔记可沉淀。

## 不是什么

- 不是通用聊天机器人
- 不是纯文献管理器
- 不是纯文献发现工具
- 不做抄袭检测、全文改写、账号体系

## 特性

- **文献入库与索引**：支持 txt / md / pdf / arXiv 链接，三重去重，自动识别章节结构
- **文献速读**：11 字段速读卡（主旨 / 核心方法 / 结论 / 局限性 / 金句等），带来源锚点
- **深解析**：11 字段结构化 + 逐字溯源校验，校验不过拒绝入库
- **智能检索**：TF-IDF 向量检索，支持模糊检索、单篇问答、跨文献问答、多篇定向
- **对比分析**：多篇文献多维度对比，生成带相关性颜色标注的 HTML 表格
- **综述生成**：Markdown-lite 正文 + 参考文献 JSON → 带引用标注 [1] 的 HTML/Markdown 报告
- **综述引用升级**：引用密度、争议标注、来源可信度分级、证据缺口提示
- **笔记与划线**：句子级划线 + 段落级笔记 + 版本链 + 关联笔记 + 三联对照
- **知识库**：知识单元（论断 + 来源）+ 收藏按钮 + 相似问题优先
- **专题 / 项目**：总库超集，项目子集，读写一体
- **阅读时间记忆**：读到哪 + 继续阅读 + 停留时长
- **翻译**：段落级翻译 + 术语表一致 + 核心词汇 + API 自动
- **复现模式**：从深解析抽复现清单，未提及如实标注
- **模型卡片与术语扩展**：查词弹窗 + 内置公开库 + 用户导入库
- **设置页与用户体系**：本地多用户标识 + 数据隔离
- **纯标准库**：核心功能零依赖（仅解析 PDF 时需要 `pypdf`）

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 入库一篇文献
python scripts/knowledge_base.py add --file your_paper.pdf --authors "张三" --year 2026

# 3. 检索
python scripts/knowledge_base.py search "检索增强生成"

# 4. 看看库里有什么
python scripts/knowledge_base.py list
```

更多命令见 [附录 B：命令速查](./docs/appendix-b-commands.md)。

## 目录结构

```
literature-assistant/
├── README.md
├── PRD.md                       # 产品需求文档（长文档）
├── SKILL.md                     # Agent 执行说明书
├── LICENSE
├── requirements.txt
├── docs/                        # PRD 分章节（以后拆）
├── scripts/
│   ├── common.py
│   ├── knowledge_base.py
│   ├── note_manager.py
│   ├── comparison_table.py
│   └── generate_reports.py
├── examples/
├── tests/
├── data/                        # 运行时数据
│   ├── users/                   # 用户目录
│   ├── literature_meta/
│   ├── note_snapshots/
│   ├── qa_history.json
│   ├── qa_knowledge.json
│   └── ...
└── outputs/
```

## 文档

- [PRD](./PRD.md) — 产品需求文档
- [SKILL](./SKILL.md) — Agent 执行说明书
- [附录 A：数据结构](./docs/appendix-a-data-structure.md)
- [附录 B：命令速查](./docs/appendix-b-commands.md)
- [附录 C：验收清单](./docs/appendix-c-acceptance.md)
- [附录 D：竞品详细对比](./docs/appendix-d-competitors.md)
- [附录 E：工程实现文档](./docs/appendix-e-engineering-doc.md)

## 数据存储

文献元数据示例：

```json
{
  "doc_id": "lit_001",
  "title": "基于大语言模型的临床诊断辅助系统研究",
  "authors": ["张明等"],
  "year": 2026,
  "tags": ["方法", "实验"],
  "deleted": false,
  "chunks": [
    {"pid": 1, "section": "2. 方法", "text": "该方法采用RAG机制..."}
  ],
  "notes": [
    {
      "note_id": "note_001",
      "pid": 3,
      "versions": [
        {"version": "v1", "created_at": "...", "content": "可迁移到我的实验", "status": "active"}
      ],
      "current_version": "v1",
      "status": "active"
    }
  ]
}
```

存储规则：
- 删除文献采用**软删除**，笔记 / 问答 / 划线全保留，可 `restore`
- 彻底删除需二次确认
- 笔记按版本链存储，编辑追加新版本
- 数据根目录可用环境变量 `KA_HOME` 重定向

## 运行测试

```bash
python tests/test_agent.py
```

## 边界说明

- 只检索用户已上传的文献，不做联网搜索
- 笔记定位到段落级（不做到字符级）
- 翻译按段落触发，不做全文自动翻译
- 不做抄袭检测 / 全文改写
- 不做真登录 / 云端同步
- 复现模式只抽取，不补全
- 外部知识库不主动联网

## License

MIT