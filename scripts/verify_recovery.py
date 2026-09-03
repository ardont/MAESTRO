import sys
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import json
import httpx

with open("dataset/kb_all_articles.json", "r", encoding="utf-8") as f:
    articles = json.load(f)

empty = [a for a in articles if not a.get("html_content") or not a.get("html_content").strip()]
empty_static_ids = {a.get("staticId"): a for a in empty if a.get("staticId")}
empty_ids = {a.get("id"): a for a in empty if a.get("id")}
print(f"Empty articles: {len(empty)}")
print(f"Empty staticIds: {len(empty_static_ids)}")

# Let's fetch GetQuestionsBySectionType for all 4 sections with count=1000
base_url = "https://zakupki.mos.ru/newapi/api/KnowledgeBase/GetQuestionsBySectionType"
sections = ["supplier", "customer", "instruction", "general"]

questions_by_static_id = {}
questions_by_id = {}

for sec in sections:
    try:
        r = httpx.get(base_url, params={"sectionType": sec, "count": 1000}, timeout=30)
        if r.status_code == 200:
            for q in r.json():
                sid = q.get("staticId")
                qid = q.get("id")
                txt = q.get("previewText") or q.get("detailText") or ""
                if sid:
                    questions_by_static_id[sid] = q
                if qid:
                    questions_by_id[qid] = q
    except Exception as e:
        print(f"Error fetching section {sec}: {e}")

print(f"Fetched total questions: {len(questions_by_static_id)} unique staticIds")

# Check how many of the 193 empty articles can be recovered from GetQuestionsBySectionType!
recovered_from_questions = 0
for sid, a in empty_static_ids.items():
    if sid in questions_by_static_id:
        q = questions_by_static_id[sid]
        txt = q.get("previewText") or q.get("detailText") or ""
        if txt.strip():
            recovered_from_questions += 1

print(f"Can be recovered from GetQuestionsBySectionType: {recovered_from_questions} out of {len(empty_static_ids)}")

# Also let's inspect the remaining ones if any
not_in_questions = [a for sid, a in empty_static_ids.items() if sid not in questions_by_static_id or not (questions_by_static_id[sid].get("previewText") or "").strip()]
print(f"Remaining not in questions: {len(not_in_questions)}")
for a in not_in_questions[:10]:
    print(f"  id={a.get('id')} staticId={a.get('staticId')} title={a.get('title')} url={a.get('url')}")
