# -*- coding: utf-8 -*-

import math

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsUnitTypes
)


class GeometryBuilder:
    """
    Модуль построения геометрии.

    Создаёт точки скважин и круги заданной площади.

    Начиная с версии 1.5.4 круг строится непосредственно в CRS выбранного
    полигонального слоя. Это важно для слоёв EPSG:4326: прежнее построение
    метрического круга с последующим переводом обратно в градусы визуально
    превращало его в овал. Новый алгоритм рассчитывает радиус в единицах
    целевого слоя и делает обычный круговой buffer вокруг центра скважины.
    """

    SOURCE_CRS = QgsCoordinateReferenceSystem("EPSG:4326")

    def __init__(self):
        """Получает текущий проект QGIS для координатных преобразований."""
        self.project = QgsProject.instance()

    def radius_from_area(self, area_hectares):
        """
        Рассчитывает радиус круга по площади, заданной в гектарах.

        1 гектар = 10 000 м².
        Например:
        33 га = 330 000 м².
        """
        area_hectares = float(area_hectares)

        if area_hectares <= 0:
            raise Exception("Площадь круга должна быть больше нуля.")

        area_m2 = area_hectares * 10000.0
        return math.sqrt(area_m2 / math.pi)

    def normalize_lon_lat(self, x, y):
        """Проверяет исходные координаты EPSG:4326."""
        x = float(x)
        y = float(y)
        if not (-180.0 <= x <= 180.0):
            raise Exception("Координата X находится вне диапазона -180..180.")
        if not (-90.0 <= y <= 90.0):
            raise Exception("Координата Y находится вне диапазона -90..90.")
        return x, y

    def create_point(self, lon, lat):
        """Создаёт точку скважины в EPSG:4326."""
        lon, lat = self.normalize_lon_lat(lon, lat)
        return QgsGeometry.fromPointXY(QgsPointXY(lon, lat))

    def create_circle_for_layer(self, lon, lat, area, layer, segments=180):
        """
        Создаёт круг непосредственно в CRS выбранного слоя кругов.

        Центр круга — та же координата, что используется для точки скважины.
        Радиус сначала вычисляется в метрах по указанной площади, затем
        переводится в единицы CRS слоя.
        """
        lon, lat = self.normalize_lon_lat(lon, lat)
        radius_m = self.radius_from_area(area)
        layer_crs = layer.crs()

        to_layer = QgsCoordinateTransform(
            self.SOURCE_CRS,
            layer_crs,
            self.project
        )
        center_layer = to_layer.transform(QgsPointXY(lon, lat))
        radius_layer = self._radius_in_layer_units(
            radius_m=radius_m,
            latitude=lat,
            crs=layer_crs
        )

        if radius_layer <= 0:
            raise Exception("Не удалось рассчитать радиус круга в единицах слоя.")

        return QgsGeometry.fromPointXY(center_layer).buffer(
            radius_layer,
            segments
        )

    def _radius_in_layer_units(self, radius_m, latitude, crs):
        """Переводит радиус из метров в единицы целевого CRS."""
        units = crs.mapUnits()

        if units == QgsUnitTypes.DistanceMeters:
            return radius_m

        if units == QgsUnitTypes.DistanceDegrees:
            return self._meters_to_local_degrees(radius_m, latitude)

        try:
            factor = QgsUnitTypes.fromUnitToUnitFactor(
                QgsUnitTypes.DistanceMeters,
                units
            )
            if factor and factor > 0:
                return radius_m * factor
        except Exception:
            pass

        raise Exception(
            "Не поддерживаются единицы измерения выбранного слоя кругов. "
            "Используйте CRS в метрах или EPSG:4326."
        )

    def _meters_to_local_degrees(self, radius_m, latitude):
        """
        Переводит метры в локальный угловой радиус для EPSG:4326.

        Используется геометрическое среднее масштаба одного градуса по
        широте и долготе. Благодаря одному радиусу по X и Y buffer остаётся
        именно кругом в координатах слоя, а заданная площадь сохраняется
        с высокой локальной точностью.
        """
        lat = math.radians(float(latitude))

        meters_per_degree_lat = (
            111132.92
            - 559.82 * math.cos(2.0 * lat)
            + 1.175 * math.cos(4.0 * lat)
            - 0.0023 * math.cos(6.0 * lat)
        )

        meters_per_degree_lon = (
            111412.84 * math.cos(lat)
            - 93.5 * math.cos(3.0 * lat)
            + 0.118 * math.cos(5.0 * lat)
        )

        if meters_per_degree_lat <= 0 or meters_per_degree_lon <= 0:
            raise Exception("Не удалось определить локальный масштаб EPSG:4326.")

        equivalent_meters_per_degree = math.sqrt(
            meters_per_degree_lat * meters_per_degree_lon
        )
        return radius_m / equivalent_meters_per_degree

    def transform_geometry_to_layer(self, geometry_4326, layer):
        """Преобразует геометрию точки из EPSG:4326 в CRS выбранного слоя."""
        if layer.crs() == self.SOURCE_CRS:
            return QgsGeometry(geometry_4326)
        result = QgsGeometry(geometry_4326)
        result.transform(
            QgsCoordinateTransform(
                self.SOURCE_CRS,
                layer.crs(),
                self.project
            )
        )
        return result
