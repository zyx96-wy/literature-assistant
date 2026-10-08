import sys, json, os, time, re
sys.path.insert(0, '..')
sys.stdout.reconfigure(encoding='utf-8')

import requests

API = 'http://127.0.0.1:5000'

with open('eval_retrieval.json', encoding='utf-8') as f:
    questions = json.load(f)

from core.vector_store import load_vectorstore
from core.rag_chain import multi_retrieval
from backend.database import get_doc

vs = load_vectorstore()


def norm(s):
    return re.sub(r'\s+', '', (s or '')).lower()


def check_L2(answer_text, doc_id, pid):
    """L2：召回的片段里，是否包含目标段的关键内容"""
    doc = get_doc(doc_id)
    if not doc or not doc.get('paragraphs'):
        return False
    target = doc['paragraphs'][pid - 1]
    # 目标段拆成 20 字滑窗，命中任意 3 个就算
    nt = norm(target)
    na = norm(answer_text)
    if not nt:
        return False
    hit = 0
    for i in range(0, max(1, len(nt) - 20), 10):
        if nt[i:i+20] in na:
            hit += 1
            if hit >= 3:
                return True
    return False


def check_L3_keywords(answer, keywords):
    """L3：LLM 答案里是否包含关键词（粗糙版人工判断的替代）"""
    na = norm(answer)
    return all(norm(k) in na for k in keywords)


results = []

for q in questions:
    print(f"\n--- {q['qid']} {q['question'][:50]} ---")

    # --- L1 + L2：检索层 ---
    docs = multi_retrieval(q['question'], vs, doc_ids=None)
    top5 = docs[:5]

    hit1_doc = False
    hit5_doc = False
    hit5_para = False

    for rank, d in enumerate(top5, 1):
        if d.metadata.get('doc_id') == q['doc_id']:
            hit5_doc = True
            if rank == 1:
                hit1_doc = True
            # L2：目标段是否在召回片段里
            all_content = ' '.join(x.page_content for x in top5)
            if check_L2(all_content, q['doc_id'], q['pid']):
                hit5_para = True
            break

    # --- L3：生成层（调 /api/ask）---
    answer = ''
    try:
        r = requests.post(f'{API}/api/ask', json={
            'question': q['question'],
            'scope': [q['doc_id']],
            'session_id': f'eval_{q["qid"]}'
        }, timeout=60)
        answer = r.json().get('answer', '')
    except Exception as e:
        answer = f'[ERROR] {e}'

    results.append({
        'qid': q['qid'],
        'question': q['question'],
        'hit@1_doc': hit1_doc,
        'hit@5_doc': hit5_doc,
        'hit@5_para': hit5_para,
        'answer': answer[:200],  # 保留前 200 字供人工核验
    })

    print(f"  L1 Hit@5（文献）: {'✅' if hit5_doc else '❌'}")
    print(f"  L2 Hit@5（段落）: {'✅' if hit5_para else '❌'}")
    print(f"  L3 答案：{answer[:120]}")


# --- 汇总 ---
n = len(results)
h1 = sum(1 for r in results if r['hit@1_doc'])
h5 = sum(1 for r in results if r['hit@5_doc'])
h5p = sum(1 for r in results if r['hit@5_para'])

print(f"\n{'='*60}")
print(f"=== 汇总（{n} 条） ===")
print(f"L1 Hit@1（文献级）: {h1}/{n} = {h1/n*100:.1f}%")
print(f"L1 Hit@5（文献级）: {h5}/{n} = {h5/n*100:.1f}%")
print(f"L2 Hit@5（段落级）: {h5p}/{n} = {h5p/n*100:.1f}%")
print(f"\n注意：L2 段落级是「召回片段里是否包含目标段」，判据是中文字符滑窗。")
print(f"     如果 L2 命中率低，说明检索召回了对的文献、但没召回对的段。")

with open('results/eval_retrieval_result.json', 'w', encoding='utf-8') as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print(f"\n结果保存到 eval_retrieval_result.json（含每条的 LLM 答案，供人工核验）")