"""
Модуль fetch_graphql.py

Отвечает за сбор "сырых" статей базы знаний напрямую из закрытого API (GraphQL) 
Портала Поставщиков (zakupki.mos.ru). Скачивает сотни статей за 1 секунду.
Сохраняет данные в формате JSON для дальнейшей очистки.
"""
import httpx
import json

def fetch_kb():
    url = "https://zakupki.mos.ru/cms/api/graphql"
    query = """
    {
      contentPage(first: 1000) {
        contentItemId
        displayText
        content { html }
      }
    }
    """
    
    headers = {
        'content-type': 'application/json',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36'
    }
    
    try:
        response = httpx.post(url, json={'query': query}, headers=headers, timeout=10)
        data = response.json()
        
        pages = data.get('data', {}).get('contentPage', [])
        print(f"Loaded {len(pages)} pages from GraphQL.")
        
        if pages:
            print("First item sample:")
            print(f"Title: {pages[0]['displayText']}")
            print(f"ID: {pages[0]['contentItemId']}")
            print(f"HTML size: {len(pages[0].get('content', {}).get('html', ''))} chars")
            
        with open('dataset/kb_graphql.json', 'w', encoding='utf-8') as f:
            json.dump(pages, f, ensure_ascii=False, indent=2)
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    fetch_kb()
