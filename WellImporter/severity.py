# -*- coding: utf-8 -*-


class Severity:
    """Единая шкала серьёзности замечаний Well Importer."""

    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

    ORDER = {
        INFO: 0,
        WARNING: 1,
        ERROR: 2,
        CRITICAL: 3,
    }

    LABELS = {
        INFO: "Информация",
        WARNING: "Предупреждение",
        ERROR: "Ошибка",
        CRITICAL: "Критическая",
    }

    COLORS = {
        INFO: (221, 235, 247),
        WARNING: (255, 242, 204),
        ERROR: (252, 229, 205),
        CRITICAL: (244, 204, 204),
    }

    @classmethod
    def normalize(cls, value):
        """Возвращает корректный код серьёзности."""
        value = str(value or cls.INFO).upper()
        return value if value in cls.ORDER else cls.INFO

    @classmethod
    def label(cls, value):
        """Возвращает русское название уровня."""
        return cls.LABELS[cls.normalize(value)]

    @classmethod
    def max(cls, *values):
        """Возвращает наиболее серьёзный уровень из переданных."""
        normalized = [cls.normalize(value) for value in values if value]
        if not normalized:
            return cls.INFO
        return max(normalized, key=lambda item: cls.ORDER[item])

    @classmethod
    def counts(cls, values):
        """Считает количество результатов по уровням."""
        result = {key: 0 for key in cls.ORDER}
        for value in values:
            result[cls.normalize(value)] += 1
        return result
