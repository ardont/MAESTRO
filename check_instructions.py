import os
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

url = "https://www.roseltorg.ru/knowledge_db/docs/documents"
try:
    r = requests.get(url, headers=headers, timeout=10)
    print(f"Status Code: {r.status_code}")
    soup = BeautifulSoup(r.text, 'html.parser')
    
    doc_links = []
    for a in soup.find_all('a', href=True):
        href = a['href']
        if any(href.lower().endswith(ext) for ext in ['.pdf', '.docx', '.doc', '.xlsx', '.xls', '.pptx']):
            doc_links.append((a.get_text(strip=True), urljoin(url, href)))
        elif '/instr' in href or '/docs' in href:
            doc_links.append((a.get_text(strip=True), urljoin(url, href)))
            
    print(f"Found {len(doc_links)} instruction/document links:")
    for title, link in doc_links[:30]:
        print(f" - {title}: {link}")
except Exception as e:
    print(f"Error checking instructions page: {e}")
