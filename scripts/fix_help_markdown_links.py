import json
import re
import os

def main():
    kb_clean_path = "dataset/kb_clean.json"
    with open(kb_clean_path, "r", encoding="utf-8") as f:
        docs = json.load(f)

    img_dir = "dataset/images"
    local_files = set(os.listdir(img_dir))

    replaced = 0
    pattern = re.compile(r'https?://help\.mos\.ru/uploads/([^\s\)\"\'>]+(?:\([0-9]+\))?\.[a-zA-Z0-9]+)')

    for d in docs:
        text = d.get("text", "")
        
        def replacer(match):
            nonlocal replaced
            full_url = match.group(0)
            filename = match.group(1)
            safe_name = f"help_{filename}"
            if safe_name in local_files:
                replaced += 1
                return f"images/{safe_name}"
            return full_url

        new_text = pattern.sub(replacer, text)
        d["text"] = new_text

    with open(kb_clean_path, "w", encoding="utf-8") as f:
        json.dump(docs, f, ensure_ascii=False, indent=2)

    with open("dataset/kb_final.json", "w", encoding="utf-8") as f:
        json.dump(docs, f, ensure_ascii=False, indent=2)

    print(f"Successfully mapped {replaced} help.mos.ru images to local images/ paths!")

    web_rem = 0
    for d in docs:
        rem = re.findall(r'https?://[^\s\)\"\'>]+\.(?:png|jpg|jpeg|gif)', d["text"])
        web_rem += len(rem)

    print(f"Remaining external image links: {web_rem}")

if __name__ == "__main__":
    main()
