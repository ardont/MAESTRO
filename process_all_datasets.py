import os
import re
import glob
import hashlib
import shutil
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import fitz # PyMuPDF
import docx

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

BASE_DIR = r"c:\Users\Maxim\Desktop\фокусы\хакатоны\рлт\агентная система поддержки"
DATASET_DIR = os.path.join(BASE_DIR, "dataset")
LEG_DIR = os.path.join(DATASET_DIR, "1_legislation")
INST_DIR = os.path.join(DATASET_DIR, "2_instructions")
INST_OFFICIAL_DIR = os.path.join(INST_DIR, "roseltorg_official_docs")
INST_KB_DIR = os.path.join(INST_DIR, "roseltorg_kb_articles")
PDF_CACHE_DIR = os.path.join(BASE_DIR, "pdf_cache")

os.makedirs(LEG_DIR, exist_ok=True)
os.makedirs(INST_DIR, exist_ok=True)
os.makedirs(INST_OFFICIAL_DIR, exist_ok=True)
os.makedirs(INST_KB_DIR, exist_ok=True)
os.makedirs(PDF_CACHE_DIR, exist_ok=True)

# Helper function for hash computation
def get_file_hash(filepath):
    hasher = hashlib.md5()
    with open(filepath, 'rb') as f:
        buf = f.read()
        # normalize whitespace for text check
        buf_norm = re.sub(rb'\s+', b' ', buf).strip()
        hasher.update(buf_norm)
    return hasher.hexdigest()

print("--- STEP 1: Processing & Deduplicating Local Files ---")
local_files_dir = os.path.join(BASE_DIR, "txt_dataset", "local_files")

seen_hashes = {}
duplicate_count = 0
unique_local_files = []

for fpath in glob.glob(os.path.join(local_files_dir, "*.txt")):
    fname = os.path.basename(fpath)
    fhash = get_file_hash(fpath)
    
    if fhash in seen_hashes:
        print(f"[DUPLICATE REMOVED] {fname} matches {seen_hashes[fhash]}")
        duplicate_count += 1
    else:
        seen_hashes[fhash] = fname
        unique_local_files.append(fpath)

# Separate local files into legislation vs instructions
for fpath in unique_local_files:
    fname = os.path.basename(fpath)
    # Check if it's law / legislation
    if any(law in fname.lower() for law in ['zakon', 'kodex', 'fz', 'гк', 'фз']):
        target_path = os.path.join(LEG_DIR, fname)
        shutil.copy2(fpath, target_path)
        print(f"[LEGISLATION] Saved -> {target_path}")
    else:
        target_path = os.path.join(INST_DIR, fname)
        shutil.copy2(fpath, target_path)
        print(f"[INSTRUCTIONS] Saved -> {target_path}")


print("\n--- STEP 2: Downloading & Parsing Official PDF Instructions from Roseltorg ---")
docs_page_url = "https://www.roseltorg.ru/knowledge_db/docs/documents"
try:
    r = requests.get(docs_page_url, headers=headers, timeout=12)
    soup = BeautifulSoup(r.text, 'html.parser')
    
    pdf_links = []
    for a in soup.find_all('a', href=True):
        href = a['href']
        if href.lower().endswith('.pdf') or href.lower().endswith('.docx'):
            full_url = urljoin(docs_page_url, href)
            title = a.get_text(strip=True)
            # Remove file size if present in title
            title = re.sub(r'\d+(\.\d+)?\s*(KB|MB|GB|B)$', '', title, flags=re.IGNORECASE).strip()
            pdf_links.append((title, full_url))
            
    print(f"Found {len(pdf_links)} official document links to download.")
    
    downloaded_pdf_count = 0
    for idx, (title, pdf_url) in enumerate(pdf_links, 1):
        parsed = urlparse(pdf_url)
        pdf_fname = os.path.basename(parsed.path)
        pdf_local_path = os.path.join(PDF_CACHE_DIR, pdf_fname)
        
        # Download if not cached
        if not os.path.exists(pdf_local_path):
            try:
                res = requests.get(pdf_url, headers=headers, timeout=15)
                if res.status_code == 200:
                    with open(pdf_local_path, 'wb') as pf:
                        pf.write(res.content)
            except Exception as ex:
                print(f"Failed to download {pdf_url}: {ex}")
                continue
                
        if os.path.exists(pdf_local_path):
            # Convert PDF to TXT
            txt_name = f"{os.path.splitext(pdf_fname)[0]}.txt"
            out_txt_path = os.path.join(INST_OFFICIAL_DIR, txt_name)
            
            try:
                doc = fitz.open(pdf_local_path)
                lines = [f"SOURCE DOCUMENT: {pdf_url}", f"TITLE: {title}", "="*60, ""]
                for p_num, page in enumerate(doc, 1):
                    lines.append(f"--- Page {p_num} ---")
                    lines.append(page.get_text())
                
                content_str = "\n".join(lines)
                if len(content_str.strip()) > 100:
                    with open(out_txt_path, 'w', encoding='utf-8') as out_f:
                        out_f.write(content_str)
                    downloaded_pdf_count += 1
            except Exception as ex:
                print(f"Error parsing PDF {pdf_fname}: {ex}")

    print(f"Successfully processed {downloaded_pdf_count} official PDF instructions!")
