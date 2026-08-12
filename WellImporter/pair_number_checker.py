# -*- coding: utf-8 -*-

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsDistanceArea,
    QgsPointXY,
    QgsProject,
)

from .severity import Severity
from .well_number_field import feature_well_number


class PairNumberConsistencyChecker:
    """Проверяет номер скважины у геометрически соответствующей точки и круга.

    Связь определяется независимо от номера: для каждого площадного круга
    ищется ближайшая точка бурения к его центру. Если центр круга находится
    внутри допустимой дистанции от точки, пара считается геометрически
    однозначной и её номера сравниваются. Это позволяет обнаруживать как раз
    тот класс ошибок, который невозможно найти сопоставлением только по номеру.
    """

    CATEGORY = "Несовпадение номера точки и круга"
    WGS84 = QgsCoordinateReferenceSystem("EPSG:4326")

    def __init__(self, max_center_distance_m=50.0):
        self.project = QgsProject.instance()
        self.max_center_distance_m = float(max_center_distance_m)

    def check(self, point_layer, polygon_layer):
        points = [
            feature for feature in point_layer.getFeatures()
            if feature.hasGeometry() and not feature.geometry().isEmpty()
        ]
        polygons = [
            feature for feature in polygon_layer.getFeatures()
            if feature.hasGeometry() and not feature.geometry().isEmpty()
        ]

        if not points or not polygons:
            return {
                "checked": 0,
                "mismatches": 0,
                "unresolved": len(polygons),
                "max_center_distance_m": self.max_center_distance_m,
                "items": [],
            }

        point_to_wgs = QgsCoordinateTransform(
            point_layer.crs(), self.WGS84, self.project
        )
        polygon_to_wgs = QgsCoordinateTransform(
            polygon_layer.crs(), self.WGS84, self.project
        )
        distance = QgsDistanceArea()
        distance.setSourceCrs(self.WGS84, self.project.transformContext())
        distance.setEllipsoid("WGS84")

        point_rows = []
        for feature in points:
            point = feature.geometry().asPoint()
            point_wgs = point_to_wgs.transform(QgsPointXY(point))
            point_rows.append((feature, point_wgs))

        checked = 0
        unresolved = 0
        items = []

        for polygon in polygons:
            centroid_geometry = polygon.geometry().centroid()
            if centroid_geometry.isEmpty():
                unresolved += 1
                continue
            centroid = centroid_geometry.asPoint()
            centroid_wgs = polygon_to_wgs.transform(QgsPointXY(centroid))

            nearest_feature = None
            nearest_distance = None
            for point_feature, point_wgs in point_rows:
                current_distance = float(distance.measureLine(centroid_wgs, point_wgs))
                if nearest_distance is None or current_distance < nearest_distance:
                    nearest_distance = current_distance
                    nearest_feature = point_feature

            if (
                nearest_feature is None
                or nearest_distance is None
                or nearest_distance > self.max_center_distance_m
            ):
                unresolved += 1
                continue

            checked += 1
            point_number = feature_well_number(
                nearest_feature, point_layer, ""
            ).strip()
            circle_number = feature_well_number(
                polygon, polygon_layer, ""
            ).strip()

            # Пустые номера отдельно контролируются обязательными атрибутами и
            # проверкой формата номера. Здесь фиксируем именно конфликт двух
            # заполненных значений.
            if not point_number or not circle_number or point_number == circle_number:
                continue

            items.append({
                "source": "pair_number_consistency",
                "category": self.CATEGORY,
                "layer_id": polygon_layer.id(),
                "layer_name": polygon_layer.name(),
                "feature_id": int(polygon.id()),
                "number": circle_number,
                "point_number": point_number,
                "circle_number": circle_number,
                "point_feature_id": int(nearest_feature.id()),
                "circle_feature_id": int(polygon.id()),
                "center_distance_m": float(nearest_distance),
                "severity": Severity.CRITICAL,
                "message": (
                    f"Критическое несовпадение номера: точка №{point_number}, "
                    f"площадной круг №{circle_number}; расстояние от точки до "
                    f"центра круга {nearest_distance:.2f} м."
                ),
            })

        return {
            "checked": checked,
            "mismatches": len(items),
            "unresolved": unresolved,
            "max_center_distance_m": self.max_center_distance_m,
            "items": items,
        }
