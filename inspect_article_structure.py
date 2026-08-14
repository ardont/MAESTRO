import requests
from bs4 import BeautifulSoup
import html2text

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

test_urls = [
    "https://www.roseltorg.ru/knowledge_db/registration/article/eis",
    "https://www.roseltorg.ru/knowledge_db/systems/instr/registraciya-v-roseltorgid",
    "https://www.roseltorg.ru/knowledge_db/44fz/instr/osnovnye-shagi-po-rabote-v-sekcii-gosudarstvennye-i-municipalnye-zakupki-po-44fz"
]

h = html2text.HTML2Text()
h.ignore_links = False
h.ignore_images = True
h.ignore_emphasis = False

for u in test_urls:
    r = requests.get(u, headers=headers, timeout=10)
    soup = BeautifulSoup(r.text, 'html.parser')
    
    # Try finding main container
    main_el = soup.find('main') or soup.find('article') or soup.find(class_='content') or soup.find(class_='region-content')
    title_el = soup.find('h1')
    title = title_el.get_text(strip=True) if title_el else "No title"
    
    print("========================================")
    print(f"URL: {u}")
    print(f"Title: {title}")
    
    if main_el:
        # Convert to text
        text = h.handle(str(main_el))
        print("Text snippet (first 500 chars):")
        print(text[:500])
    else:
        print("Main container not found, using body snippet:")
        print(soup.get_text()[:500])
