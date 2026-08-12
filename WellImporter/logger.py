# -*- coding: utf-8 -*-

import os
from datetime import datetime


class ImportLogger:
    """Модуль журналирования импорта в файл ~/WellImporterLogs/import.log."""

    def __init__(self):
        """Создаёт папку и путь к файлу журнала."""
        self.folder = os.path.join(os.path.expanduser("~"), "WellImporterLogs")
        os.makedirs(self.folder, exist_ok=True)
        self.file_path = os.path.join(self.folder, "import.log")

    def write(self, text):
        """Добавляет строку в журнал."""
        with open(self.file_path, "a", encoding="utf-8") as file:
            file.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | {text}\n")
