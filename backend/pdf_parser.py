# -*- coding: utf-8 -*-
"""
PDF 解析 + 两套分段
===================

本文件刻意维护 **两套互不相干的分段**。用途不同、约束相反，任何时候都不要合并成一个：

┌──────────────┬─────────────────────────┬───────────────────────────────┐
│              │ split_for_rag()         │ split_for_reading()           │
├──────────────┼─────────────────────────┼───────────────────────────────┤
│ 消费者       │ Chroma 向量库 / LLM     │ 阅读页的人眼                  │
│ 用途         │ 召回单元                │ 阅读单元（¶N 编号、溯源锚点） │
│ 允许重叠     │ **必须**（overlap 50）   │ **禁止**（重叠=同一句读两遍） │
│ 允许句中切   │ 允许（截断不影响语义）  │ **禁止**（半句跨段即为 BUG）  │
│ 长度         │ 500（召回粒度）         │ ≤ 700（阅读舒适区上限）       │
│ 干净度要求   │ 中等                    │ 高（页眉页脚必须去掉）        │
└──────────────┴─────────────────────────┴───────────────────────────────┘

一句话：**检索块可以断，阅读段不能断。**
"""
import re

try:                       # PyMuPDF >= 1.24 推荐新名；老版本只有 fitz
    import pymupdf as fitz
except ImportError:
    import fitz

# ---------------------------------------------------------------- 常量

# 句末标点（中英）
_SENT_END = set('。！？；….!?;')
# 句末标点后面可能出现的右括号 / 引号
_CLOSING = set('」』》】）)］]"\'”’')
# 英文常见缩写：这些点不是句末，不能在这里切
_ABBREV = {
    'al.', 'e.g.', 'i.e.', 'etc.', 'vs.', 'cf.', 'approx.', 'fig.', 'eq.',
    'ref.', 'no.', 'vol.', 'pp.', 'et', 'dr.', 'mr.', 'ms.', 'prof.', 'st.',
    'jan.', 'feb.', 'mar.', 'apr.', 'jun.', 'jul.', 'aug.', 'sep.', 'oct.',
    'nov.', 'dec.', 'figs.', 'secs.', 'eqs.', 'refs.',
}
# 页眉页脚 / 出版商水印特征
_NOISE_PAT = re.compile(
    r'(Authorized licensed use'
    r'|Downloaded on\s'
    r'|©\s*\d{4}\s*(IEEE|ACM|Springer|Elsevier)'
    r'|Digital Object Identifier'
    r'|https?://(dx\.)?doi\.org'
    r'|Conditions of access and use'
    r'|This article may be used for research'
    r'|arXiv:\d{4}\.\d{4,5}v\d'
    r'|Proceedings of the\s+\d'
    r'|^共\s*\d+\s*页$'
    r'|^\d{4}年第\d+期$'
    r')'
)


# ---------------------------------------------------------------- PDF 提取

def _clean_line(s: str) -> str:
    """单行清洗：全角空格 / 软连字符 / 连续空白，但保留行首缩进（段落信号）"""
    s = s.replace('\xa0', ' ').replace('\u3000', ' ').replace('\xad', '')
    s = re.sub(r'[ \t]+', ' ', s)
    return s.strip()


def _sort_blocks(blocks):
    """y 分桶（容差 3pt）后按 x 排序 —— 保证同一行内的词序正确"""
    return sorted(blocks, key=lambda b: (round(b[1] / 3.0), b[0]))


def _join_text(a: str, b: str) -> str:
    """拼接同一行内的两个块：中英混排时按需补空格"""
    if not a:
        return b
    if a[-1].isascii() and a[-1].isalnum() and b[0].isascii() and b[0].isalnum():
        return a + ' ' + b
    return a + b


def _blocks_to_lines(blocks) -> list:
    """
    块 → 行。同一 y 桶内的块合并成一行（按 x 排序）。

    PDF 里一行常因字体/样式变化被切成多个块（比如加粗的术语）。
    不合并的话阅读页会看到「半句换行」，和「半句跨段」一样难读。
    """
    lines, cur_key, cur = [], None, []
    for b in _sort_blocks(blocks):
        key = round(b[1] / 3.0)
        if cur_key is None or key == cur_key:
            cur.append(b)
            cur_key = key
        else:
            lines.append(_merge_line(cur))
            cur, cur_key = [b], key
    if cur:
        lines.append(_merge_line(cur))
    return [l for l in lines if l]


