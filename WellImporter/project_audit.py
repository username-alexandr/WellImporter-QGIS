# -*- coding: utf-8 -*-

from .severity import Severity


class ProjectAuditManager:
    """Объединяет независимые проверки проекта в единый нормализованный отчёт."""

    def build(
        self,
        point_layer,
        polygon_layer,
        attribute_report,
        quality_report,
        pair_report=None,
        number_consistency_report=None,
        number_format_report=None,
    ):
        issues = []
        pair_report = dict(pair_report or {})
        number_consistency_report = dict(number_consistency_report or {})
        number_format_report = dict(number_format_report or {})

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

        for item in pair_report.get("items", []):
            issues.append({
                "source": "pair_integrity",
                "category": str(item.get("category", "1 точка = 1 круг") or "1 точка = 1 круг"),
                "layer_id": str(item.get("layer_id", "") or ""),
                "layer_name": str(item.get("layer_name", "") or ""),
                "feature_id": int(item.get("feature_id", -1) or -1),
                "number": str(item.get("number", "") or ""),
                "severity": Severity.normalize(item.get("severity")),
                "message": str(item.get("message", "") or ""),
            })

        # Несовпадение заполненных номеров в геометрически связанной паре всегда CRITICAL.
        for item in number_consistency_report.get("items", []):
            issues.append({
                "source": "pair_number_consistency",
                "category": str(
                    item.get("category", "Несовпадение номера точки и круга")
                    or "Несовпадение номера точки и круга"
                ),
                "layer_id": str(item.get("layer_id", "") or ""),
                "layer_name": str(item.get("layer_name", "") or ""),
                "feature_id": int(item.get("feature_id", -1) or -1),
                "number": str(item.get("number", "") or ""),
                "severity": Severity.CRITICAL,
                "message": str(item.get("message", "") or ""),
            })

        for item in number_format_report.get("items", []):
            issues.append({
                "source": "number_format",
                "category": str(item.get("category", "Неверный формат номера") or "Неверный формат номера"),
                "layer_id": str(item.get("layer_id", "") or ""),
                "layer_name": str(item.get("layer_name", "") or ""),
                "feature_id": int(item.get("feature_id", -1) or -1),
                "number": str(item.get("number", "") or ""),
                "severity": Severity.normalize(item.get("severity", Severity.ERROR)),
                "message": str(item.get("message", "") or ""),
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
            "pair_integrity": pair_report,
            "number_consistency": number_consistency_report,
            "number_format": number_format_report,
            "checked": {
                "points": int(point_layer.featureCount()),
                "circles": int(polygon_layer.featureCount()),
                "pairs": int(pair_report.get("numbers_checked", quality_report.get("total", 0))),
                "circles_ok": int(quality_report.get("ok", 0)),
            },
        }
