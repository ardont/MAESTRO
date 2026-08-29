import json
from bs4 import BeautifulSoup
import os

def clean_html(html_content):
    if not html_content:
        return ""
    soup = BeautifulSoup(html_content, 'html.parser')
    return soup.get_text(separator='\n', strip=True)

def determine_doc_type(title, text):
    title_lower = title.lower()
    text_lower = text[:500].lower()
    if "закон" in title_lower or "фз" in title_lower or "регламент" in title_lower:
        return "legislation"
    if "статья " in text_lower and ("федеральный" in text_lower or "кодекс" in text_lower):
         return "legislation"
    return "instruction"

def determine_category(title, text):
    content = (title + " " + text[:500]).lower()
    if "эцп" in content or "криптопро" in content or "мчд" in content:
        return "ecp_mchd"
    if "44-фз" in content or "44 фз" in content:
        return "44fz"
    if "223-фз" in content or "223 фз" in content:
        return "223fz"
    if "регистрация" in content or "регистрации" in content:
        return "registration"
    if "гарантия" in content or "услуг" in content:
        return "services"
    return "kb_article"

def main():
    input_file = os.path.join(os.path.dirname(__file__), '..', 'dataset', 'kb_graphql.json')
    output_file = os.path.join(os.path.dirname(__file__), '..', 'dataset', 'kb_clean.json')
    
    with open(input_file, 'r', encoding='utf-8') as f:
        pages = json.load(f)
        
    cleaned_dataset = []
    
    for page in pages:
        title = page.get('displayText', 'Без заголовка')
        html_content = page.get('content', {}).get('html', '')
        
        text_content = clean_html(html_content)
        
        if len(text_content) < 10:
            continue
            
        doc_type = determine_doc_type(title, text_content)
        category = determine_category(title, text_content)
        
        cleaned_dataset.append({
            "file_name": page.get('contentItemId', ''),
            "title": title,
            "text": text_content,
            "url": f"https://zakupki.mos.ru/knowledgebase/article/details/cms/{page.get('contentItemId', '')}",
            "doc_type": doc_type,
            "category": category
        })
        
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(cleaned_dataset, f, ensure_ascii=False, indent=2)
        
    print(f"Очистка завершена. Сохранено {len(cleaned_dataset)} чистых статей в {output_file}")

if __name__ == "__main__":
    main()
