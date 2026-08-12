# -*- coding: utf-8 -*-

from pathlib import Path

from qgis.core import (
    QgsCoordinateTransform,
    QgsGeometry,
    QgsLayoutExporter,
    QgsLayoutItemLabel,
    QgsLayoutItemMap,
    QgsLayoutItemScaleBar,
    QgsLayoutPoint,
    QgsLayoutSize,
    QgsPrintLayout,
    QgsProject,
    QgsRectangle,
    QgsUnitTypes,
)
from qgis.PyQt.QtGui import QFont
from .well_number_field import well_number_field_name


class WellCardManager:
    """Формирует PDF-карточку и PNG карту-схему выбранной скважины."""

    NUMBER_FIELDS = ("Номер скважины",)
    YEAR_FIELDS = ("Год",)

    def __init__(self):
        self.project = QgsProject.instance()

    def export_pdf(self, point_layer, polygon_layer, point_feature, path, area_ha=33.0):
        layout = self._create_layout(point_layer, polygon_layer, point_feature, area_ha, card=True)
        path = str(Path(path).with_suffix(".pdf"))
        result = QgsLayoutExporter(layout).exportToPdf(path, QgsLayoutExporter.PdfExportSettings())
        if result != QgsLayoutExporter.Success:
            raise Exception(f"Не удалось сформировать PDF-карточку. Код: {result}")
        return path

    def export_map_png(self, point_layer, polygon_layer, point_feature, path, area_ha=33.0):
        layout = self._create_layout(point_layer, polygon_layer, point_feature, area_ha, card=False)
        path = str(Path(path).with_suffix(".png"))
        settings = QgsLayoutExporter.ImageExportSettings()
        settings.dpi = 200
        result = QgsLayoutExporter(layout).exportToImage(path, settings)
        if result != QgsLayoutExporter.Success:
            raise Exception(f"Не удалось сформировать карту-схему PNG. Код: {result}")
        return path

    def _create_layout(self, point_layer, polygon_layer, feature, area_ha, card=True):
        layout = QgsPrintLayout(self.project)
        layout.initializeDefaults()
        number = self._attribute(feature, point_layer, self.NUMBER_FIELDS, str(feature.id()))
        year = self._attribute(feature, point_layer, self.YEAR_FIELDS, "—")
        point = feature.geometry().asPoint()

        title = QgsLayoutItemLabel(layout)
        title.setText(f"Скважина №{number}" if card else f"Карта-схема скважины №{number}")
        title.setFont(QFont("Arial", 16, QFont.Bold))
        title.adjustSizeToText()
        layout.addLayoutItem(title)
        title.attemptMove(QgsLayoutPoint(15, 10, QgsUnitTypes.LayoutMillimeters))

        map_item = QgsLayoutItemMap(layout)
        layout.addLayoutItem(map_item)
        map_item.attemptMove(QgsLayoutPoint(15, 42 if card else 25, QgsUnitTypes.LayoutMillimeters))
        map_item.attemptResize(QgsLayoutSize(180, 190 if card else 240, QgsUnitTypes.LayoutMillimeters))
        map_item.setLayers([polygon_layer, point_layer])
        map_item.setExtent(self._map_extent(point_layer, polygon_layer, feature, number))
        map_item.setFrameEnabled(True)

        if card:
            info = QgsLayoutItemLabel(layout)
            cadastral = self._attribute(feature, point_layer, ("WI_CAD",), "—")
            parcel = self._attribute(feature, point_layer, ("WI_PARCEL",), "—")
            info.setText(
                f"Номер скважины: {number}    Год: {year}    Площадь круга: {float(area_ha):.2f} га\n"
                f"X: {point.x():.8f}    Y: {point.y():.8f}\n"
                f"Земельный участок: {parcel}    Кадастровый номер: {cadastral}"
            )
            info.setFont(QFont("Arial", 9))
            info.adjustSizeToText()
            layout.addLayoutItem(info)
            info.attemptMove(QgsLayoutPoint(15, 26, QgsUnitTypes.LayoutMillimeters))

        scale = QgsLayoutItemScaleBar(layout)
        scale.setStyle("Single Box")
        scale.setLinkedMap(map_item)
        scale.applyDefaultSettings()
        scale.applyDefaultSize()
        layout.addLayoutItem(scale)
        scale.attemptMove(QgsLayoutPoint(20, 242 if card else 270, QgsUnitTypes.LayoutMillimeters))

        north = QgsLayoutItemLabel(layout)
        north.setText("N\n↑")
        north.setFont(QFont("Arial", 18, QFont.Bold))
        north.adjustSizeToText()
        layout.addLayoutItem(north)
        north.attemptMove(QgsLayoutPoint(174, 48 if card else 31, QgsUnitTypes.LayoutMillimeters))

        footer = QgsLayoutItemLabel(layout)
        footer.setText("Well Importer — автоматическая карта-схема")
        footer.setFont(QFont("Arial", 8))
        footer.adjustSizeToText()
        layout.addLayoutItem(footer)
        footer.attemptMove(QgsLayoutPoint(15, 282, QgsUnitTypes.LayoutMillimeters))
        return layout

    def _map_extent(self, point_layer, polygon_layer, point_feature, number):
        polygon_field = self._number_field(polygon_layer)
        if polygon_field:
            for polygon in polygon_layer.getFeatures():
                if self._key(polygon[polygon_field]) == self._key(number):
                    geom = QgsGeometry(polygon.geometry())
                    if polygon_layer.crs() != self.project.crs():
                        geom.transform(QgsCoordinateTransform(polygon_layer.crs(), self.project.crs(), self.project))
                    rect = geom.boundingBox()
                    rect.scale(1.35)
                    return rect

        geom = QgsGeometry(point_feature.geometry())
        if point_layer.crs() != self.project.crs():
            geom.transform(QgsCoordinateTransform(point_layer.crs(), self.project.crs(), self.project))
        p = geom.asPoint()
        delta = 0.01 if self.project.crs().isGeographic() else 1000.0
        return QgsRectangle(p.x() - delta, p.y() - delta, p.x() + delta, p.y() + delta)

    def _number_field(self, layer):
        return well_number_field_name(layer)

    def _attribute(self, feature, layer, fields, default):
        names = layer.fields().names()
        for field in fields:
            if field in names:
                try:
                    value = str(feature[field]).strip()
                    return value if value else default
                except Exception:
                    pass
        return default

    def _key(self, value):
        text = str(value).strip().lower().replace("№", "").replace(" ", "")
        return text.lstrip("0") or "0" if text.isdigit() else text