except Exception as e:
    print(f"Error scraping official docs page: {e}")


print("\n--- STEP 3: Deduplicating & Moving Roseltorg KB Articles ---")
kb_files_dir = os.path.join(BASE_DIR, "txt_dataset", "roseltorg_kb")

kb_duplicate_count = 0
kb_unique_count = 0

for fpath in glob.glob(os.path.join(kb_files_dir, "*.txt")):
    fname = os.path.basename(fpath)
    fhash = get_file_hash(fpath)
    
    if fhash in seen_hashes:
        kb_duplicate_count += 1
    else:
        seen_hashes[fhash] = fname
        target_path = os.path.join(INST_KB_DIR, fname)
        shutil.copy2(fpath, target_path)
        kb_unique_count += 1

print(f"KB Articles: {kb_unique_count} unique copied, {kb_duplicate_count} duplicates skipped.")


print("\n--- STEP 4: Creating Combined Category TXT Exports ---")

# 1. Legislation Combined
leg_combined_path = os.path.join(DATASET_DIR, "legislation_combined.txt")
leg_files = glob.glob(os.path.join(LEG_DIR, "*.txt"))
leg_chars = 0
with open(leg_combined_path, "w", encoding="utf-8") as leg_out:
    leg_out.write("========================================================\n")
    leg_out.write("ЗАКОНОДАТЕЛЬНАЯ СФЕРА - СВОДНЫЙ ФАЙЛ (TXT)\n")
    leg_out.write(f"Всего законов и нормативных актов: {len(leg_files)}\n")
    leg_out.write("========================================================\n\n")
    for lf in leg_files:
        with open(lf, "r", encoding="utf-8") as infile:
            text = infile.read()
            leg_out.write(f"DOCUMENT FILE: {os.path.basename(lf)}\n{'='*60}\n")
            leg_out.write(text)
            leg_out.write("\n\n" + "#"*80 + "\n\n")
            leg_chars += len(text)

print(f"[COMBINED] Saved {leg_combined_path} ({len(leg_files)} files, {leg_chars} chars)")

# 2. Instructions Combined
inst_combined_path = os.path.join(DATASET_DIR, "instructions_combined.txt")
inst_files = glob.glob(os.path.join(INST_DIR, "*.txt")) + \
             glob.glob(os.path.join(INST_OFFICIAL_DIR, "*.txt")) + \
             glob.glob(os.path.join(INST_KB_DIR, "*.txt"))

inst_chars = 0
with open(inst_combined_path, "w", encoding="utf-8") as inst_out:
    inst_out.write("========================================================\n")
    inst_out.write("ИНСТРУКЦИИ И РЕГЛАМЕНТЫ - СВОДНЫЙ ФАЙЛ (TXT)\n")
    inst_out.write(f"Всего инструкций, регламентов и гайдов: {len(inst_files)}\n")
    inst_out.write("========================================================\n\n")
    for inf in inst_files:
        with open(inf, "r", encoding="utf-8") as infile:
            text = infile.read()
            inst_out.write(f"DOCUMENT FILE: {os.path.basename(inf)}\n{'='*60}\n")
            inst_out.write(text)
            inst_out.write("\n\n" + "#"*80 + "\n\n")
            inst_chars += len(text)

print(f"[COMBINED] Saved {inst_combined_path} ({len(inst_files)} files, {inst_chars} chars)")

# 3. Full Complete Dataset Combined
full_combined_path = os.path.join(DATASET_DIR, "full_dataset_combined.txt")
with open(full_combined_path, "w", encoding="utf-8") as full_out:
    full_out.write("========================================================\n")
    full_out.write("ПОЛНАЯ БАЗА ЗНАНИЙ (ЗАКОНОДАТЕЛЬСТВО + ИНСТРУКЦИИ)\n")
    full_out.write("========================================================\n\n")
    with open(leg_combined_path, "r", encoding="utf-8") as f1:
        full_out.write(f1.read())
    full_out.write("\n\n" + "="*100 + "\n\n")
    with open(inst_combined_path, "r", encoding="utf-8") as f2:
        full_out.write(f2.read())

print(f"[COMBINED] Saved {full_combined_path} (Total chars: {leg_chars + inst_chars})")

print("\n--- DATASET PIPELINE COMPLETE! ---")
