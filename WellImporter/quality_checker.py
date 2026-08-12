# -*- coding: utf-8 -*-

from dataclasses import dataclass
from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsDistanceArea,
    QgsPointXY,
    QgsProject,
)

from .severity import Severity
from .well_number_field import well_number_field_name


@dataclass
class CircleCheckResult:
    number: str
    area_m2: float
    expected_area_m2: float
    area_deviation_pct: float
    center_distance_m: float
    area_ok: bool
    center_ok: bool
    severity: str
    message: str


class QualityChecker:
    """Проверяет площадь кругов, их центрирование и наличие пар точка/круг."""

    BATCH_FIELD = "WI_BATCH"
    NUMBER_FIELDS = ("Номер скважины",)
    WGS84 = QgsCoordinateReferenceSystem("EPSG:4326")

    def __init__(self):
        self.project = QgsProject.instance()

    def validate_batch(self, point_layer, polygon_layer, batch_id, expected_area_ha,
                       area_tolerance_pct=2.0, center_tolerance_m=5.0):
        points = self._batch_features(point_layer, batch_id)
        polygons = self._batch_features(polygon_layer, batch_id)
        return self._validate_features(
            point_layer, polygon_layer, points, polygons, expected_area_ha,
            area_tolerance_pct, center_tolerance_m, batch_id=batch_id,
        )

    def validate_all(self, point_layer, polygon_layer, expected_area_ha,
                     area_tolerance_pct=2.0, center_tolerance_m=5.0):
        """Проверяет все пары скважина/круг выбранных слоёв."""
        return self._validate_features(
            point_layer, polygon_layer,
            list(point_layer.getFeatures()), list(polygon_layer.getFeatures()),
            expected_area_ha, area_tolerance_pct, center_tolerance_m,
            batch_id="ALL",
        )

    def _validate_features(self, point_layer, polygon_layer, points, polygons,
                           expected_area_ha, area_tolerance_pct, center_tolerance_m,
                           batch_id=""):
        point_field = self._number_field(point_layer)
        polygon_field = self._number_field(polygon_layer)
        if not point_field or not polygon_field:
            return {
                "batch_id": batch_id,
                "total": 0,
                "ok": 0,
                "failed": 1,
                "area_tolerance_pct": area_tolerance_pct,
                "center_tolerance_m": center_tolerance_m,
                "severity_counts": Severity.counts([Severity.CRITICAL]),
                "highest_severity": Severity.CRITICAL,
                "items": [{
                    "number": "",
                    "area_m2": 0.0,
                    "expected_area_m2": float(expected_area_ha) * 10000.0,
                    "area_deviation_pct": 100.0,
                    "center_distance_m": 0.0,
                    "area_ok": False,
                    "center_ok": False,
                    "severity": Severity.CRITICAL,
                    "message": "В одном из слоёв отсутствует поле «Номер скважины».",
                }],
            }

        point_by_number = {self._key(feature[point_field]): feature for feature in points}
        polygon_by_number = {self._key(feature[polygon_field]): feature for feature in polygons}
        display_number = {}
        for feature in points:
            display_number[self._key(feature[point_field])] = str(feature[point_field]).strip()
        for feature in polygons:
            display_number.setdefault(self._key(feature[polygon_field]), str(feature[polygon_field]).strip())
        numbers = sorted(set(point_by_number) | set(polygon_by_number))

        area_meter = QgsDistanceArea()
        area_meter.setSourceCrs(polygon_layer.crs(), self.project.transformContext())
        area_meter.setEllipsoid("WGS84")

        distance_meter = QgsDistanceArea()
        distance_meter.setSourceCrs(self.WGS84, self.project.transformContext())
        distance_meter.setEllipsoid("WGS84")

        point_to_wgs = QgsCoordinateTransform(point_layer.crs(), self.WGS84, self.project)
        polygon_to_wgs = QgsCoordinateTransform(polygon_layer.crs(), self.WGS84, self.project)

        expected_m2 = float(expected_area_ha) * 10000.0
        items = []

        for key in numbers:
            number = display_number.get(key, key)
            point_feature = point_by_number.get(key)
            polygon_feature = polygon_by_number.get(key)
            if point_feature is None or polygon_feature is None:
                items.append(CircleCheckResult(
                    number, 0.0, expected_m2, 100.0, 0.0, False, False,
                    Severity.CRITICAL, "Не найдена парная точка или площадной круг"
                ))
                continue

            actual_area = abs(area_meter.measureArea(polygon_feature.geometry()))
            deviation_pct = (abs(actual_area - expected_m2) / expected_m2 * 100.0) if expected_m2 else 100.0

            point = point_feature.geometry().asPoint()
            centroid = polygon_feature.geometry().centroid().asPoint()
            point_wgs = point_to_wgs.transform(QgsPointXY(point))
            centroid_wgs = polygon_to_wgs.transform(QgsPointXY(centroid))
            center_distance = distance_meter.measureLine(point_wgs, centroid_wgs)

            area_ok = deviation_pct <= float(area_tolerance_pct)
            center_ok = center_distance <= float(center_tolerance_m)
            severity = self._severity_for(deviation_pct, center_distance, area_tolerance_pct, center_tolerance_m)

            messages = []
            if not area_ok:
                messages.append(f"площадь отличается на {deviation_pct:.2f}%")
            if not center_ok:
                messages.append(f"центр смещён на {center_distance:.2f} м")
            message = "OK" if not messages else "; ".join(messages)

            items.append(CircleCheckResult(
                number, actual_area, expected_m2, deviation_pct,
                center_distance, area_ok, center_ok, severity, message
            ))

        ok_count = sum(1 for item in items if item.area_ok and item.center_ok)
        severity_counts = Severity.counts(item.severity for item in items)
        highest = Severity.max(*(item.severity for item in items)) if items else Severity.INFO
        return {
            "batch_id": batch_id,
            "total": len(items),
            "ok": ok_count,
            "failed": len(items) - ok_count,
            "area_tolerance_pct": area_tolerance_pct,
            "center_tolerance_m": center_tolerance_m,
            "severity_counts": severity_counts,
            "highest_severity": highest,
            "items": [item.__dict__ for item in items],
        }

    def _severity_for(self, deviation_pct, center_distance, area_tolerance_pct, center_tolerance_m):
        if deviation_pct <= float(area_tolerance_pct) and center_distance <= float(center_tolerance_m):
            return Severity.INFO
        if deviation_pct > 15.0 or center_distance > 50.0:
            return Severity.CRITICAL
        if deviation_pct > 5.0 or center_distance > 15.0:
            return Severity.ERROR
        return Severity.WARNING

    def _batch_features(self, layer, batch_id):
        if layer.fields().indexFromName(self.BATCH_FIELD) < 0:
            return []
        return [feature for feature in layer.getFeatures() if str(feature[self.BATCH_FIELD]) == str(batch_id)]

    def _number_field(self, layer):
        return well_number_field_name(layer)

    def _key(self, value):
        text = str(value).strip().lower().replace("№", "").replace(" ", "")
        if text.isdigit():
            return text.lstrip("0") or "0"
        return text
