# -*- coding: utf-8 -*-

import re
from dataclasses import dataclass

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsPointXY,
    QgsProject,
)

from .coordinate_precision import CoordinatePrecisionNormalizer


@dataclass
class ParsedCoordinate:
    """Результат преобразования исходных координат в WGS84."""
    lon: float
    lat: float
    detected_format: str


class CoordinateParser:
    """
    Разбирает разные форматы координат.

    Поддерживаются:
    - DD — десятичные градусы;
    - DMS — градусы, минуты, секунды;
    - PROJECTED — проекционные координаты, включая UTM, по указанной CRS;
    - AUTO — автоматическое определение DD/DMS и использование указанной CRS.

    На выходе всегда возвращаются долгота/широта EPSG:4326, нормализованные
    до шести знаков после запятой, поэтому остальная логика плагина работает
    с единым правилом точности.
    """

    WGS84 = QgsCoordinateReferenceSystem("EPSG:4326")

    def __init__(self, coordinate_decimals=CoordinatePrecisionNormalizer.DEFAULT_DECIMALS):
        self.precision = CoordinatePrecisionNormalizer(coordinate_decimals)

    def parse_pair(self, raw_x, raw_y, mode="AUTO", source_crs="EPSG:4326"):
        """Преобразует пару исходных значений в EPSG:4326 и нормализует точность."""
        mode = str(mode or "AUTO").upper()
        source_crs = self._normalize_source_crs(source_crs)

        if mode == "AUTO":
            if self._looks_like_dms(raw_x) or self._looks_like_dms(raw_y):
                mode = "DMS"
            elif self._is_wgs84(source_crs):
                mode = "DD"
            else:
                mode = "PROJECTED"

        if mode == "DMS":
            lon = self.parse_dms(raw_x, axis="lon")
            lat = self.parse_dms(raw_y, axis="lat")
            self._validate_lon_lat(lon, lat)
            lon, lat = self.precision.normalize_pair(lon, lat)
            return ParsedCoordinate(lon, lat, "DMS")

        x = self.parse_decimal(raw_x)
        y = self.parse_decimal(raw_y)

        if mode == "PROJECTED" or not self._is_wgs84(source_crs):
            lon, lat = self._transform_to_wgs84(x, y, source_crs)
            self._validate_lon_lat(lon, lat)
            lon, lat = self.precision.normalize_pair(lon, lat)
            label = "UTM/проекционные" if self._looks_like_utm(source_crs) else f"Проекционные ({source_crs})"
            return ParsedCoordinate(lon, lat, label)

        self._validate_lon_lat(x, y)
        x, y = self.precision.normalize_pair(x, y)
        return ParsedCoordinate(x, y, "DD")

    def parse_decimal(self, value):
        """Читает обычное десятичное число с точкой или запятой."""
        text = str(value).strip().replace("\u00a0", "").replace(" ", "")
        if not text:
            raise ValueError("пустое значение координаты")
        return float(text.replace(",", "."))

    def parse_dms(self, value, axis):
        """Читает DMS: 48°12'34.5\"E, 48 12 34.5 В и похожие варианты."""
        text = str(value).strip().upper().replace(",", ".")
        if not text:
            raise ValueError("пустое значение DMS")

        direction = None
        direction_match = re.search(r"([NSEWСЮВЗ])", text)
        if direction_match:
            direction = direction_match.group(1)

        numbers = re.findall(r"[-+]?\d+(?:\.\d+)?", text)
        if not numbers:
            raise ValueError(f"не удалось распознать DMS «{value}»")

        if len(numbers) == 1:
            result = float(numbers[0])
        else:
            degrees = float(numbers[0])
            minutes = float(numbers[1]) if len(numbers) >= 2 else 0.0
            seconds = float(numbers[2]) if len(numbers) >= 3 else 0.0
            if not (0.0 <= minutes < 60.0) or not (0.0 <= seconds < 60.0):
                raise ValueError(f"некорректные минуты/секунды в «{value}»")
            sign = -1.0 if degrees < 0 else 1.0
            result = sign * (abs(degrees) + minutes / 60.0 + seconds / 3600.0)

        if direction in ("W", "S", "З", "Ю"):
            result = -abs(result)
        elif direction in ("E", "N", "В", "С"):
            result = abs(result)

        if axis == "lon" and direction in ("N", "S", "С", "Ю"):
            raise ValueError("для X/долготы указано направление широты")
        if axis == "lat" and direction in ("E", "W", "В", "З"):
            raise ValueError("для Y/широты указано направление долготы")
        return result

    def _normalize_source_crs(self, value):
        """Понимает как EPSG-код, так и короткую запись UTM 38N / 38S."""
        text = str(value or "EPSG:4326").strip().upper() or "EPSG:4326"
        compact = text.replace(" ", "")
        match = re.fullmatch(r"(?:UTM)?(\d{1,2})([NS])", compact)
        if match:
            zone = int(match.group(1))
            hemisphere = match.group(2)
            if not (1 <= zone <= 60):
                raise ValueError("номер зоны UTM должен быть от 1 до 60")
            epsg = (32600 if hemisphere == "N" else 32700) + zone
            return f"EPSG:{epsg}"
        if re.fullmatch(r"\d{4,6}", compact):
            return f"EPSG:{compact}"
        return text

    def _transform_to_wgs84(self, x, y, source_crs):
        """Преобразует координаты указанной CRS в EPSG:4326."""
        source = QgsCoordinateReferenceSystem(source_crs)
        if not source.isValid():
            raise ValueError(
                f"неизвестная исходная CRS «{source_crs}». "
                "Для UTM укажите, например, EPSG:32638 (север) или EPSG:32738 (юг)"
            )
        transform = QgsCoordinateTransform(source, self.WGS84, QgsProject.instance())
        point = transform.transform(QgsPointXY(float(x), float(y)))
        return float(point.x()), float(point.y())

    def _validate_lon_lat(self, lon, lat):
        """Проверяет итоговые координаты WGS84."""
        if not (-180.0 <= float(lon) <= 180.0):
            raise ValueError("долгота после преобразования вне диапазона -180..180")
        if not (-90.0 <= float(lat) <= 90.0):
            raise ValueError("широта после преобразования вне диапазона -90..90")

    def _looks_like_dms(self, value):
        text = str(value).upper()
        return any(symbol in text for symbol in ("°", "′", "″", "'", '"')) or bool(re.search(r"[NSEWСЮВЗ]", text))

    def _is_wgs84(self, crs):
        normalized = str(crs).strip().upper().replace(" ", "")
        return normalized in ("EPSG:4326", "4326", "WGS84", "WGS-84")

    def _looks_like_utm(self, crs):
        text = str(crs).upper().replace(" ", "")
        match = re.search(r"EPSG:(326|327)\d{2}", text)
        return bool(match)
