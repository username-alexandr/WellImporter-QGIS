# -*- coding: utf-8 -*-

from datetime import datetime
import json
from qgis.PyQt.QtCore import QSettings


class PluginSettings:
    """Сохранение настроек, папок, обязательных полей и параметров интерфейса."""

    PREFIX = "WellImporter"

    def __init__(self):
        self.settings = QSettings()

    def year(self):
        return int(self.settings.value(f"{self.PREFIX}/year", datetime.now().year, type=int))

    def area(self):
        return float(self.settings.value(f"{self.PREFIX}/area", 33.0, type=float))

    def point_layer_name(self):
        return self.settings.value(f"{self.PREFIX}/point_layer_name", "", type=str)

    def polygon_layer_name(self):
        return self.settings.value(f"{self.PREFIX}/polygon_layer_name", "", type=str)

    def coordinate_mode(self):
        return self.settings.value(f"{self.PREFIX}/coordinate_mode", "AUTO", type=str)

    def source_crs(self):
        return self.settings.value(f"{self.PREFIX}/source_crs", "EPSG:4326", type=str)

    def skip_duplicates(self):
        return self._bool(f"{self.PREFIX}/skip_duplicates", True)

    def auto_current_year(self):
        return self._bool(f"{self.PREFIX}/auto_current_year", True)

    def last_folder(self):
        return self.settings.value(f"{self.PREFIX}/last_folder", "", type=str)

    def favorite_folders(self):
        return self._json_list(f"{self.PREFIX}/favorite_folders", [])

    def required_point_fields(self):
        return self._json_list(f"{self.PREFIX}/required_point_fields", ["Номер скважины", "Год"])

    def required_polygon_fields(self):
        return self._json_list(f"{self.PREFIX}/required_polygon_fields", ["Номер скважины"])

    def parcel_layer_name(self):
        return self.settings.value(f"{self.PREFIX}/parcel_layer_name", "", type=str)

    def parcel_label_field(self):
        return self.settings.value(f"{self.PREFIX}/parcel_label_field", "", type=str)

    def cadastral_field(self):
        return self.settings.value(f"{self.PREFIX}/cadastral_field", "", type=str)

    def parcel_group_path(self):
        """Путь выбранной группы земельных участков в дереве слоёв QGIS."""
        return self.settings.value(f"{self.PREFIX}/parcel_group_path", "", type=str)

    def save(self, year, area, point_layer_name, polygon_layer_name, skip_duplicates=True,
             coordinate_mode="AUTO", source_crs="EPSG:4326", auto_current_year=True):
        self.settings.setValue(f"{self.PREFIX}/year", int(year))
        self.settings.setValue(f"{self.PREFIX}/area", float(area))
        self.settings.setValue(f"{self.PREFIX}/point_layer_name", point_layer_name)
        self.settings.setValue(f"{self.PREFIX}/polygon_layer_name", polygon_layer_name)
        self.settings.setValue(f"{self.PREFIX}/skip_duplicates", bool(skip_duplicates))
        self.settings.setValue(f"{self.PREFIX}/coordinate_mode", str(coordinate_mode))
        self.settings.setValue(f"{self.PREFIX}/source_crs", str(source_crs))
        self.settings.setValue(f"{self.PREFIX}/auto_current_year", bool(auto_current_year))

    def set_last_folder(self, folder):
        self.settings.setValue(f"{self.PREFIX}/last_folder", str(folder or ""))

    def set_favorite_folders(self, folders):
        self.settings.setValue(f"{self.PREFIX}/favorite_folders", json.dumps(list(folders), ensure_ascii=False))

    def set_required_fields(self, point_fields, polygon_fields):
        self.settings.setValue(f"{self.PREFIX}/required_point_fields", json.dumps(list(point_fields), ensure_ascii=False))
        self.settings.setValue(f"{self.PREFIX}/required_polygon_fields", json.dumps(list(polygon_fields), ensure_ascii=False))

    def set_parcel_settings(self, layer_name, label_field, cadastral_field):
        self.settings.setValue(f"{self.PREFIX}/parcel_layer_name", str(layer_name or ""))
        self.settings.setValue(f"{self.PREFIX}/parcel_label_field", str(label_field or ""))
        self.settings.setValue(f"{self.PREFIX}/cadastral_field", str(cadastral_field or ""))

    def set_parcel_group_path(self, group_path):
        self.settings.setValue(f"{self.PREFIX}/parcel_group_path", str(group_path or "").strip())
        self.settings.sync()

    def _bool(self, key, default):
        value = self.settings.value(key, default)
        if isinstance(value, bool):
            return value
        return str(value).lower() in ("true", "1", "yes", "да")

    def _json_list(self, key, default):
        raw = self.settings.value(key, "", type=str)
        if not raw:
            return list(default)
        try:
            value = json.loads(raw)
            return list(value) if isinstance(value, list) else list(default)
        except Exception:
            return list(default)
