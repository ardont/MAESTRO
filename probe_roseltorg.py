import requests
from bs4 import BeautifulSoup

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

url = "https://www.roseltorg.ru/knowledge_db"
try:
    resp = requests.get(url, headers=headers, timeout=15)
    print(f"Status Code: {resp.status_code}")
    print(f"Final URL: {resp.url}")
    soup = BeautifulSoup(resp.text, 'html.parser')
    
    # Print page title
    print(f"Title: {soup.title.string if soup.title else 'No title'}")
    
    # Find links
    links = soup.find_all('a', href=True)
    kb_links = [l['href'] for l in links if '/knowledge_db' in l['href'] or '/knowledge' in l['href'] or '/faq' in l['href'] or '/help' in l['href']]
    print(f"Total links: {len(links)}, KB related links: {len(kb_links)}")
    
    for l in kb_links[:30]:
        print("  ", l)
        
    # Check if there are sitemaps or main navigation categories
    all_links = set([l['href'] for l in links])
    print("\nSample internal links:")
    for l in list(all_links)[:40]:
        print("  ", l)
        
except Exception as e:
    print(f"Error fetching URL: {e}")
