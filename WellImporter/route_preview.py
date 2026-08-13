# -*- coding: utf-8 -*-

from qgis.PyQt.QtCore import QVariant
from qgis.core import QgsFeature, QgsField, QgsGeometry, QgsPointXY, QgsProject, QgsVectorLayer


class RoutePreviewManager:
    """Создаёт временные слои маршрута и хранит последний расчёт сессии."""

    PROPERTY = "well_importer/route_preview"

    def __init__(self, iface):
        self.iface = iface
        self.project = QgsProject.instance()
        self.last_plan = None
        self.last_mode_label = ""

    def draw(self, plan, mode_label=""):
        self.clear()
        self.last_plan = plan
        self.last_mode_label = str(mode_label or "")
        line_layer = self._line_layer(plan, mode_label)
        order_layer = self._order_layer(plan)
        self.project.addMapLayer(line_layer)
        self.project.addMapLayer(order_layer)
        self.iface.setActiveLayer(line_layer)
        self.iface.zoomToActiveLayer()
        self.iface.mapCanvas().refresh()
        return line_layer, order_layer

    def clear(self):
        for layer in list(self.project.mapLayers().values()):
            if bool(layer.customProperty(self.PROPERTY, False)):
                self.project.removeMapLayer(layer.id())

    def _line_layer(self, plan, mode_label):
        layer = QgsVectorLayer("LineString?crs=EPSG:4326", "Маршрут объезда Well Importer", "memory")
        provider = layer.dataProvider()
        provider.addAttributes([
            QgsField("Режим", QVariant.String),
            QgsField("Скважин", QVariant.Int),
            QgsField("Длина_км", QVariant.Double),
        ])
        layer.updateFields()
        points = []
        if plan.start_point is not None:
            points.append(QgsPointXY(*plan.start_point))
        points.extend(QgsPointXY(stop.lon, stop.lat) for stop in plan.stops)
        if plan.closed and plan.stops:
            points.append(QgsPointXY(plan.stops[0].lon, plan.stops[0].lat))
        feature = QgsFeature(layer.fields())
        feature.setGeometry(QgsGeometry.fromPolylineXY(points))
        feature.setAttributes([str(mode_label), len(plan.stops), plan.distance_m / 1000.0])
        provider.addFeature(feature)
        layer.updateExtents()
        layer.setCustomProperty(self.PROPERTY, True)
        return layer

    def _order_layer(self, plan):
        layer = QgsVectorLayer("Point?crs=EPSG:4326", "Порядок объезда Well Importer", "memory")
        provider = layer.dataProvider()
        provider.addAttributes([
            QgsField("Порядок", QVariant.Int),
            QgsField("Номер", QVariant.String),
            QgsField("FID", QVariant.Int),
        ])
        layer.updateFields()
        features = []
        for index, stop in enumerate(plan.stops, start=1):
            feature = QgsFeature(layer.fields())
            feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(stop.lon, stop.lat)))
            feature.setAttributes([index, str(stop.number), int(stop.feature_id)])
            features.append(feature)
        provider.addFeatures(features)
        layer.updateExtents()
        layer.setCustomProperty(self.PROPERTY, True)
        return layer
