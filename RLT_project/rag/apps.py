from django.apps import AppConfig


class RagConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'rag'

    def ready(self):
        # Глобальная предзагрузка моделей при запуске Django-сервера
        import os
        import sys
        
        # Пропускаем вспомогательные команды управления (миграции, статика и т.д.)
        skip_commands = ['makemigrations', 'migrate', 'collectstatic', 'check', 'showmigrations']
        if any(cmd in sys.argv for cmd in skip_commands):
            return

        # При runserver выполняется два процесса (монитор и воркер). Загружаем только в воркере (RUN_MAIN=true)
        if os.environ.get('RUN_MAIN') == 'true' or 'runserver' not in sys.argv:
            try:
                print("\n" + "=" * 60)
                print("[RAG STARTUP] Инициализация ML-моделей (GPU/CUDA)...")
                from .indexer.embedder import get_embedder, get_sparse_embedder
                dense = get_embedder()
                sparse = get_sparse_embedder()
                print(f"[RAG STARTUP] Dense Embedder готов: device={dense.device}")
                print(f"[RAG STARTUP] Sparse BM25 Embedder готов")
                print("=" * 60 + "\n")
            except Exception as e:
                print(f"[RAG STARTUP WARNING] Предзагрузка моделей завершилась с ошибкой: {e}")
