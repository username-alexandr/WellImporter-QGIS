# -*- coding: utf-8 -*-

import math

from qgis.core import QgsGeometry, QgsPointXY


class GeometryBuilder:
    """Геометрия импорта. Входные координаты считаются EPSG:4326."""

    def create_point(self, x, y):
        return QgsGeometry.fromPointXY(QgsPointXY(float(x), float(y)))

    def create_circle(self, x, y, area):
        area = float(area)
        if area <= 0:
            raise Exception("Площадь должна быть больше 0.")

        radius = math.sqrt(area / math.pi)
        # Историческая версия: радиус используется в единицах слоя.
        return self.create_point(x, y).buffer(radius, 64)
