import os
import json
import httpx
import urllib.parse
import fitz # PyMuPDF

def download_and_parse_pdf(url, output_dir):
    filename = urllib.parse.unquote(url.split('/')[-1])
    local_path = os.path.join(output_dir, filename)
    
    # Download
    print(f"Скачивание {filename}...")
    try:
        with httpx.Client(timeout=30) as client:
            r = client.get(url)
            if r.status_code == 200:
                with open(local_path, 'wb') as f:
                    f.write(r.content)
            else:
                print(f"Ошибка {r.status_code} при скачивании {url}")
                return None
    except Exception as e:
        print(f"Ошибка при скачивании {url}: {e}")
        return None

    # Parse
    print(f"Парсинг {filename}...")
    try:
        doc = fitz.open(local_path)
        text = ""
        for page in doc:
            text += page.get_text()
        return text
    except Exception as e:
        print(f"Ошибка при парсинге {filename}: {e}")
        return None

def main():
    # Links we found
    pdf_links = [
        "https://zakupki.mos.ru/static/media/offer_yml_sku_howto.6a3b8d81.pdf",
        "https://zakupki.mos.ru/static/media/yml_instruction.1510c09b.pdf",
        "https://zakupki.mos.ru/cms/Media/docs/%D0%98%D0%BD%D1%81%D1%82%D1%80%D1%83%D0%BA%D1%86%D0%B8%D1%8F%20%D0%BF%D0%BE%20%D1%80%D0%B5%D0%B3%D0%B8%D1%81%D1%82%D1%80%D0%B0%D1%86%D0%B8%D0%B8%20%D0%BD%D0%B0%20%D0%9F%D0%BE%D1%80%D1%82%D0%B0%D0%BB%D0%B5.pdf"
    ]
    
    output_dir = os.path.join("dataset", "pdfs")
    os.makedirs(output_dir, exist_ok=True)
    
    parsed_data = []
    
    for url in pdf_links:
        text = download_and_parse_pdf(url, output_dir)
        if text:
            filename = urllib.parse.unquote(url.split('/')[-1])
            parsed_data.append({
                "url": url,
                "filename": filename,
                "content": text
            })
            
    out_file = os.path.join("dataset", "kb_pdfs.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(parsed_data, f, ensure_ascii=False, indent=2)
    print(f"Сохранено {len(parsed_data)} PDF документов в {out_file}")

if __name__ == "__main__":
    main()
