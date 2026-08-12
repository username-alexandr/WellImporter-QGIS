# -*- coding: utf-8 -*-

from .severity import Severity


class ProjectAuditManager:
    """
    Объединяет все текущие проверки проекта в один нормализованный отчёт.

    На этом уровне аудит ничего не исправляет и не изменяет в слоях. Его задача —
    собрать результаты независимых проверок в общий список проблем с единой
    шкалой серьёзности. Такой формат затем используется интерфейсом, экспортом
    отчёта и следующими этапами развития мастера исправления ошибок.
    """

    def build(self, point_layer, polygon_layer, attribute_report, quality_report):
        issues = []

        # Ошибки обязательных атрибутов уже содержат FID конкретного объекта.
        for issue in attribute_report.get("issues", []):
            layer_name = str(issue.get("layer_name", ""))
            layer_id = ""
            if layer_name == point_layer.name():
                layer_id = point_layer.id()
            elif layer_name == polygon_layer.name():
                layer_id = polygon_layer.id()

            issues.append({
                "source": "attributes",
                "category": "Обязательные атрибуты",
                "layer_id": layer_id,
                "layer_name": layer_name,
                "feature_id": issue.get("feature_id", -1),
                "number": str(issue.get("number", "") or ""),
                "severity": Severity.normalize(issue.get("severity")),
                "message": str(issue.get("message", "") or ""),
            })

        # В итоговый список попадают только проблемные результаты проверки кругов.
        # INFO/OK остаются в статистике quality_report, но не засоряют список ошибок.
        for item in quality_report.get("items", []):
            if item.get("area_ok") and item.get("center_ok"):
                continue

            message = str(item.get("message", "") or "")
            category = (
                "Соответствие точка ↔ круг"
                if "парная точка" in message.lower() or "площадной круг" in message.lower()
                else "Геометрия площадного круга"
            )
            issues.append({
                "source": "quality",
                "category": category,
                "layer_id": polygon_layer.id(),
                "layer_name": polygon_layer.name(),
                "feature_id": -1,
                "number": str(item.get("number", "") or ""),
                "severity": Severity.normalize(item.get("severity")),
                "message": message,
            })

        counts = Severity.counts(issue["severity"] for issue in issues)
        highest = Severity.max(*(issue["severity"] for issue in issues)) if issues else Severity.INFO

        return {
            "total": len(issues),
            "severity_counts": counts,
            "highest_severity": highest,
            "issues": issues,
            "attributes": attribute_report,
            "quality": quality_report,
            "checked": {
                "points": int(point_layer.featureCount()),
                "circles": int(polygon_layer.featureCount()),
                "pairs": int(quality_report.get("total", 0)),
                "circles_ok": int(quality_report.get("ok", 0)),
            },
        }
