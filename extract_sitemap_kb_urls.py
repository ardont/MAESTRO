import requests
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

kb_urls = set()

# 1. Parse sitemaps
for page_num in range(1, 20):
    sitemap_url = f"https://www.roseltorg.ru/sitemap.xml?page={page_num}"
    try:
        r = requests.get(sitemap_url, headers=headers, timeout=10)
        if r.status_code != 200:
            print(f"Page {page_num} returned status {r.status_code}, stopping sitemap scan.")
            break
        
        # Parse XML
        root = ET.fromstring(r.content)
        # sitemap namespace usually http://www.sitemaps.org/schemas/sitemap/0.9
        for elem in root.iter('{http://www.sitemaps.org/schemas/sitemap/0.9}loc'):
            url = elem.text.strip()
            if '/knowledge_db' in url or '/azbuka-zakupok' in url:
                kb_urls.add(url)
        print(f"Sitemap page {page_num}: total kb_urls found so far = {len(kb_urls)}")
    except Exception as e:
        print(f"Sitemap page {page_num} error: {e}")
        break

print(f"\nFound {len(kb_urls)} knowledge_db URLs from sitemaps.")

# 2. Let's sample first 10 URLs
print("\nSample URLs from sitemap:")
for u in sorted(list(kb_urls))[:20]:
    print(" ", u)
