# -*- coding: utf-8 -*-

import json
from qgis.PyQt.QtCore import QSettings


class ProfileManager:
    """Хранит именованные профили параметров Well Importer."""

    KEY = "WellImporter/profiles_json"
    ADD_PROFILE_LABEL = "+ Добавить профиль…"

    def __init__(self):
        self.settings = QSettings()
        self._ensure_default()

    def _load(self):
        raw = self.settings.value(self.KEY, "", type=str)
        if not raw:
            return {}
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _save(self, data):
        self.settings.setValue(self.KEY, json.dumps(data, ensure_ascii=False))

    def _ensure_default(self):
        data = self._load()
        if "Солевая съёмка 33 га" not in data:
            data["Солевая съёмка 33 га"] = {
                "area": 33.0,
                "coordinate_mode": "AUTO",
                "source_crs": "EPSG:4326",
                "skip_duplicates": True,
                "auto_current_year": True,
                "point_layer_name": "Скважины солевая съёмка",
                "polygon_layer_name": "Площадные круги",
                "required_point_fields": ["Номер скважины", "Год"],
                "required_polygon_fields": ["Номер скважины"],
            }
            self._save(data)

    def names(self):
        return sorted(self._load().keys(), key=lambda value: value.lower())

    def get(self, name):
        return dict(self._load().get(name, {}))

    def save(self, name, profile):
        name = str(name).strip()
        if not name:
            raise Exception("Название профиля не может быть пустым.")
        if name == self.ADD_PROFILE_LABEL:
            raise Exception("Это название зарезервировано интерфейсом Well Importer.")
        data = self._load()
        data[name] = dict(profile)
        self._save(data)

    def exists(self, name):
        """Проверяет наличие профиля по точному названию."""
        return str(name).strip() in self._load()

    def delete(self, name):
        if name == "Солевая съёмка 33 га":
            raise Exception("Встроенный профиль «Солевая съёмка 33 га» удалить нельзя.")
        data = self._load()
        data.pop(name, None)
        self._save(data)
