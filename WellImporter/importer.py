# -*- coding: utf-8 -*-

import csv
import re
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from qgis.PyQt.QtWidgets import QApplication

from .coordinate_parser import CoordinateParser
from .import_quarantine import SessionImportQuarantine


@dataclass
class WellRecord:
    """Одна строка импорта, приведённая к EPSG:4326."""
    x: float
    y: float
    number: str
    original_x: str = ""
    original_y: str = ""
    coordinate_format: str = "DD"


class ImportRecords(list):
    """Список корректных записей с ошибочными строками текущего разбора."""

    def __init__(self, records=(), quarantine=None):
        super().__init__(records)
        self.quarantine = list(quarantine or [])


class BaseTableImporter:
    """Базовый разборщик таблиц и координат разных форматов."""

    def __init__(self):
        self.coordinate_parser = CoordinateParser()
        # Очередь живёт только пока существует экземпляр импортера/QGIS-сессия.
        self.quarantine = SessionImportQuarantine()

    def parse_rows(self, rows, coordinate_mode="AUTO", source_crs="EPSG:4326", source="Источник"):
        """Разбирает строки, а ошибочные помещает в сессионный карантин."""
        records = []
        source = self.quarantine.begin(source)

        for row_index, row in enumerate(rows, start=1):
            # Важно сохранять пустые ячейки на своих позициях, чтобы столбцы
            # X/Y/Номер не сдвигались при пропуске значения.
            parts = ["" if value is None else str(value).strip() for value in row]
            if not any(parts):
                continue

            if len(parts) < 3:
                if self._looks_like_header(parts):
                    continue
                message = f"Строка {row_index}: нужно минимум 3 столбца: X, Y, Номер скважины."
                self.quarantine.add(source, row_index, parts, message)
                continue

            try:
                records.append(self._parse_parts(parts, row_index, coordinate_mode, source_crs))
            except Exception as exc:
                if not records and self._looks_like_header(parts):
                    continue
                self.quarantine.add(source, row_index, parts, str(exc))

        quarantined = self.quarantine.entries(source)
        if not records:
            if quarantined:
                raise Exception(
                    "Не удалось прочитать ни одной корректной строки. "
                    f"Ошибочных строк в карантине: {len(quarantined)}."
                )
            raise Exception("Не удалось прочитать ни одной строки.\nНужны три столбца: X | Y | Номер скважины.")

        return ImportRecords(records, quarantined)

    def quarantine_entries(self, source=None):
        """Возвращает копию очереди карантина текущей сессии."""
        return self.quarantine.entries(source)

    def clear_quarantine(self, source=None):
        """Очищает всю очередь или ошибки конкретного источника."""
        self.quarantine.clear(source)

    def _parse_parts(self, parts, row_index, coordinate_mode, source_crs):
        """Преобразует первые три столбца строки в WellRecord."""
        raw_x = parts[0]
        raw_y = parts[1]
        number = self._to_number(parts[2], row_index)
        if not raw_x or not raw_y:
            raise Exception(f"Строка {row_index}: координаты X и Y не должны быть пустыми.")
        try:
            parsed = self.coordinate_parser.parse_pair(raw_x, raw_y, coordinate_mode, source_crs)
        except Exception as exc:
            raise Exception(f"Строка {row_index}: ошибка координат: {exc}")
        return WellRecord(
            x=float(parsed.lon),
            y=float(parsed.lat),
            number=number,
            original_x=str(raw_x),
            original_y=str(raw_y),
            coordinate_format=parsed.detected_format,
        )

    def _split_line(self, line):
        """Делит текстовую строку на столбцы."""
        if "\t" in line:
            return [part.strip() for part in line.split("\t")]
        if ";" in line:
            return [part.strip() for part in line.split(";")]
        if line.count(",") >= 2 and not re.search(r"\d,\d", line):
            return [part.strip() for part in line.split(",")]
        # Для DMS строки могут содержать пробелы внутри координаты, поэтому
        # разделение по пробелам используется только как последний вариант.
        return re.split(r"\s+", line.strip())

    def _to_number(self, value, row_index):
        """Читает номер скважины как строку, сохраняя ведущие нули."""
        text = str(value).strip()
        if re.match(r"^\d+\.0+$", text):
            text = text.split(".")[0]
        if not text:
            raise Exception(f"Строка {row_index}: Номер скважины не заполнен.")
        if len(text) > 64:
            raise Exception(f"Строка {row_index}: Номер скважины слишком длинный.")
        return text

    def _looks_like_header(self, parts):
        """Определяет строку заголовков."""
        joined = " ".join(str(part).strip().lower() for part in parts[:3])
        return any(token in joined for token in ["x", "y", "№", "номер", "скваж", "longitude", "latitude", "долгот", "широт", "id"])


class ClipboardImporter(BaseTableImporter):
    """Импорт из буфера обмена Excel."""

    def parse(self, coordinate_mode="AUTO", source_crs="EPSG:4326"):
        """Возвращает записи WellRecord из буфера обмена."""
        text = QApplication.clipboard().text()
        if not text or not text.strip():
            raise Exception("Буфер обмена пуст.")

        rows = []
        for raw_line in text.splitlines():
            if raw_line.strip():
                rows.append(self._split_line(raw_line.rstrip("\r\n")))
        return self.parse_rows(rows, coordinate_mode, source_crs, source="Буфер обмена")


