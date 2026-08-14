import requests

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

for url in ["https://www.roseltorg.ru/robots.txt", "https://www.roseltorg.ru/sitemap.xml"]:
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        print(f"--- {url} (Status: {resp.status_code}) ---")
        print(resp.text[:1000])
    except Exception as e:
        print(f"Error {url}: {e}")
