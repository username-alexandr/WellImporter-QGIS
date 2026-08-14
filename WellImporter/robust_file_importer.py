# -*- coding: utf-8 -*-

from .importer import ExcelFileImporter
from .text_encoding import decode_table_bytes


class RobustExcelFileImporter(ExcelFileImporter):
    """Файловый импортёр с устойчивым определением кодировки CSV/TXT."""

    def _decode_text_file(self, raw):
        try:
            return decode_table_bytes(raw)
        except (UnicodeError, ValueError) as exc:
            raise Exception(str(exc))