def _merge_line(bs) -> str:
    s = ''
    for b in bs:
        t = _clean_line(b[4])
        if t:
            s = _join_text(s, t)
    return s


def _page_text(page) -> str:
    """
    按文本块的 bbox 提取，**先左栏后右栏**。

    用 page.get_text('text', sort=True) 只能得到按 y 排序的字符流，
    双栏 PDF 会把「左栏行 + 右栏行」拼进同一行，读出来是两句交错的天书。
    这里改用 blocks（带坐标），先判栏再按栏输出。
    """
    W, H = page.rect.width, page.rect.height
    raw = [b for b in page.get_text('blocks') if b[6] == 0]  # b[6]=0 文本块
    blocks = [b for b in raw if _clean_line(b[4])]
    if not blocks:
        return ''

    # 全宽块（页眉 / 标题 / 跨栏图注 / 页脚） vs 窄块（栏内正文）
    full = [b for b in blocks if (b[2] - b[0]) > 0.62 * W]
    side = [b for b in blocks if (b[2] - b[0]) <= 0.62 * W]

    # 双栏判定：左右半页都得有足够多的窄块
    two_col = False
    if len(side) >= 6:
        mid_x = W / 2.0
        n_left = sum(1 for b in side if (b[0] + b[2]) / 2 < mid_x)
        two_col = n_left >= 3 and (len(side) - n_left) >= 3

    if not two_col:
        return '\n'.join(_blocks_to_lines(blocks))

    mid_x = W / 2.0
    left = [b for b in side if (b[0] + b[2]) / 2 < mid_x]
    right = [b for b in side if (b[0] + b[2]) / 2 >= mid_x]

    # 顶部全宽 = 标题/作者/摘要开头；其余全宽（跨栏图表、脚注）排在正文之后
    top = [b for b in full if b[1] < 0.15 * H]
    rest = [b for b in full if b[1] >= 0.15 * H]

    return '\n'.join(
        _blocks_to_lines(top) + _blocks_to_lines(left)
        + _blocks_to_lines(right) + _blocks_to_lines(rest)
    )


def parse_pdf(filepath: str) -> str:
    """按阅读顺序提取全文，页与页之间用空行分隔（空行 = 段落边界信号）"""
    doc = fitz.open(filepath)
    pages = [_page_text(p) for p in doc]
    doc.close()
    return '\n\n'.join(p for p in pages if p)


# ---------------------------------------------------------------- 检索分段

def split_for_rag(text: str) -> list:
    """
    RAG 检索块。**允许句中切、允许重叠** —— 目的是召回率，不是给人读。
    不要拿这份去渲染阅读页。
    """
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=50,
        separators=['\n\n', '\n', '。', '！', '？', '；', ' ', '']
    )
    return splitter.split_text(text)


# ---------------------------------------------------------------- 阅读分段

def _is_noise(s: str) -> bool:
    if len(s) < 5 and not re.match(r'^\d+(\.\d+)*$', s):
        return True
    if s.isdigit():
        return True
    if _NOISE_PAT.search(s):
        return True
    return False


def _ends_sentence(s: str) -> bool:
    """去掉尾部右引号/右括号后，最后一个字符是不是句末标点"""
    i = len(s) - 1
    while i >= 0 and s[i] in _CLOSING:
        i -= 1
    if i < 0:
        return False
    return s[i] in _SENT_END


def _is_abbrev_dot(s: str, i: int) -> bool:
    """s[i] == '.'，判断它是缩写点（非句末）还是真正的句末"""
    j = i - 1
    while j >= 0 and s[j].isalpha():
        j -= 1
    word = s[j + 1:i + 1].lower()
    if word in _ABBREV:
        return True
    if len(word) == 2 and word[0].isalpha():      # "A." / "B."
        return True
    nxt = s[i + 1] if i + 1 < len(s) else ''
    if nxt and (nxt.islower() or nxt.isdigit()):  # "Fig. 1" / "0.5"
        return True
    return False


