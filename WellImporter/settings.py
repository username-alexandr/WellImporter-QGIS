# -*- coding: utf-8 -*-

from qgis.PyQt.QtCore import QSettings


class PluginSettings:
    PREFIX = "WellImporter"

    def load(self):
        settings = QSettings()
        return {
            "year": settings.value(f"{self.PREFIX}/year", "2024"),
            "area": settings.value(f"{self.PREFIX}/area", 33.0, type=float),
            "point_layer": settings.value(f"{self.PREFIX}/point_layer", "Скважины солевая съёмка"),
            "polygon_layer": settings.value(f"{self.PREFIX}/polygon_layer", "Площадные круги"),
            "skip_duplicates": settings.value(f"{self.PREFIX}/skip_duplicates", True, type=bool),
        }

    def save(self, year, area, point_layer, polygon_layer, skip_duplicates):
        settings = QSettings()
        settings.setValue(f"{self.PREFIX}/year", year)
        settings.setValue(f"{self.PREFIX}/area", area)
        settings.setValue(f"{self.PREFIX}/point_layer", point_layer)
        settings.setValue(f"{self.PREFIX}/polygon_layer", polygon_layer)
        settings.setValue(f"{self.PREFIX}/skip_duplicates", skip_duplicates)
