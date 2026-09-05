from django.apps import AppConfig
import os
import threading
import subprocess
from chat.kafka.subscribers import llm_request_handler

class ChatConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'chat'

    def ready(self):
        if os.environ.get('RUN_MAIN') == 'true':
            threading.Thread(target=self._run_broker, daemon=True).start()

    def _run_broker(self):
        subprocess.Popen([
            'faststream', 'run',
            'chat.kafka.broker:app',
            '--workers', '5'
        ])