# -*- coding: utf-8 -*-

import os
from datetime import datetime


class ImportLogger:
    def __init__(self):
        self.folder = os.path.join(os.path.expanduser("~"), "WellImporterLogs")
        os.makedirs(self.folder, exist_ok=True)
        self.file_path = os.path.join(self.folder, "import.log")

    def write(self, text):
        with open(self.file_path, "a", encoding="utf-8") as file:
            file.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | {text}\n")
