import os
import sys
import json

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

print("=== 1. FILES IN dataset/pdfs/ ===")
pdf_dir = "dataset/pdfs"
if os.path.exists(pdf_dir):
    for f in os.listdir(pdf_dir):
        p = os.path.join(pdf_dir, f)
        print(f"  {f} -> {os.path.getsize(p):,} bytes")
else:
    print("  Directory dataset/pdfs does not exist!")

print("\n=== 2. dataset/kb_pdfs.json ===")
kb_pdfs = "dataset/kb_pdfs.json"
if os.path.exists(kb_pdfs):
    with open(kb_pdfs, "r", encoding="utf-8") as f:
        data = json.load(f)
    print(f"  Entries in kb_pdfs.json: {len(data)}")
    for i, item in enumerate(data):
        title = item.get("title") or item.get("file_name") or "No title"
        url = item.get("url", "")
        content = item.get("content") or item.get("text") or ""
        print(f"  [{i+1}] {title} (URL: {url})")
        print(f"      Size: {len(content)} chars | Preview: {content[:120].strip()!r}")
else:
    print("  File dataset/kb_pdfs.json does not exist!")

print("\n=== 3. IMAGES IN dataset/images/ ===")
img_dir = "dataset/images"
if os.path.exists(img_dir):
    img_files = os.listdir(img_dir)
    print(f"  Total images in dataset/images/: {len(img_files)}")
    sizes = [os.path.getsize(os.path.join(img_dir, f)) for f in img_files]
    zero_size = [f for f, s in zip(img_files, sizes) if s == 0]
    print(f"  Zero-size images: {len(zero_size)}")
    print(f"  Average size: {sum(sizes)/len(sizes):,.0f} bytes")
else:
    print("  Directory dataset/images does not exist!")

print("\n=== 4. SCREENSHOTS & IMAGES IN kb_clean.json ===")
kb_clean = "dataset/kb_clean.json"
if os.path.exists(kb_clean):
    with open(kb_clean, "r", encoding="utf-8") as f:
        clean = json.load(f)
    total_imgs = 0
    local_imgs = 0
    web_imgs = 0
    import re
    for d in clean:
        matches = re.findall(r'!\[.*?\]\((.*?)\)', d.get("text", ""))
        total_imgs += len(matches)
        for m in matches:
            if m.startswith("images/"):
                local_imgs += 1
            elif m.startswith("http"):
                web_imgs += 1
    print(f"  Total image tags in kb_clean.json: {total_imgs}")
    print(f"  Mapped to local images/: {local_imgs}")
    print(f"  Remaining web URLs: {web_imgs}")
