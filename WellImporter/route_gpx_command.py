# -*- coding: utf-8 -*-

from qgis.PyQt.QtWidgets import QFileDialog, QMessageBox

from .gpx_tools import GpxRouteExporter


class RouteGpxExportCommand:
    """Экспортирует последний рассчитанный маршрут текущей сессии."""

    def __init__(self, iface, route_planner):
        self.iface = iface
        self.route_planner = route_planner
        self.exporter = GpxRouteExporter()

    def run(self):
        preview = self.route_planner.preview
        plan = getattr(preview, "last_plan", None)
        if plan is None:
            QMessageBox.information(
                self.iface.mainWindow(), "Экспорт GPX",
                "Сначала рассчитайте маршрут через «Планировщик маршрута».",
            )
            return
        file_path, _ = QFileDialog.getSaveFileName(
            self.iface.mainWindow(), "Экспорт маршрута GPX",
            "Маршрут_скважин.gpx", "GPX (*.gpx)",
        )
        if not file_path:
            return
        try:
            result = self.exporter.export(
                plan, file_path,
                route_name=getattr(preview, "last_mode_label", "") or "Маршрут Well Importer",
            )
            QMessageBox.information(
                self.iface.mainWindow(), "Экспорт GPX",
                f"Маршрут сохранён:\n{result['path']}\n\nСкважин: {result['waypoints']}",
            )
        except Exception as exc:
            QMessageBox.critical(self.iface.mainWindow(), "Экспорт GPX", str(exc))
