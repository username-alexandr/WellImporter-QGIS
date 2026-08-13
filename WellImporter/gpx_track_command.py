# -*- coding: utf-8 -*-

from datetime import datetime
from pathlib import Path

from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtWidgets import QFileDialog, QMessageBox
from qgis.core import QgsFeature, QgsField, QgsGeometry, QgsPointXY, QgsProject, QgsVectorLayer

from .gpx_track import GpxTrackImporter


class GpxTrackImportCommand:
    """Импортирует фактический GPS-трек в отдельный memory-слой QGIS."""

    def __init__(self, iface):
        self.iface = iface
        self.project = QgsProject.instance()
        self.importer = GpxTrackImporter()

    def run(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self.iface.mainWindow(), "Импорт фактического GPS-трека", "", "GPX (*.gpx)"
        )
        if not file_path:
            return
        try:
            data = self.importer.parse(file_path)
            layer = self._create_layer(data)
            self.project.addMapLayer(layer)
            self.iface.setActiveLayer(layer)
            self.iface.zoomToActiveLayer()
            self.iface.mapCanvas().refresh()
            QMessageBox.information(
                self.iface.mainWindow(), "GPS-трек импортирован",
                f"Файл: {data.source_name}\nСегментов: {len(data.segments)}\n"
                f"Точек: {data.point_count}\nДлина: {data.distance_m / 1000.0:.2f} км",
            )
        except Exception as exc:
            QMessageBox.critical(self.iface.mainWindow(), "Импорт GPS-трека", str(exc))

    def _create_layer(self, data):
        layer_name = f"GPS-трек выезда — {Path(data.source_name).stem}"
        layer = QgsVectorLayer("LineString?crs=EPSG:4326", layer_name, "memory")
        provider = layer.dataProvider()
        provider.addAttributes([
            QgsField("Файл", QVariant.String),
            QgsField("Импортирован", QVariant.String),
            QgsField("Сегмент", QVariant.Int),
            QgsField("Точек", QVariant.Int),
            QgsField("Длина_км", QVariant.Double),
        ])
        layer.updateFields()
        imported_at = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        features = []
        for index, segment in enumerate(data.segments, start=1):
            feature = QgsFeature(layer.fields())
            feature.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(lon, lat) for lon, lat in segment]))
            feature.setAttributes([
                data.source_name,
                imported_at,
                index,
                len(segment),
                self.importer.segment_distance(segment) / 1000.0,
            ])
            features.append(feature)
        if not provider.addFeatures(features):
            raise Exception("QGIS не смог добавить геометрию GPS-трека.")
        layer.updateExtents()
        return layer
