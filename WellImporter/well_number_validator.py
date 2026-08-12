# -*- coding: utf-8 -*-

import re

from .severity import Severity
from .well_number_field import feature_well_number


class WellNumberFormatChecker:
    """Проверяет, что заполненный номер скважины состоит только из цифр 0-9.

    Пустые значения здесь намеренно пропускаются: их уже выявляет проверка
    обязательных атрибутов. Это исключает дублирование одной и той же проблемы
    в полном аудите. Ведущие нули допустимы, например ``0015``.
    """

    CATEGORY = "Неверный формат номера"
    VALID_RE = re.compile(r"^[0-9]+$")

    def check(self, point_layer, polygon_layer):
        items = []
        checked = 0

        for layer, object_name in (
            (point_layer, "точка бурения"),
            (polygon_layer, "площадной круг"),
        ):
            for feature in layer.getFeatures():
                raw = feature_well_number(feature, layer, "")
                text = str(raw or "")
                if not text:
                    continue
                checked += 1
                if self.VALID_RE.fullmatch(text):
                    continue

                reasons = self._reasons(text)
                items.append({
                    "source": "number_format",
                    "category": self.CATEGORY,
                    "layer_id": layer.id(),
                    "layer_name": layer.name(),
                    "feature_id": int(feature.id()),
                    "number": text,
                    "severity": Severity.ERROR,
                    "message": (
                        f"Номер {object_name} «{text}» недопустим: "
                        f"{'; '.join(reasons)}. Разрешены только цифры 0-9."
                    ),
                    "reasons": reasons,
                })

        return {
            "checked": checked,
            "invalid": len(items),
            "items": items,
        }

    def _reasons(self, text):
        reasons = []
        if any(char.isspace() for char in text):
            reasons.append("обнаружены пробелы")
        if "." in text:
            reasons.append("обнаружены точки")
        if any(char.isalpha() for char in text):
            reasons.append("обнаружены буквы")
        if any(not ("0" <= char <= "9") for char in text):
            if not reasons:
                reasons.append("обнаружены посторонние символы")
            elif any(
                not ("0" <= char <= "9")
                and not char.isspace()
                and char != "."
                and not char.isalpha()
                for char in text
            ):
                reasons.append("обнаружены другие посторонние символы")
        return reasons or ["формат не соответствует числовому"]
