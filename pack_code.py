import os
import zipfile

def create_code_zip():
    zip_path = "code_only.zip"
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        # Добавляем основные файлы
        for f in ["Dockerfile", "docker-compose.yml", "docker-compose.mac.yml", "requirements.txt", "requirements_mac.txt", "run_mac.sh"]:
            if os.path.exists(f):
                zipf.write(f)
        
        # Рекурсивно добавляем только нужные папки, исключая json, csv и картинки
        for root, dirs, files in os.walk("RLT_project"):
            # Пропускаем папки с кэшем
            if "__pycache__" in root or ".pytest_cache" in root or "qdrant_storage" in root:
                continue
                
            for file in files:
                ext = file.split('.')[-1].lower()
                # Берем только код и шаблоны, игнорируем тяжелые данные
                if ext in ["py", "html", "css", "js"]:
                    file_path = os.path.join(root, file)
                    zipf.write(file_path)

if __name__ == "__main__":
    create_code_zip()
    print("Создан архив code_only.zip только с исходным кодом!")
