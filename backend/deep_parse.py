# -*- coding: utf-8 -*-
"""
深解析：用 LLM 抽 11 字段（JSON Mode + 真实溯源）

改动说明（修复原实现三个问题）：
1. 原来只喂 text[:3000] —— 约 1~2 页，导致「结论」「局限性」等后部字段大量假阴性。
   现在按段落编号喂全文（超长时保留首尾，中间省略并显式标注）。
2. 原来 loc 写死 '¶1'、quote 恒为空 —— 溯源是假的。
   现在要求 LLM 同时给出 pid（段落号）和 quote（原文摘录），并在 Python 侧逐字校验。
3. 校验不过的字段标记 verified=False，不静默通过，也不伪装成「论文中未提及」。
"""
from langchain_community.chat_models import ChatTongyi
from langchain_core.prompts import ChatPromptTemplate
from config.settings import LLM_MODEL, DASHSCOPE_API_KEY
import os
import json
import re
import unicodedata

os.environ['DASHSCOPE_API_KEY'] = DASHSCOPE_API_KEY

_llm = ChatTongyi(
    model_name=LLM_MODEL,
    temperature=0.1,
    model_kwargs={"response_format": {"type": "json_object"}}
)

FIELD_KEYS = ['主旨', '研究问题', '核心方法', '关键步骤', '创新点',
              '实验设置', '评估指标', '关键结果', '结论', '局限性', '金句摘录']
# 论文靠后才出现的字段：多批结果冲突时取最后一批的答案（引言里的"结论"往往是预告，不是真结论）
_TAIL_FIELDS = {'结论', '局限性', '关键结果', '金句摘录'}

# 单次喂给 LLM 的字符上限（约 7~8k token，留足余量）
MAX_CHARS = 30000

PROMPT = ChatPromptTemplate.from_template('''你是文献解析助手。请从论文文本中抽取 11 个字段。

论文文本已按段落编号，格式形如：
[1] 段落正文
[2] 段落正文

严格按以下 JSON 格式输出（key 必须是下面列出的中文名，不能增删改）：

{{
  "主旨": {{"text": "你的概括", "pid": 3, "quote": "该结论依据的原文短句，必须逐字来自 [3] 段"}},
  "研究问题": {{"text": "...", "pid": 1, "quote": "..."}},
  "核心方法": null,
  "关键步骤": null,
  "创新点": null,
  "实验设置": null,
  "评估指标": null,
  "关键结果": null,
  "结论": null,
  "局限性": null,
  "金句摘录": null
}}

要求：
- 每个字段都要尽力填。只要能在编号段落里找到依据就必须填，不要因为拿不准就偷懒填 null。
  一篇论文通常至少能填 6~8 个字段；整份 JSON 里非 null 少于 4 个，说明你过于保守了
- 确实全文都找不到依据的字段才填 null，不要编造
- pid 必须是文本中真实存在的段落号（整数）
- quote 必须是 pid 指向段落中的连续原文片段，逐字复制，长度 10~150 字。
  整句太长就截取其中连续的一段；实在找不到才把该字段填 null，绝不改写原文
- text 是你自己的概括，可以跨段落综合；但 quote 必须来自 pid 指向的那一段
- 值里不要用英文双引号，用「」代替
- 只输出 JSON，不要任何额外内容

论文文本：
{text}
''')


# ===== 溯源校验工具 =====

def _norm(s: str) -> str:
    """归一化：去空白、统一全半角，用于逐字比对"""
    if not s:
        return ''
    s = unicodedata.normalize('NFKC', str(s))
    s = re.sub(r'\s+', '', s)
    return s


def _split_paragraphs(text: str):
    """没有现成段落表时的兜底切分"""
    parts = [p.strip() for p in re.split(r'\n\s*\n', text or '') if p.strip()]
    return parts or ([text] if text else [])


def _chunk_paragraphs(paragraphs, max_chars=MAX_CHARS):
    """
    按累计字符数把段落切成若干批。**段落号始终是全局编号**，
    这样 LLM 返回的 pid 无需换算就能直接对应真实段落。
    """
    batches, cur, used = [], [], 0
    for idx, p in enumerate(paragraphs, 1):
        # 单段本身就超长：单独成批并截断，避免这一批永远拼不出内容
        if not cur and len(p) > max_chars:
            batches.append([(idx, p[:max_chars])])
            continue
        if cur and used + len(p) > max_chars:
            batches.append(cur)
            cur, used = [], 0
        cur.append((idx, p))
        used += len(p)
    if cur:
        batches.append(cur)
    return batches


