# -*- coding: utf-8 -*-

from .severity import Severity
from .well_number_field import feature_well_number


class PairIntegrityChecker:
    """Проверяет правило «одна точка бурения = один площадной круг».

    Сопоставление выполняется по единому логическому полю «Номер скважины».
    Проверка не изменяет слои и возвращает отдельный структурированный отчёт,
    который затем включается в полный аудит проекта.
    """

    CATEGORY = "1 точка = 1 круг"

    def check(self, point_layer, polygon_layer):
        points = self._group_by_number(point_layer)
        circles = self._group_by_number(polygon_layer)
        numbers = sorted(set(points) | set(circles), key=self._sort_key)

        items = []
        ok = 0
        missing_circles = 0
        missing_points = 0
        duplicate_points = 0
        duplicate_circles = 0

        for number in numbers:
            point_features = points.get(number, [])
            circle_features = circles.get(number, [])
            point_count = len(point_features)
            circle_count = len(circle_features)

            if point_count == 1 and circle_count == 1:
                ok += 1
                continue

            if circle_count == 0 and point_count > 0:
                missing_circles += 1
            if point_count == 0 and circle_count > 0:
                missing_points += 1
            if point_count > 1:
                duplicate_points += 1
            if circle_count > 1:
                duplicate_circles += 1

            severity = (
                Severity.CRITICAL
                if point_count > 1 or circle_count > 1
                else Severity.ERROR
            )

            if point_count > 0:
                layer = point_layer
                feature_id = point_features[0].id()
            else:
                layer = polygon_layer
                feature_id = circle_features[0].id() if circle_features else -1

            message_parts = [
                f"Нарушение соответствия 1:1: точек {point_count}, кругов {circle_count}."
            ]
            if circle_count == 0 and point_count:
                message_parts.append("Для точки отсутствует площадной круг.")
            if point_count == 0 and circle_count:
                message_parts.append("Для площадного круга отсутствует точка бурения.")
            if point_count > 1:
                message_parts.append("Найдено несколько точек с одним номером.")
            if circle_count > 1:
                message_parts.append("Найдено несколько кругов с одним номером.")

            items.append({
                "source": "pair_integrity",
                "category": self.CATEGORY,
                "layer_id": layer.id(),
                "layer_name": layer.name(),
                "feature_id": int(feature_id),
                "number": number,
                "severity": severity,
                "message": " ".join(message_parts),
                "point_count": point_count,
                "circle_count": circle_count,
                "point_feature_ids": [feature.id() for feature in point_features],
                "circle_feature_ids": [feature.id() for feature in circle_features],
            })

        return {
            "numbers_checked": len(numbers),
            "ok": ok,
            "violations": len(items),
            "missing_circles": missing_circles,
            "missing_points": missing_points,
            "duplicate_points": duplicate_points,
            "duplicate_circles": duplicate_circles,
            "items": items,
        }

    def _group_by_number(self, layer):
        grouped = {}
        for feature in layer.getFeatures():
            number = feature_well_number(feature, layer, "").strip()
            if not number:
                # Пустые номера контролируются проверкой обязательных атрибутов;
                # здесь они не объединяются в фиктивную общую «скважину».
                continue
            grouped.setdefault(number, []).append(feature)
        return grouped

    def _sort_key(self, number):
        text = str(number)
        if text.isdigit():
            return (0, int(text), text)
        return (1, text.casefold(), text)
