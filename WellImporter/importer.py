# -*- coding: utf-8 -*-

from dataclasses import dataclass
import re

from qgis.PyQt.QtWidgets import QApplication


@dataclass
class WellRecord:
    x: float
    y: float
    number: str
    row: int


class ClipboardImporter:
    """Чтение трёх столбцов X | Y | Номер из буфера Excel."""

    def parse_clipboard(self):
        text = QApplication.clipboard().text()
        if not text.strip():
            raise Exception("Буфер обмена пуст.")

        records = []
        for row_number, raw_line in enumerate(text.splitlines(), start=1):
            line = raw_line.strip()
            if not line:
                continue

            parts = [part.strip() for part in re.split(r"\t+|;", raw_line)]
            if len(parts) < 3:
                raise Exception(f"Строка {row_number}: требуется 3 столбца X | Y | Номер.")

            try:
                x = float(parts[0].replace(",", "."))
                y = float(parts[1].replace(",", "."))
            except ValueError:
                if row_number == 1:
                    # Допускаем заголовок первой строки.
                    continue
                raise Exception(f"Строка {row_number}: координаты должны быть числами.")

            number = self._normalize_number(parts[2])
            if not number:
                raise Exception(f"Строка {row_number}: не указан номер скважины.")

            records.append(WellRecord(x=x, y=y, number=number, row=row_number))

        if not records:
            raise Exception("Не найдено строк для импорта.")
        return records

    def _normalize_number(self, value):
        value = str(value).strip()
        if re.fullmatch(r"\d+\.0+", value):
            value = value.split(".", 1)[0]
        return value
