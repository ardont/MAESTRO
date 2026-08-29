import json
import os
from pathlib import Path

def load_all_documents():
    """
    Загружает все документы из датасета (dataset/kb_clean.json)
    и возвращает список словарей, готовых для чанкинга.
    
    Ожидаемый формат словаря на выходе:
    {
        "text": <Текст документа>,
        "title": <Название>,
        "url": <URL>,
        "category": <Категория (например, "kb_article")>,
        "doc_type": <"instruction" или "legislation">,
        "file_name": <ID документа или имя файла>
    }
    """
    base_dir = Path(__file__).resolve().parent.parent.parent.parent
    dataset_file = base_dir / "dataset" / "kb_clean.json"
    
    if not dataset_file.exists():
        print(f"[ОШИБКА] Файл датасета не найден: {dataset_file}")
        return []
        
    try:
        with open(dataset_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        # Убедимся, что формат верный
        documents = []
        for item in data:
            # Маппинг полей из JSON в нужный формат для чанкера
            doc = {
                "text": item.get("text", ""),
                "title": item.get("title", "Без названия"),
                "url": item.get("url", ""),
                "category": item.get("category", "kb_article"),
                "doc_type": item.get("doc_type", "instruction"),
                "file_name": item.get("file_name", "")
            }
            if doc["text"]:
                documents.append(doc)
                
        print(f"[OK] Успешно загружено {len(documents)} документов из {dataset_file.name}")
        return documents
    except Exception as e:
        print(f"[ОШИБКА] Ошибка при чтении файла датасета: {e}")
        return []

if __name__ == "__main__":
    docs = load_all_documents()
    if docs:
        print(f"Первый документ: {docs[0]['title']} (Тип: {docs[0]['doc_type']})")
