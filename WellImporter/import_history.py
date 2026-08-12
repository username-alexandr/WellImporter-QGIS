# -*- coding: utf-8 -*-

import json
from qgis.PyQt.QtCore import QSettings


class ImportHistory:
    """
    Хранилище истории импортов Well Importer.

    История сохраняется в QSettings профиля QGIS и содержит сведения о
    партии импорта, слоях, количестве объектов, проверке качества и отмене.
    """

    KEY = "WellImporter/import_history_v1"
    MAX_ITEMS = 100

    def __init__(self):
        """Создаёт доступ к настройкам QGIS."""
        self.settings = QSettings()

    def items(self):
        """Возвращает историю от новой записи к старой."""
        raw = self.settings.value(self.KEY, "", type=str)
        if not raw:
            return []
        try:
            data = json.loads(raw)
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def add(self, entry):
        """Добавляет запись в начало истории."""
        data = self.items()
        data.insert(0, dict(entry))
        self.settings.setValue(self.KEY, json.dumps(data[:self.MAX_ITEMS], ensure_ascii=False))

    def last_active(self):
        """Возвращает последнюю рабочую партию, которая не отменена и не архивирована."""
        for item in self.items():
            if (not item.get("undone", False)
                    and not item.get("archived", False)
                    and item.get("batch_id")):
                return item
        return None

    def mark_undone(self, batch_id):
        """Помечает партию как отменённую."""
        data = self.items()
        for item in data:
            if item.get("batch_id") == batch_id:
                item["undone"] = True
                break
        self.settings.setValue(self.KEY, json.dumps(data, ensure_ascii=False))

    def update_validation(self, batch_id, validation):
        """Обновляет результат проверки качества партии."""
        data = self.items()
        for item in data:
            if item.get("batch_id") == batch_id:
                item["validation"] = validation
                break
        self.settings.setValue(self.KEY, json.dumps(data, ensure_ascii=False))

    def mark_archived(self, batch_ids, archive_path):
        """Помечает выбранные партии как перенесённые в архив."""
        batch_ids = {str(value) for value in batch_ids}
        data = self.items()
        from datetime import datetime
        archived_at = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        for item in data:
            if str(item.get("batch_id")) in batch_ids:
                item["archived"] = True
                item["archive_path"] = str(archive_path)
                item["archived_at"] = archived_at
        self.settings.setValue(self.KEY, json.dumps(data, ensure_ascii=False))
