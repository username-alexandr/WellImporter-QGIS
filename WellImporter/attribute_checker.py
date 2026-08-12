# -*- coding: utf-8 -*-

from dataclasses import dataclass
import csv

from .severity import Severity
from .well_number_field import well_number_field_name


@dataclass
class AttributeIssue:
    layer_name: str
    feature_id: int
    number: str
    field_name: str
    severity: str
    message: str


class AttributeChecker:
    """Проверяет наличие и заполненность обязательных атрибутов."""

    DEFAULT_POINT_FIELDS = ["Номер скважины", "Год"]
    DEFAULT_POLYGON_FIELDS = ["Номер скважины"]

    def check(self, point_layer, polygon_layer, point_fields=None, polygon_fields=None):
        issues = []
        issues.extend(self._check_layer(
            point_layer,
            point_fields or self.DEFAULT_POINT_FIELDS,
            number_candidates=["Номер скважины"],
        ))
        issues.extend(self._check_layer(
            polygon_layer,
            polygon_fields or self.DEFAULT_POLYGON_FIELDS,
            number_candidates=["Номер скважины"],
        ))
        counts = Severity.counts(item.severity for item in issues)
        highest = Severity.max(*(item.severity for item in issues)) if issues else Severity.INFO
        return {
            "total": len(issues),
            "severity_counts": counts,
            "highest_severity": highest,
            "issues": [item.__dict__ for item in issues],
        }

    def _check_layer(self, layer, required_fields, number_candidates):
        issues = []
        field_names = layer.fields().names()
        logical_number_field = well_number_field_name(layer)
        resolved_required = []
        for field in required_fields:
            if field == "Номер скважины":
                if logical_number_field:
                    resolved_required.append((field, logical_number_field))
                else:
                    issues.append(AttributeIssue(
                        layer.name(), -1, "", field, Severity.CRITICAL,
                        f"В слое отсутствует обязательное поле «{field}»."
                    ))
            elif field in field_names:
                resolved_required.append((field, field))
            else:
                issues.append(AttributeIssue(
                    layer.name(), -1, "", field, Severity.CRITICAL,
                    f"В слое отсутствует обязательное поле «{field}»."
                ))
        number_field = logical_number_field
        for feature in layer.getFeatures():
            number = ""
            if number_field:
                try:
                    number = str(feature[number_field]).strip()
                except Exception:
                    number = ""
            for display_name, physical_name in resolved_required:
                try:
                    value = feature[physical_name]
                except Exception:
                    value = None
                if value is None or str(value).strip() in ("", "NULL", "None"):
                    issues.append(AttributeIssue(
                        layer.name(), int(feature.id()), number, display_name, Severity.ERROR,
                        f"Не заполнено обязательное поле «{display_name}»."
                    ))
        return issues

    def export_csv(self, report, path):
        """Сохраняет список проблем обязательных атрибутов в CSV UTF-8 BOM."""
        with open(path, "w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.writer(stream, delimiter=";")
            writer.writerow(["Слой", "FID", "Номер скважины", "Поле", "Серьёзность", "Проблема"])
            for issue in report.get("issues", []):
                writer.writerow([
                    issue.get("layer_name", ""), issue.get("feature_id", ""),
                    issue.get("number", ""), issue.get("field_name", ""),
                    Severity.label(issue.get("severity")), issue.get("message", ""),
                ])
