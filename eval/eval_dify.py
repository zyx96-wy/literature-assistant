# -*- coding: utf-8 -*-
"""
Dify RAG 应用 · 批量评测脚本
=====================================
功能：读取 eval/questions.json，逐题调用 Dify 应用的对话 API，
收集"生成答案 + 召回分块"，自动计算指标并写入 CSV。

设计原则：Dify 只负责"生成答案"，所有评测指标都在本脚本里算，保证可复现。

三组实验怎么用它（只改命令行参数，不改代码）：
  实验A(chunk_size) : 在 Dify 知识库改分段 -> 重新索引 -> python eval_dify.py --tag chunk_512
  实验B(retrieval_k): 在 Dify 应用检索设置改 Top-K          -> python eval_dify.py --tag k_6
  实验C(模型选型)   : 在 Dify 应用改 LLM 模型               -> python eval_dify.py --tag model_qwen-max

依赖：
  pip install requests rouge-score -i https://pypi.tuna.tsinghua.edu.cn/simple

先照下面【配置区】填好 API 地址和 Key（就是你 Dify 应用 -> 访问API 页面里给的那两个）。
"""

import os
import sys
import json
import time
import argparse
import csv

import requests

# ============================================================
# 配置区 —— 只改这里
# ============================================================
# Dify API 基地址：
#   官方云     https://api.dify.ai/v1
#   自建本地   http://localhost/v1
DIFY_API_BASE = os.getenv("DIFY_API_BASE", "https://api.dify.ai/v1")

# Dify 应用的 API Key（应用 -> 访问API -> API KEY，形如 app-xxxx）
DIFY_API_KEY = os.getenv("DIFY_API_KEY", "app-在这里粘贴你的Key")

# 应用类型："chat"（对话型，走 /chat-messages）或 "completion"（文本生成型，走 /completion-messages）
APP_MODE = os.getenv("DIFY_APP_MODE", "chat")

# 每次请求之间的间隔秒数（防止触发限流；额度充足可设 0.5~1）
REQUEST_INTERVAL = float(os.getenv("REQUEST_INTERVAL", "1"))

# 单题请求超时（秒）
TIMEOUT = int(os.getenv("TIMEOUT", "60"))

# 评测集与结果输出路径（相对本脚本所在目录）
QUESTIONS_FILE = os.getenv("QUESTIONS_FILE", "questions.json")
RESULT_DIR = os.getenv("RESULT_DIR", "results")


# ============================================================
# 指标计算：ROUGE-L
# ============================================================
_rouge_scorer = None


def _get_rouge():
    global _rouge_scorer
    if _rouge_scorer is None:
        try:
            from rouge_score import rouge_scorer
            _rouge_scorer = rouge_scorer.RougeScorer(["rougeL"], use_stemmer=True)
        except Exception:
            _rouge_scorer = False  # 标记为不可用
    return _rouge_scorer


def rouge_l(prediction: str, reference: str) -> float:
    """ROUGE-L F1。优先用 rouge-score，缺失则退化为字符重合率（对中文更友好）。"""
    prediction = (prediction or "").strip()
    reference = (reference or "").strip()
    if not prediction or not reference:
        return 0.0

    scorer = _get_rouge()
    if scorer is not False:
        # 中文没有空格分词，先用字符级预处理：把每个 CJK 字符之间插空格
        p = _cjk_spaced(prediction)
        r = _cjk_spaced(reference)
        return scorer.score(r, p)["rougeL"].fmeasure

    # 退化方案：字符级 LCS 重合率
    return _char_lcs_f1(prediction, reference)


def _cjk_spaced(text: str) -> str:
    out = []
    for ch in text:
        if "\u4e00" <= ch <= "\u9fff":
            out.append(" " + ch + " ")
        else:
            out.append(ch)
    return "".join(out)


def _char_lcs_f1(a: str, b: str) -> float:
    la, lb = len(a), len(b)
    dp = [[0] * (lb + 1) for _ in range(la + 1)]
    for i in range(1, la + 1):
        for j in range(1, lb + 1):
            if a[i - 1] == b[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])
    lcs = dp[la][lb]
    if lcs == 0:
        return 0.0
    prec = lcs / la
    rec = lcs / lb
    return 2 * prec * rec / (prec + rec)


# ============================================================
# 指标计算：召回相关性（检回的分块里是否含答案要点）
# ============================================================
def retrieval_relevance(reference: str, chunks: list) -> float:
    """标准答案拆成要点，看有多少要点的关键词命中了召回到的分块。返回 0~1。"""
    if not chunks or not reference:
        return 0.0
    joined = " ".join(chunks).lower()
    # 把参考要点按标点切成若干关键片段，取长度>=4 的片段做命中判断
    import re
    points = re.split(r"[，,。.；;、\n]", reference)
    points = [p.strip().lower() for p in points if len(p.strip()) >= 4]
    if not points:
        # 没有可切分的要点，退化为整段字符重合
        return rouge_l(joined, reference)
    hit = sum(1 for p in points if _best_substr_match(p, joined))
    return hit / len(points)


