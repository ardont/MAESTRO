import httpx
import json
import os

def main():
    base_url = "https://zakupki.mos.ru/newapi/api/KnowledgeBase/GetArticlesBySectionType"
    sections = ["supplier", "customer", "general", "instruction"]
    
    all_articles = []
    
    for section in sections:
        print(f"Загрузка раздела {section}...")
        try:
            r = httpx.get(base_url, params={"sectionType": section}, timeout=30)
            if r.status_code == 200:
                data = r.json()
                for category in data:
                    category_name = category.get("categoryName")
                    for service in category.get("articlesByService", []):
                        service_name = service.get("serviceName")
                        for article in service.get("articles", []):
                            # Convert relative image paths to absolute
                            detail_text = article.get("detailText") or ""
                            detail_text = detail_text.replace('src="/', 'src="https://zakupki.mos.ru/')
                            detail_text = detail_text.replace("src='/", "src='https://zakupki.mos.ru/")
                            
                            all_articles.append({
                                "id": article.get("id"),
                                "staticId": article.get("staticId"),
                                "title": article.get("largeName"),
                                "html_content": detail_text,
                                "section": section,
                                "category": category_name,
                                "service": service_name,
                                "url": f"https://zakupki.mos.ru/knowledgebase/article/{article.get('staticId')}"
                            })
            else:
                print(f"Ошибка HTTP {r.status_code} для раздела {section}")
        except Exception as e:
            print(f"Ошибка загрузки {section}: {e}")
            
    print(f"Всего загружено {len(all_articles)} статей.")
    
    out_file = os.path.join(os.path.dirname(__file__), "..", "kb_all_articles.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(all_articles, f, ensure_ascii=False, indent=2)
    print(f"Сохранено в {out_file}")

if __name__ == "__main__":
    main()
