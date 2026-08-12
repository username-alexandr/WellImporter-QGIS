# -*- coding: utf-8 -*-

from dataclasses import dataclass
import math
from datetime import datetime
from uuid import uuid4

from qgis.core import QgsProject, QgsField, QgsFeature, QgsGeometry, QgsPointXY, QgsVectorLayerUtils
from qgis.PyQt.QtCore import QVariant

from .geometry import GeometryBuilder
from .importer import ClipboardImporter
from .logger import ImportLogger
from .progress import Progress
from .validator import Validator


@dataclass
class ImportResult:
    parsed_records: int = 0
    added_points: int = 0
    added_circles: int = 0
    skipped_duplicates: int = 0
    errors: int = 0
    log_file: str = ""


class ImportController:
    POINT_NUMBER_FIELD = "Номер скважины"
    POINT_YEAR_FIELD = "Год"
    POLYGON_NUMBER_FIELD = "Номер скважины"
    POLYGON_AREA_FIELD = "Площадь"

    def __init__(self, iface):
        self.iface = iface
        self.project = QgsProject.instance()
        self.importer = ClipboardImporter()
        self.geometry = GeometryBuilder()
        self.logger = ImportLogger()

    def execute(self, point_layer_id, polygon_layer_id, year, area, skip_duplicates=True):
        point_layer = self.project.mapLayer(point_layer_id)
        polygon_layer = self.project.mapLayer(polygon_layer_id)
        self._validate_layers(point_layer, polygon_layer)

        records = self.importer.parse_clipboard()
        if not records:
            raise Exception("Нет данных для импорта.")

        result = ImportResult(parsed_records=len(records), log_file=self.logger.file_path)
        validator = Validator(point_layer, self.POINT_NUMBER_FIELD)
        progress = Progress(self.iface, len(records), "Импорт скважин...")

        point_provider = point_layer.dataProvider()
        polygon_provider = polygon_layer.dataProvider()

        for index, record in enumerate(records, start=1):
            progress.set_value(index)
            if progress.was_canceled():
                self.logger.write("Импорт отменён пользователем.")
                break

            try:
                if skip_duplicates and validator.exists(record.number):
                    result.skipped_duplicates += 1
                    self.logger.write(f"Пропуск дубля: № {record.number}")
                    continue

                point_feature = self._make_point_feature(point_layer, record, year)
                circle_feature = self._make_circle_feature(polygon_layer, record, area)

                ok_points, _ = point_provider.addFeatures([point_feature])
                ok_polygons, _ = polygon_provider.addFeatures([circle_feature])

                if ok_points:
                    result.added_points += 1
                else:
                    raise Exception("Не удалось добавить точку.")

                if ok_polygons:
                    result.added_circles += 1
                else:
                    raise Exception("Не удалось добавить круг.")

                validator.add(record.number)
                self.logger.write(
                    f"Импортировано: № {record.number}; X={record.x}; Y={record.y}; год={year}; площадь={area}"
                )
            except Exception as exc:
                result.errors += 1
                self.logger.write(f"Ошибка строки {record.row}: {exc}")

        progress.close()
        point_layer.updateExtents()
        polygon_layer.updateExtents()
        point_layer.triggerRepaint()
        polygon_layer.triggerRepaint()
        self.iface.mapCanvas().refresh()

        return result

    def _make_point_feature(self, layer, record, year):
        feature = QgsVectorLayerUtils.createFeature(layer)
        feature.setGeometry(self.geometry.create_point(record.x, record.y))
        feature[self.POINT_NUMBER_FIELD] = record.number
        feature[self.POINT_YEAR_FIELD] = str(year)
        return feature

    def _make_circle_feature(self, layer, record, area):
        feature = QgsVectorLayerUtils.createFeature(layer)
        feature.setGeometry(self.geometry.create_circle(record.x, record.y, area))
        feature[self.POLYGON_NUMBER_FIELD] = record.number
        feature[self.POLYGON_AREA_FIELD] = float(area)
        return feature

    def _validate_layers(self, point_layer, polygon_layer):
        if point_layer is None:
            raise Exception("Не найден слой скважин.")
        if polygon_layer is None:
            raise Exception("Не найден слой площадных кругов.")

        point_fields = point_layer.fields().names()
        polygon_fields = polygon_layer.fields().names()

        for field in (self.POINT_NUMBER_FIELD, self.POINT_YEAR_FIELD):
            if field not in point_fields:
                raise Exception(f"В слое скважин отсутствует поле «{field}».")

        for field in (self.POLYGON_NUMBER_FIELD, self.POLYGON_AREA_FIELD):
            if field not in polygon_fields:
                raise Exception(f"В слое площадных кругов отсутствует поле «{field}».")