class ExcelFileImporter(BaseTableImporter):
    """Импорт из .xlsx, .csv и .txt."""

    def parse_file(self, file_path, coordinate_mode="AUTO", source_crs="EPSG:4326"):
        """Читает файл и возвращает список WellRecord."""
        path = Path(file_path)
        if not path.exists():
            raise Exception(f"Файл не найден:\n{path}")

        suffix = path.suffix.lower()
        if suffix == ".xlsx":
            rows = self._read_xlsx(path)
        elif suffix in [".csv", ".txt"]:
            rows = self._read_csv_or_txt(path)
        elif suffix == ".xls":
            raise Exception("Формат .xls не поддерживается.\nСохраните файл как .xlsx или .csv.")
        else:
            raise Exception("Неподдерживаемый формат файла.\nПоддерживаются: .xlsx, .csv, .txt")

        return self.parse_rows(rows, coordinate_mode, source_crs, source=path.name)

    def _read_csv_or_txt(self, path):
        """Читает CSV/TXT с автоматическим подбором кодировки."""
        raw = path.read_bytes()
        text = self._decode_text_file(raw)
        sample = text[:4096]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters="\t;,")
            delimiter = dialect.delimiter
        except Exception:
            delimiter = ";" if ";" in sample else "\t" if "\t" in sample else ","

        rows = []
        for row in csv.reader(text.splitlines(), delimiter=delimiter):
            if row:
                rows.append([cell.strip() for cell in row])
        return rows

    def _decode_text_file(self, raw):
        """Поддерживает UTF-8, UTF-16, Windows-1251 и CP866."""
        if raw.startswith(b"\xef\xbb\xbf"):
            return raw.decode("utf-8-sig")
        if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
            return raw.decode("utf-16")

        errors = []
        for encoding in ("utf-8", "cp1251", "cp866"):
            try:
                return raw.decode(encoding)
            except UnicodeDecodeError as exc:
                errors.append(f"{encoding}: {exc}")
        raise Exception(
            "Не удалось прочитать CSV/TXT-файл. Поддерживаются UTF-8, UTF-16, Windows-1251 и CP866.\n"
            "Попробуйте пересохранить файл из Excel в формате CSV UTF-8.\n\n" + "\n".join(errors)
        )

    def _read_xlsx(self, path):
        """Читает первый лист .xlsx через zip+xml."""
        with zipfile.ZipFile(path, "r") as archive:
            shared_strings = self._read_shared_strings(archive)
            sheet_name = self._first_sheet_name(archive)
            sheet_xml = archive.read(sheet_name)

        root = ET.fromstring(sheet_xml)
        ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        rows = []
        for row in root.findall(".//m:sheetData/m:row", ns):
            cells = []
            for cell in row.findall("m:c", ns):
                col_idx = self._column_index(cell.attrib.get("r", ""))
                value = self._cell_value(cell, shared_strings, ns)
                while len(cells) < col_idx:
                    cells.append("")
                cells[col_idx - 1] = value
            if any(str(value).strip() for value in cells):
                rows.append(cells)
        return rows

    def _read_shared_strings(self, archive):
        if "xl/sharedStrings.xml" not in archive.namelist():
            return []
        root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
        ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        strings = []
        for item in root.findall("m:si", ns):
            strings.append("".join((text.text or "") for text in item.findall(".//m:t", ns)))
        return strings

    def _first_sheet_name(self, archive):
        names = archive.namelist()
        if "xl/workbook.xml" in names and "xl/_rels/workbook.xml.rels" in names:
            workbook_root = ET.fromstring(archive.read("xl/workbook.xml"))
            rels_root = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
            wb_ns = {
                "m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
                "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
            }
            rel_ns = {"rel": "http://schemas.openxmlformats.org/package/2006/relationships"}
            first_sheet = workbook_root.find(".//m:sheets/m:sheet", wb_ns)
            if first_sheet is not None:
                rel_id = first_sheet.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
                for relation in rels_root.findall("rel:Relationship", rel_ns):
                    if relation.attrib.get("Id") == rel_id:
                        target = relation.attrib.get("Target", "")
                        if target.startswith("/"):
                            return target.lstrip("/")
                        return "xl/" + target.lstrip("./")
        for name in names:
            if name.startswith("xl/worksheets/") and name.endswith(".xml"):
                return name
        raise Exception("В .xlsx не найден лист с данными.")

    def _column_index(self, cell_ref):
        letters = "".join(character for character in cell_ref if character.isalpha())
        if not letters:
            return 1
        result = 0
        for character in letters.upper():
            result = result * 26 + (ord(character) - ord("A") + 1)
        return result

    def _cell_value(self, cell, shared_strings, ns):
        cell_type = cell.attrib.get("t")
        if cell_type == "inlineStr":
            return "".join((text.text or "") for text in cell.findall(".//m:t", ns))
        value_node = cell.find("m:v", ns)
        if value_node is None or value_node.text is None:
            return ""
        raw = value_node.text
        if cell_type == "s":
            try:
                return shared_strings[int(raw)]
            except Exception:
                return raw
        return raw
