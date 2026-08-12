# -*- coding: utf-8 -*-

from qgis.PyQt import QtCore
from qgis.core import (
    QgsCoordinateTransform,
    QgsFeatureRequest,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsRectangle,
    QgsSpatialIndex,
    QgsWkbTypes,
)
from qgis.gui import QgsMapTool, QgsRubberBand


class FieldRectangleSelectionTool(QgsMapTool):
    """Выделяет объекты заданного слоя прямоугольником на карте.

    Инструмент используется мастером выезда и для скважин, и для земельных
    участков. После завершения выделения он возвращает список FID и освобождает
    rubber-band. Сам мастер может быть временно скрыт, пока пользователь рисует
    область на основном canvas QGIS.
    """

    selectionFinished = QtCore.pyqtSignal(list)
    selectionCanceled = QtCore.pyqtSignal()

    def __init__(self, canvas, layer):
        super().__init__(canvas)
        self.canvas = canvas
        self.layer = layer
        self.start_point = None
        self.rubber = QgsRubberBand(canvas, QgsWkbTypes.PolygonGeometry)
        self.rubber.setWidth(2)

    def canvasPressEvent(self, event):
        if event.button() == QtCore.Qt.RightButton:
            self.cancel()
            return
        self.start_point = QgsPointXY(event.mapPoint())
        self._update_rubber(self.start_point)

    def canvasMoveEvent(self, event):
        if self.start_point is not None:
            self._update_rubber(QgsPointXY(event.mapPoint()))

    def canvasReleaseEvent(self, event):
        if self.start_point is None:
            return
        end_point = QgsPointXY(event.mapPoint())
        rect = QgsRectangle(self.start_point, end_point)
        self.start_point = None
        self.rubber.reset(QgsWkbTypes.PolygonGeometry)
        if rect.isEmpty():
            self.selectionFinished.emit([])
            return

        geometry = QgsGeometry.fromRect(rect)
        canvas_crs = self.canvas.mapSettings().destinationCrs()
        if canvas_crs != self.layer.crs():
            transform = QgsCoordinateTransform(
                canvas_crs, self.layer.crs(), QgsProject.instance()
            )
            geometry.transform(transform)

        request = QgsFeatureRequest().setFilterRect(geometry.boundingBox())
        ids = []
        for feature in self.layer.getFeatures(request):
            if not feature.hasGeometry() or feature.geometry().isEmpty():
                continue
            if feature.geometry().intersects(geometry):
                ids.append(feature.id())
        self.layer.selectByIds(ids)
        self.selectionFinished.emit(ids)

    def keyPressEvent(self, event):
        if event.key() == QtCore.Qt.Key_Escape:
            self.cancel()
        else:
            super().keyPressEvent(event)

    def deactivate(self):
        self.rubber.reset(QgsWkbTypes.PolygonGeometry)
        super().deactivate()

    def cancel(self):
        self.start_point = None
        self.rubber.reset(QgsWkbTypes.PolygonGeometry)
        self.selectionCanceled.emit()

    def _update_rubber(self, end_point):
        rect = QgsRectangle(self.start_point, end_point)
        self.rubber.setToGeometry(QgsGeometry.fromRect(rect), None)
        self.rubber.show()


class FieldScopeManager:
    """Подготавливает набор скважин для выезда по выбранной территории."""

    MODE_ALL = "all"
    MODE_SELECTED_WELLS = "selected_wells"
    MODE_SELECTED_PARCELS = "selected_parcels"
    MODE_MAP_AREA = "map_area"

    def __init__(self, project=None):
        self.project = project or QgsProject.instance()

    def wells_inside_selected_parcels(self, point_layer, parcel_layer):
        """Выделяет все скважины внутри одного или нескольких выбранных участков."""
        parcels = list(parcel_layer.selectedFeatures())
        if not parcels:
            raise Exception(
                "Не выбраны земельные участки. Выделите один или несколько участков на карте."
            )

        parcel_geometries = [
            QgsGeometry(feature.geometry())
            for feature in parcels
            if feature.hasGeometry() and not feature.geometry().isEmpty()
        ]
        if not parcel_geometries:
            raise Exception("У выбранных земельных участков отсутствует геометрия.")

        transform = QgsCoordinateTransform(
            point_layer.crs(), parcel_layer.crs(), self.project
        )
        selected_ids = []
        for point in point_layer.getFeatures():
            if not point.hasGeometry() or point.geometry().isEmpty():
                continue
            geometry = QgsGeometry(point.geometry())
            geometry.transform(transform)
            if any(parcel.intersects(geometry) for parcel in parcel_geometries):
                selected_ids.append(point.id())

        point_layer.selectByIds(selected_ids)
        return {
            "mode": self.MODE_SELECTED_PARCELS,
            "selected_parcels": len(parcels),
            "selected_wells": len(selected_ids),
            "well_ids": selected_ids,
            "parcel_ids": [feature.id() for feature in parcels],
        }

    def prepare(self, mode, point_layer, parcel_layer=None):
        """Нормализует выбранный режим территории перед упаковкой."""
        mode = str(mode or self.MODE_ALL)
        if mode == self.MODE_ALL:
            return {
                "mode": mode,
                "selected_wells": int(point_layer.featureCount()),
                "selected_only": False,
            }

        if mode == self.MODE_SELECTED_PARCELS:
            if parcel_layer is None:
                raise Exception("Не удалось определить слой земельных участков.")
            result = self.wells_inside_selected_parcels(point_layer, parcel_layer)
            if not result["selected_wells"]:
                raise Exception("В выбранных земельных участках скважины не найдены.")
            result["selected_only"] = True
            return result

        # MODE_SELECTED_WELLS и MODE_MAP_AREA используют выделение точек,
        # которое уже сформировано пользователем или инструментом рамки.
        count = int(point_layer.selectedFeatureCount())
        if count <= 0:
            raise Exception("Для выбранного режима нет выделенных скважин.")
        return {
            "mode": mode,
            "selected_wells": count,
            "selected_only": True,
            "well_ids": [feature.id() for feature in point_layer.selectedFeatures()],
        }
