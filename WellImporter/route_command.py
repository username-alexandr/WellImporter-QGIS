# -*- coding: utf-8 -*-

from qgis.PyQt.QtWidgets import QInputDialog, QMessageBox
from qgis.core import QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsPointXY, QgsProject, QgsWkbTypes
from qgis.gui import QgsMapToolEmitPoint

from .route_optimizer import RouteOptimizer, RouteStop
from .route_preview import RoutePreviewManager
from .well_number_field import feature_well_number


class RoutePlannerCommand:
    """Запускает оптимизацию маршрута из меню Well Importer."""

    MODES = [
        ("От первой выбранной скважины", RouteOptimizer.MODE_FIRST),
        ("От выбранной точки на карте", RouteOptimizer.MODE_MAP_POINT),
        ("Замкнутый маршрут с возвратом в начало", RouteOptimizer.MODE_CLOSED),
    ]

    def __init__(self, iface):
        self.iface = iface
        self.project = QgsProject.instance()
        self.optimizer = RouteOptimizer()
        self.preview = RoutePreviewManager(iface)
        self.map_tool = None
        self.previous_tool = None
        self.pending = None

    def run(self):
        try:
            layer = self.iface.activeLayer()
            if layer is None or not hasattr(layer, "wkbType"):
                raise Exception("Сделайте точечный слой скважин активным.")
            if QgsWkbTypes.geometryType(layer.wkbType()) != QgsWkbTypes.PointGeometry:
                raise Exception("Активный слой должен быть точечным слоем скважин.")
            stops = self._selected_stops(layer)
            labels = [item[0] for item in self.MODES]
            label, ok = QInputDialog.getItem(
                self.iface.mainWindow(), "Планировщик маршрута", "Режим:", labels, 0, False
            )
            if not ok:
                return
            mode = dict(self.MODES)[label]
            if mode == RouteOptimizer.MODE_MAP_POINT:
                self.pending = (stops, mode, label)
                self._pick_start()
                return
            self._finish(stops, mode, label, None)
        except Exception as exc:
            QMessageBox.warning(self.iface.mainWindow(), "Планировщик маршрута", str(exc))

    def _selected_stops(self, layer):
        ids = list(layer.selectedFeatureIds())
        if len(ids) < 2:
            raise Exception("Выберите минимум две скважины.")
        transform = QgsCoordinateTransform(
            layer.crs(), QgsCoordinateReferenceSystem("EPSG:4326"), self.project
        )
        result = []
        for fid in ids:
            feature = layer.getFeature(fid)
            geometry = feature.geometry()
            if geometry is None or geometry.isEmpty():
                raise Exception(f"У FID {fid} отсутствует геометрия.")
            if geometry.isMultipart():
                points = geometry.asMultiPoint()
                if not points:
                    raise Exception(f"Не удалось прочитать точку FID {fid}.")
                point = points[0]
            else:
                point = geometry.asPoint()
            point = transform.transform(QgsPointXY(point))
            number = feature_well_number(feature, layer, "")
            if not number:
                raise Exception(f"У скважины FID {fid} не заполнен номер.")
            result.append(RouteStop(int(fid), str(number), float(point.x()), float(point.y())))
        return result

    def _pick_start(self):
        canvas = self.iface.mapCanvas()
        self.previous_tool = canvas.mapTool()
        self.map_tool = QgsMapToolEmitPoint(canvas)
        self.map_tool.canvasClicked.connect(self._start_clicked)
        canvas.setMapTool(self.map_tool)
        self.iface.messageBar().pushMessage(
            "Well Importer", "Щёлкните стартовую точку маршрута на карте.", duration=5
        )

    def _start_clicked(self, point, _button):
        try:
            canvas = self.iface.mapCanvas()
            transform = QgsCoordinateTransform(
                canvas.mapSettings().destinationCrs(),
                QgsCoordinateReferenceSystem("EPSG:4326"), self.project,
            )
            point = transform.transform(QgsPointXY(point))
            anchor = (float(point.x()), float(point.y()))
            stops, mode, label = self.pending
            self._finish(stops, mode, label, anchor)
        except Exception as exc:
            QMessageBox.warning(self.iface.mainWindow(), "Планировщик маршрута", str(exc))
        finally:
            self._restore_tool()
            self.pending = None

    def _finish(self, stops, mode, label, anchor):
        plan = self.optimizer.optimize(stops, mode=mode, start_point=anchor)
        self.preview.draw(plan, label)
        order = " → ".join(f"Скважина {stop.number}" for stop in plan.stops)
        if plan.closed:
            order += f" → Скважина {plan.stops[0].number}"
        QMessageBox.information(
            self.iface.mainWindow(), "Маршрут рассчитан",
            f"Длина: {plan.distance_m / 1000.0:.2f} км\n\n{order}",
        )

    def _restore_tool(self):
        canvas = self.iface.mapCanvas()
        if self.previous_tool is not None:
            canvas.setMapTool(self.previous_tool)
        elif self.map_tool is not None:
            try:
                canvas.unsetMapTool(self.map_tool)
            except Exception:
                pass
        self.map_tool = None
        self.previous_tool = None
