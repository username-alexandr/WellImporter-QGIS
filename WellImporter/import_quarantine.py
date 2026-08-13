# -*- coding: utf-8 -*-

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class QuarantineEntry:
    """Одна ошибочная строка импорта, сохранённая только в текущей сессии."""

    source: str
    row: int
    values: tuple
    error: str
    created_at: str

    @property
    def raw_values(self):
        return " | ".join(str(value) for value in self.values)


class SessionImportQuarantine:
    """Память ошибочных строк без записи в QSettings, проект или файл."""

    def __init__(self):
        self._entries = []

    def begin(self, source):
        """Начинает повторную проверку источника, заменяя его старые ошибки."""
        source = str(source or "Источник")
        self._entries = [item for item in self._entries if item.source != source]
        return source

    def add(self, source, row, values, error):
        entry = QuarantineEntry(
            source=str(source or "Источник"),
            row=int(row),
            values=tuple("" if value is None else str(value) for value in values),
            error=str(error),
            created_at=datetime.now().strftime("%H:%M:%S"),
        )
        self._entries.append(entry)
        return entry

    def entries(self, source=None):
        if source is None:
            return list(self._entries)
        source = str(source)
        return [item for item in self._entries if item.source == source]

    def count(self, source=None):
        return len(self.entries(source))

    def clear(self, source=None):
        if source is None:
            self._entries.clear()
            return
        source = str(source)
        self._entries = [item for item in self._entries if item.source != source]