def _best_substr_match(point: str, text: str) -> bool:
    """要点整体命中，或要点里一半以上字符出现在文本中，算命中。"""
    if point in text:
        return True
    hit_chars = sum(1 for c in set(point) if c in text)
    return hit_chars / max(1, len(set(point))) >= 0.7


# ============================================================
# 调用 Dify API
# ============================================================
def call_dify(question: str, user: str = "eval-bot"):
    """返回 (answer, retrieved_chunks, raw_response)。失败时 answer 以 ERROR 开头。"""
    headers = {
        "Authorization": f"Bearer {DIFY_API_KEY}",
        "Content-Type": "application/json",
    }
    if APP_MODE == "completion":
        url = f"{DIFY_API_BASE}/completion-messages"
        payload = {"inputs": {"query": question}, "response_mode": "blocking", "user": user}
    else:
        url = f"{DIFY_API_BASE}/chat-messages"
        payload = {"inputs": {}, "query": question, "response_mode": "blocking", "user": user}

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        answer = data.get("answer", "")
        # 召回分块：blocking 响应里 metadata.retriever_resources
        chunks = []
        meta = data.get("metadata") or {}
        for res in (meta.get("retriever_resources") or []):
            content = res.get("content")
            if content:
                chunks.append(content)
        return answer, chunks, data
    except Exception as e:
        return f"ERROR: {e}", [], {}


# ============================================================
# 主流程
# ============================================================
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", default="baseline", help="本次实验标签，用于命名结果文件")
    parser.add_argument("--questions", default=QUESTIONS_FILE, help="评测集路径")
    args = parser.parse_args()

    base_dir = os.path.dirname(os.path.abspath(__file__))
    qpath = args.questions if os.path.isabs(args.questions) else os.path.join(base_dir, args.questions)
    with open(qpath, "r", encoding="utf-8") as f:
        questions = json.load(f)

    os.makedirs(RESULT_DIR, exist_ok=True)
    out_csv = os.path.join(RESULT_DIR, f"{args.tag}.csv")
    out_json = os.path.join(RESULT_DIR, f"{args.tag}.jsonl")

    print(f"📋 评测集：{qpath}（共 {len(questions)} 题）")
    print(f"🎯 实验标签：{args.tag}")
    print(f"📝 结果写入：{out_csv}\n")

    rows = []
    with open(out_json, "w", encoding="utf-8") as jf:
        for i, item in enumerate(questions, 1):
            qid = item.get("id", i)
            q = item["q"]
            ref = item.get("ref", "")

            answer, chunks, raw = call_dify(q)
            rl = rouge_l(answer, ref)
            rr = retrieval_relevance(ref, chunks)
            token_est = len((answer or "") + "".join(chunks))  # 粗略长度代理，可在 Dify 用量页看真实 token

            rec = {
                "id": qid, "question": q, "answer": answer,
                "rouge_l": round(rl, 4), "retrieval_relevance": round(rr, 4),
                "n_chunks": len(chunks), "char_len": token_est,
            }
            jf.write(json.dumps(rec, ensure_ascii=False) + "\n")
            rows.append({
                "id": qid, "question": q[:40], "rouge_l": round(rl, 4),
                "retrieval_relevance": round(rr, 4), "n_chunks": len(chunks),
                "answer_preview": (answer or "")[:60],
            })
            print(f"  [{i}/{len(questions)}] id={qid}  ROUGE-L={rl:.3f}  召回相关={rr:.3f}  分块={len(chunks)}")
            time.sleep(REQUEST_INTERVAL)

    # 汇总
    n = len(rows)
    avg_rl = sum(r["rouge_l"] for r in rows) / n if n else 0
    avg_rr = sum(r["retrieval_relevance"] for r in rows) / n if n else 0

    with open(out_csv, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "question", "rouge_l", "retrieval_relevance", "n_chunks", "answer_preview"])
        writer.writeheader()
        writer.writerows(rows)
        writer.writerow({})
        writer.writerow({"id": "==AVG==", "rouge_l": round(avg_rl, 4), "retrieval_relevance": round(avg_rr, 4)})

    print(f"\n===== 实验 {args.tag} 汇总 =====")
    print(f"题目数        : {n}")
    print(f"平均 ROUGE-L  : {avg_rl:.4f}")
    print(f"平均召回相关性: {avg_rr:.4f}")
    print(f"\n结果文件：{out_csv}")
    print("把不同 --tag 跑出来的 CSV 里 ==AVG== 那一行填进报告对比表即可。")


if __name__ == "__main__":
    main()