def _sentence_positions(s: str) -> list:
    """所有可安全切分的句末位置（切分点 = 该标点之后）"""
    pos = []
    for i, ch in enumerate(s):
        if ch not in _SENT_END:
            continue
        if ch == '.' and _is_abbrev_dot(s, i):
            continue
        if ch in '!?;' and i + 1 < len(s) and s[i + 1].isdigit():
            continue
        pos.append(i + 1)
    return pos


def _split_long(p: str, max_len: int) -> list:
    """超长段落按句子边界切 —— 只在句末切，绝不切在句中"""
    if len(p) <= max_len:
        return [p]
    cuts = _sentence_positions(p)
    if not cuts:
        # 整段没有任何句末标点（表格、公式堆、乱码）：宁可整段保留，也不硬切
        return [p]

    out, start = [], 0
    for c in cuts:
        # 攒够一段就切；单句本身超长也照切（保证不无限膨胀）
        if c - start >= max_len * 0.6 or len(p) - start <= max_len:
            if c - start >= max_len * 0.6:
                out.append(p[start:c].strip())
                start = c
    if start < len(p):
        tail = p[start:].strip()
        if tail:
            out.append(tail)
    return [x for x in out if x] or [p]


def _merge_fragments(paras: list, min_len: int) -> list:
    """过短碎片并入下一段（标题行除外），避免满屏 ¶N 只有半句"""
    out = []
    for p in paras:
        s = p.strip()
        if not s:
            continue
        is_heading = bool(re.match(r'^\d+(\.\d+)*[\s、.]', s)) and len(s) < 60
        if out and (len(s) < min_len) and not is_heading:
            out[-1] = _join(out[-1], s)
        else:
            out.append(s)
    return out


def _join(a: str, b: str) -> str:
    """拼接两段：中英混排时按需补空格"""
    if not a:
        return b
    if a[-1].isascii() and a[-1].isalnum() and b[0].isascii() and b[0].isalnum():
        return a + ' ' + b
    return a + b


def split_for_reading(text: str, max_len: int = 700, min_len: int = 40) -> list:
    """
    阅读段落。**禁止句中切、禁止重叠**，目标是给人一句不差地读下来。

    处理顺序：
      1. 还原 PDF 断词连字符（linguis-\\ntic → linguistic）
      2. 逐行清洗、剔除页眉页脚
      3. 行 → 逻辑段落（空行 / 缩进 / 段末短行 三选一作为段落边界）
      4. 超长段按句子边界再切
      5. 过短碎片并入下一段
    """
    if not text:
        return []

    text = text.replace('\r\n', '\n').replace('\r', '\n').replace('\xad', '')
    # 1. 断词连字符还原： "linguis-\ntic" / "com-\nputer"
    text = re.sub(r'(?<=[A-Za-z])-\n(?=[a-z])', '', text)

    # 2. 逐行清洗（保留缩进信息）
    rows = []          # (缩进宽度, 清洗后文本)
    for ln in text.split('\n'):
        raw = ln.replace('\xa0', ' ').replace('\u3000', ' ')
        indent = len(raw) - len(raw.lstrip(' '))
        s = _clean_line(ln)
        if not s:
            rows.append((0, ''))            # 空行 = 段落边界
            continue
        if _is_noise(s):
            continue
        rows.append((indent, s))

    widths = [len(s) for _, s in rows if s]
    if widths:
        widths.sort()
        med_w = widths[len(widths) // 2]
    else:
        med_w = 0
    short_line = max(20, med_w * 0.75)

    # 3. 行 → 逻辑段落
    paras, buf, prev = [], '', ''
    for indent, s in rows:
        if not s:
            if buf:
                paras.append(buf)
                buf, prev = '', ''
            continue
        if buf:
            new_para = (
                indent >= 2                                   # 首行缩进
                or (_ends_sentence(buf) and len(buf) < short_line)  # 段末短行
                or (re.match(r'^\d+(\.\d+)*[\s、.]', s) and _ends_sentence(buf))  # 下一行是小节标题
            )
            if new_para:
                paras.append(buf)
                buf = s
                prev = s
                continue
        buf = _join(buf, s) if buf else s
        prev = s
    if buf:
        paras.append(buf)

    # 4. 超长段句级再切
    out = []
    for p in paras:
        out.extend(_split_long(p, max_len))

    # 5. 碎片合并
    out = _merge_fragments(out, min_len)

    return [p for p in out if len(p.strip()) > 10]
