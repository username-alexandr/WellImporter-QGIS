# -*- coding: utf-8 -*-

class CoordinatePrecisionNormalizer:
    """Единообразно нормализует координаты WGS84 для импорта Well Importer."""

    DEFAULT_DECIMALS = 6

    def __init__(self, decimals=DEFAULT_DECIMALS):
        decimals = int(decimals)
        if not 0 <= decimals <= 12:
            raise ValueError("Количество знаков координат должно быть от 0 до 12.")
        self.decimals = decimals

    def normalize(self, value):
        """Округляет числовую координату до заданного количества знаков."""
        result = round(float(value), self.decimals)
        # Не оставляем -0.000000 после нормализации.
        if result == 0.0:
            return 0.0
        return result

    def normalize_pair(self, lon, lat):
        """Возвращает нормализованную пару долгота/широта."""
        return self.normalize(lon), self.normalize(lat)

    def format(self, value):
        """Возвращает координату строкой с фиксированным количеством знаков."""
        return f"{self.normalize(value):.{self.decimals}f}"