def _batch_text(batch, bi, total):
    head = ''
    if total > 1:
        head = (f'（这是全文第 {bi}/{total} 批，段落号为全局编号，'
                f'只需根据给出的段落作答）\n\n')
    return head + '\n\n'.join(f'[{i}] {p}' for i, p in batch)


def _locate_quote(quote, pid, paragraphs):
    """
    在段落中定位 quote。
    返回 (真实pid, 命中方式) 或 (None, None)
    """
    q = _norm(quote)
    if not q:
        return None, None

    # 1. LLM 指定的段落
    if isinstance(pid, int) and 1 <= pid <= len(paragraphs):
        if q in _norm(paragraphs[pid - 1]):
            return pid, 'exact'

    # 2. 相邻 ±2 段（LLM 常把段号标偏）
    if isinstance(pid, int):
        for off in (-2, -1, 1, 2):
            cand = pid + off
            if 1 <= cand <= len(paragraphs) and q in _norm(paragraphs[cand - 1]):
                return cand, 'near'

    # 3. 全文搜索
    for idx, p in enumerate(paragraphs, 1):
        if q in _norm(p):
            return idx, 'global'

    return None, None


def _call_llm(numbered):
    """调一次 LLM 拿字段 JSON；失败返回 {}（不中断整篇）"""
    try:
        chain = PROMPT | _llm
        result = chain.invoke({'text': numbered})
        raw = result.content.strip()

        # 有些模型会把 JSON 包在 ```json 里
        if raw.startswith('```'):
            raw = re.sub(r'^```(?:json)?\s*', '', raw)
            raw = re.sub(r'\s*```$', '', raw)

        fields = json.loads(raw)
        if not isinstance(fields, dict):
            raise ValueError('LLM 返回的不是 JSON 对象')
        return fields
    except Exception as e:
        print(f'   ⚠ 该批调用失败（跳过）：{e}')
        return {}


def _form_one(k, v, paragraphs):
    """单个字段 → 落库结构；无依据或溯源失败返回 None / verified=False"""
    # 兼容旧格式：直接给字符串
    if isinstance(v, str):
        v = {'text': v, 'pid': None, 'quote': ''}
    if not isinstance(v, dict):
        return None

    body = str(v.get('text') or '').strip()
    if not body or body.lower() in ('null', 'none', '无'):
        return None
    if any(m in body for m in ('未提及', '未明确提及', '论文中没有', '未提到')):
        return None

    quote = str(v.get('quote') or '').strip()
    real_pid, match = _locate_quote(quote, v.get('pid'), paragraphs)

    return {
        'text': body,
        'loc': f'¶{real_pid}' if real_pid else '未定位',
        # pid 落库：resegment / demo 跳转都读这个字段，只存 loc 字符串会让它们永远拿不到段落号
        'pid': real_pid,
        'quote': quote if real_pid else '',
        # 溯源校验：quote 必须逐字命中原文，否则不标注为可追溯
        'verified': bool(real_pid),
        'match': match or 'none',
        # 分批调用后已覆盖全文，不再有截断
        'truncated': False
    }


def deep_parse(text, paragraphs=None):
    """
    抽取 11 字段（JSON Mode + 真实溯源）

    长文献按段落**分多批**调用（每批 ≤ MAX_CHARS，段落号始终全局），
    再合并各批结果 —— 旧版只喂前 30000 字符，导致长文的结论/局限性整片丢失。

    :param text: 全文
    :param paragraphs: 阅读分段（list[str]），用于段落号定位；为空则自动切分
    :return: {字段名: {'text','loc','quote','verified','match'} 或 None}
    """
    paragraphs = paragraphs or _split_paragraphs(text)
    if not paragraphs:
        return {}

    batches = _chunk_paragraphs(paragraphs)
    total = len(batches)

    # 各批结果先全收着，最后统一挑
    collected = {k: [] for k in FIELD_KEYS}
    for bi, batch in enumerate(batches, 1):
        fields = _call_llm(_batch_text(batch, bi, total))
        for k in FIELD_KEYS:
            one = _form_one(k, fields.get(k), paragraphs)
            if one:
                collected[k].append(one)
        if total > 1:
            print(f'   批 {bi}/{total}：{len(batch)} 段')

    formatted = {}
    for k in FIELD_KEYS:
        cands = collected[k]
        if not cands:
            formatted[k] = None
            continue
        # 溯源通过的优先；正文靠后的字段（结论/局限性等）取最后一批的答案更准
        pool = [c for c in cands if c['verified']] or cands
        formatted[k] = pool[-1] if k in _TAIL_FIELDS else pool[0]

    return formatted
