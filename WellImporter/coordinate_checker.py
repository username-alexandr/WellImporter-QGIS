# -*- coding: utf-8 -*-

import math
import statistics
from dataclasses import dataclass, field

from .severity import Severity


@dataclass
class CoordinateCheck:
    """Результат проверки одной строки координат перед импортом."""
    row: int
    number: str
    x: float
    y: float
    status: str = "OK"
    severity: str = Severity.INFO
    warnings: list = field(default_factory=list)

    @property
    def message(self):
        return "; ".join(self.warnings) if self.warnings else "Координаты выглядят корректно"


class CoordinateChecker:
    """
    Ищет возможную перестановку X/Y, выбросы относительно основной группы,
    повторяющиеся номера и одинаковые координаты.
    """

    def analyze(self, records):
        if not records:
            return []

        xs = [float(record.x) for record in records]
        ys = [float(record.y) for record in records]
        median_x = statistics.median(xs)
        median_y = statistics.median(ys)
        mad_x = self._mad(xs, median_x)
        mad_y = self._mad(ys, median_y)
        threshold_x = max(1.0, 8.0 * mad_x)
        threshold_y = max(1.0, 8.0 * mad_y)

        number_counts = {}
        coord_counts = {}
        for record in records:
            number_counts[str(record.number)] = number_counts.get(str(record.number), 0) + 1
            key = (round(float(record.x), 7), round(float(record.y), 7))
            coord_counts[key] = coord_counts.get(key, 0) + 1

        result = []
        for index, record in enumerate(records, start=1):
            warnings = []
            severity = Severity.INFO
            x = float(record.x)
            y = float(record.y)

            if number_counts.get(str(record.number), 0) > 1:
                warnings.append("Номер скважины повторяется в импортируемом наборе")
                severity = Severity.max(severity, Severity.ERROR)

            coord_key = (round(x, 7), round(y, 7))
            if coord_counts.get(coord_key, 0) > 1:
                warnings.append("Такие же координаты встречаются более одного раза")
                severity = Severity.max(severity, Severity.CRITICAL)

            direct_deviation = math.hypot(x - median_x, y - median_y)
            swapped_deviation = math.hypot(y - median_x, x - median_y)
            if direct_deviation > 0.25 and swapped_deviation < direct_deviation * 0.35:
                warnings.append("Возможно, координаты X и Y перепутаны местами")
                severity = Severity.max(severity, Severity.ERROR)

            if abs(x - median_x) > threshold_x:
                warnings.append(f"X заметно отличается от основной группы (медиана {median_x:.6f})")
                severity = Severity.max(severity, Severity.WARNING)
            if abs(y - median_y) > threshold_y:
                warnings.append(f"Y заметно отличается от основной группы (медиана {median_y:.6f})")
                severity = Severity.max(severity, Severity.WARNING)

            status = "OK" if not warnings else "ТРЕБУЕТ ПРОВЕРКИ"
            result.append(CoordinateCheck(index, str(record.number), x, y, status, severity, warnings))

        return result

    def count_warnings(self, checks):
        return sum(1 for item in checks if item.warnings)

    def severity_counts(self, checks):
        return Severity.counts(item.severity for item in checks if item.warnings)

    def _mad(self, values, median):
        if len(values) < 2:
            return 0.0
        return statistics.median([abs(value - median) for value in values])
