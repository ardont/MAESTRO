import os
import re
import sys
import time
import requests
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
import html2text
from urllib.parse import urlparse, urljoin

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

base_output_dir = r"c:\Users\Maxim\Desktop\фокусы\хакатоны\рлт\агентная система поддержки\txt_dataset\roseltorg_kb"
os.makedirs(base_output_dir, exist_ok=True)
merged_file_path = r"c:\Users\Maxim\Desktop\фокусы\хакатоны\рлт\агентная система поддержки\txt_dataset\roseltorg_knowledge_base_full.txt"

print("1. Collecting URLs from Roseltorg Sitemaps...")
urls_to_scrape = set()

for page_num in range(1, 30):
    sitemap_url = f"https://www.roseltorg.ru/sitemap.xml?page={page_num}"
    try:
        r = requests.get(sitemap_url, headers=headers, timeout=10)
        if r.status_code != 200:
            break
        root = ET.fromstring(r.content)
        for elem in root.iter('{http://www.sitemaps.org/schemas/sitemap/0.9}loc'):
            u = elem.text.strip()
            if '/knowledge_db' in u or '/azbuka-zakupok' in u:
                urls_to_scrape.add(u)
    except Exception as e:
        break

print(f"Total URLs found in sitemaps: {len(urls_to_scrape)}")

# BFS crawl to find additional internal KB URLs
print("2. Crawling knowledge_db hub pages for additional links...")
queue = list(urls_to_scrape) if urls_to_scrape else ["https://www.roseltorg.ru/knowledge_db"]
visited_urls = set()

h2t = html2text.HTML2Text()
h2t.ignore_links = False
h2t.ignore_images = True
h2t.ignore_emphasis = False
h2t.body_width = 0

scraped_articles = []

def clean_filename(s):
    s = re.sub(r'[\\/*?:"<>|]', '_', s)
    return s[:150]

idx = 0
while queue:
    url = queue.pop(0)
    if url in visited_urls:
        continue
    visited_urls.add(url)
    
    idx += 1
    if idx % 20 == 0 or idx == 1:
        print(f"Progress: [{idx}/{len(visited_urls)+len(queue)}] Crawling: {url}")
        
    try:
        r = requests.get(url, headers=headers, timeout=12)
        if r.status_code != 200:
            continue
        
        soup = BeautifulSoup(r.text, 'html.parser')
        
        # Discover internal knowledge_db links
        for a in soup.find_all('a', href=True):
            full_link = urljoin("https://www.roseltorg.ru", a['href'])
            parsed = urlparse(full_link)
            if parsed.netloc == "www.roseltorg.ru" and ('/knowledge_db' in parsed.path or '/azbuka-zakupok' in parsed.path):
                # Clean URL anchors & parameters
                clean_url = f"https://{parsed.netloc}{parsed.path}"
                if clean_url not in visited_urls and clean_url not in queue:
                    queue.append(clean_url)
        
        # Extract title
        title_el = soup.find('h1')
        title = title_el.get_text(strip=True) if title_el else ""
        if not title and soup.title:
            title = soup.title.get_text(strip=True)
            
        # Extract main article container
        # Priority: field--name-body -> uc-ui__content-col -> article -> main
        body_container = soup.find(class_=re.compile(r'field--name-body'))
        if not body_container:
            body_container = soup.find(class_='uc-ui__content-col')
        if not body_container:
            body_container = soup.find('article')
        if not body_container:
            body_container = soup.find(class_=re.compile(r'content-wrapper'))

        if not body_container:
            continue

        raw_html = str(body_container)
        text_content = h2t.handle(raw_html).strip()
        
        # Filter out empty or nav-only pages
        if len(text_content) < 50:
            continue

        # Extract breadcrumbs / tags if available
        tags = [t.get_text(strip=True) for t in soup.find_all(class_=re.compile(r'tag'))]
        
        slug = parsed = urlparse(url).path.strip('/').replace('/', '_')
        if not slug:
            slug = "index"
            
        out_filename = f"{clean_filename(slug)}.txt"
        out_path = os.path.join(base_output_dir, out_filename)
        
        full_article_text = f"SOURCE URL: {url}\nTITLE: {title}\n"
        if tags:
            full_article_text += f"TAGS: {', '.join(tags)}\n"
        full_article_text += f"{'='*60}\n\n{text_content}\n"
        
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(full_article_text)
            
        scraped_articles.append({
            "url": url,
            "title": title,
            "filename": out_filename,
            "length": len(text_content),
            "text": full_article_text
        })

    except Exception as e:
        print(f"Error scraping {url}: {e}")

print(f"\nFinished crawling! Successfully scraped {len(scraped_articles)} articles.")

# Save combined merged file
print(f"Saving merged knowledge base file to {merged_file_path}...")
with open(merged_file_path, "w", encoding="utf-8") as f:
    f.write("========================================================\n")
    f.write("ROSELTORG KNOWLEDGE BASE - FULL COMPLETE EXPORT (TXT)\n")
    f.write(f"Total Articles: {len(scraped_articles)}\n")
    f.write("========================================================\n\n")
    
    for item in scraped_articles:
        f.write(item["text"])
        f.write("\n\n" + "#"*80 + "\n\n")

print("Merged file saved successfully!")
