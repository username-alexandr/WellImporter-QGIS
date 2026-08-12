# -*- coding: utf-8 -*-

import math
import re
from dataclasses import dataclass, field

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsDistanceArea,
    QgsPointXY,
    QgsProject,
)

from .severity import Severity


@dataclass
class DuplicateCheck:
    """Результат интеллектуального поиска дублей для одной входной строки."""
    row: int
    number: str
    severity: str = Severity.INFO
    messages: list = field(default_factory=list)
    strong_duplicate: bool = False

    @property
    def message(self):
        return "; ".join(self.messages) if self.messages else "Дубли не обнаружены"


class DuplicateChecker:
    """
    Ищет дубли по нескольким признакам.

    Проверяются:
    - одинаковые номера;
    - номера, различающиеся только ведущими нулями;
    - одинаковые/очень близкие координаты;
    - близость новых точек к уже существующим скважинам в пределах 5 м;
    - дубли внутри самой импортируемой партии.
    """

    NUMBER_FIELD = "Номер скважины"
    WGS84 = QgsCoordinateReferenceSystem("EPSG:4326")

    def __init__(self):
        self.project = QgsProject.instance()
        self.distance = QgsDistanceArea()
        self.distance.setSourceCrs(self.WGS84, self.project.transformContext())
        self.distance.setEllipsoid("WGS84")

    def analyze(self, records, point_layer=None):
        """Возвращает DuplicateCheck для каждой входной строки."""
        results = [DuplicateCheck(i + 1, str(record.number)) for i, record in enumerate(records)]
        if not records:
            return results

        incoming = [
            {
                "row": index + 1,
                "number": str(record.number).strip(),
                "number_key": self._number_key(record.number),
                "lon": float(record.x),
                "lat": float(record.y),
            }
            for index, record in enumerate(records)
        ]

        self._check_incoming(incoming, results)
        if point_layer is not None and point_layer.isValid():
            existing = self._existing_points(point_layer)
            self._check_existing(incoming, existing, results)

        return results

    def count_flagged(self, checks):
        """Количество строк, где найден хотя бы один возможный дубль."""
        return sum(1 for item in checks if item.messages)

    def severity_counts(self, checks):
        """Количество результатов по уровням серьёзности."""
        return Severity.counts(item.severity for item in checks if item.messages)

    def _check_incoming(self, incoming, results):
        """Сравнивает строки текущей партии между собой."""
        for i in range(len(incoming)):
            left = incoming[i]
            for j in range(i + 1, len(incoming)):
                right = incoming[j]
                messages_left = []
                messages_right = []
                severity = Severity.INFO
                strong = False

                if left["number"] == right["number"]:
                    severity = Severity.max(severity, Severity.ERROR)
                    messages_left.append(f"тот же номер повторён в строке {right['row']}")
                    messages_right.append(f"тот же номер повторён в строке {left['row']}")
                    strong = True
                elif left["number_key"] and left["number_key"] == right["number_key"]:
                    severity = Severity.max(severity, Severity.WARNING)
                    messages_left.append(f"номер похож на строку {right['row']} (различие ведущих нулей/формата)")
                    messages_right.append(f"номер похож на строку {left['row']} (различие ведущих нулей/формата)")

                distance = self._distance_m(left["lon"], left["lat"], right["lon"], right["lat"])
                dist_severity, dist_text, dist_strong = self._distance_issue(distance, f"строка {right['row']}")
                if dist_text:
                    messages_left.append(dist_text)
                    messages_right.append(dist_text.replace(f"строка {right['row']}", f"строка {left['row']}"))
                    severity = Severity.max(severity, dist_severity)
                    strong = strong or dist_strong

                if messages_left:
                    self._merge(results[i], severity, messages_left, strong)
                    self._merge(results[j], severity, messages_right, strong)

    def _check_existing(self, incoming, existing, results):
        """Сравнивает входные точки с уже существующим слоем."""
        if not existing:
            return

        buckets = {}
        for item in existing:
            key = self._bucket(item["lon"], item["lat"])
            buckets.setdefault(key, []).append(item)

        by_number = {}
        by_key = {}
        for item in existing:
            by_number.setdefault(item["number"], []).append(item)
            if item["number_key"]:
                by_key.setdefault(item["number_key"], []).append(item)

        for index, record in enumerate(incoming):
            result = results[index]
            exact = by_number.get(record["number"], [])
            if exact:
                self._merge(
                    result, Severity.ERROR,
                    [f"номер уже существует в слое ({len(exact)} объект(а))"],
                    True,
                )
            elif record["number_key"] and record["number_key"] in by_key:
                examples = by_key[record["number_key"]][:2]
                sample = ", ".join(item["number"] for item in examples)
                self._merge(
                    result, Severity.WARNING,
                    [f"в слое есть эквивалентный номер после нормализации: {sample}"],
                    False,
                )

            nearby = []
            bx, by = self._bucket(record["lon"], record["lat"])
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    nearby.extend(buckets.get((bx + dx, by + dy), []))

            best = None
            for item in nearby:
                distance = self._distance_m(record["lon"], record["lat"], item["lon"], item["lat"])
                if distance <= 5.0 and (best is None or distance < best[0]):
                    best = (distance, item)
            if best:
                distance, item = best
                severity, text, strong = self._distance_issue(distance, f"существующая скважина №{item['number']}")
                if text:
                    self._merge(result, severity, [text], strong)

    def _existing_points(self, layer):
        """Получает существующие точки слоя в WGS84."""
        number_field = self.NUMBER_FIELD if layer.fields().indexFromName(self.NUMBER_FIELD) >= 0 else None

        transform = QgsCoordinateTransform(layer.crs(), self.WGS84, self.project)
        result = []
        for feature in layer.getFeatures():
            geometry = feature.geometry()
            if geometry is None or geometry.isEmpty():
                continue
            try:
                point = geometry.asPoint()
                wgs = transform.transform(QgsPointXY(point))
            except Exception:
                continue
            number = str(feature[number_field]).strip() if number_field else str(feature.id())
            result.append({
                "number": number,
                "number_key": self._number_key(number),
                "lon": float(wgs.x()),
                "lat": float(wgs.y()),
            })
        return result

    def _merge(self, result, severity, messages, strong):
        result.severity = Severity.max(result.severity, severity)
        result.strong_duplicate = result.strong_duplicate or bool(strong)
        for message in messages:
            if message not in result.messages:
                result.messages.append(message)

    def _distance_issue(self, distance, target):
        if distance <= 0.30:
            return Severity.CRITICAL, f"координаты практически совпадают с {target} ({distance:.2f} м)", True
        if distance <= 1.0:
            return Severity.ERROR, f"точка находится в {distance:.2f} м от {target}", True
        if distance <= 3.0:
            return Severity.WARNING, f"точка находится близко к {target}: {distance:.2f} м", False
        if distance <= 5.0:
            return Severity.INFO, f"рядом находится {target}: {distance:.2f} м", False
        return Severity.INFO, "", False

    def _number_key(self, value):
        text = str(value or "").strip().upper().replace(" ", "")
        if not text:
            return ""
        if re.fullmatch(r"\d+", text):
            return text.lstrip("0") or "0"
        compact = re.sub(r"[^0-9A-ZА-ЯЁ]", "", text)
        return compact.lstrip("0") or compact

    def _distance_m(self, lon1, lat1, lon2, lat2):
        return float(self.distance.measureLine(QgsPointXY(lon1, lat1), QgsPointXY(lon2, lat2)))

    def _bucket(self, lon, lat):
        # 0.001 градуса — достаточно крупная ячейка, чтобы соседние ячейки
        # надёжно покрывали поиск в радиусе 5 м даже на высоких широтах.
        size = 0.001
        return int(math.floor(float(lon) / size)), int(math.floor(float(lat) / size))
