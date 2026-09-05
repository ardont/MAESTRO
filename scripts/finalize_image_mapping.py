import json
import re
import os

kb_clean_path = "dataset/kb_clean.json"
with open(kb_clean_path, "r", encoding="utf-8") as f:
    docs = json.load(f)

img_dir = "dataset/images"
local_files = set(os.listdir(img_dir))

replaced = 0
for d in docs:
    text = d.get("text", "")
    # Find help.mos.ru matches
    matches = re.findall(r'!\[(.*?)\]\((https?://help\.mos\.ru/uploads/[^\s\)\"\']+)\)', text)
    for alt, u in matches:
        filename = os.path.basename(u)
        safe_name = "".join(c for c in f"help_{filename}" if c.isalnum() or c in ('.', '_', '-', '(', ')'))
        if safe_name in local_files:
            text = text.replace(f"![{alt}]({u})", f"![{alt}](images/{safe_name})")
            replaced += 1
    d["text"] = text

with open(kb_clean_path, "w", encoding="utf-8") as f:
    json.dump(docs, f, ensure_ascii=False, indent=2)

with open("dataset/kb_final.json", "w", encoding="utf-8") as f:
    json.dump(docs, f, ensure_ascii=False, indent=2)

print(f"Replaced {replaced} remaining help.mos.ru links with local images/ paths.")

# Recount
with open(kb_clean_path, "r", encoding="utf-8") as f:
    docs = json.load(f)
web_rem = []
for d in docs:
    rem = re.findall(r'!\[.*?\]\((https?://[^\)]+)\)', d["text"])
    web_rem.extend(rem)
print(f"Remaining web image links: {len(web_rem)}")
