# -*- coding: utf-8 -*-

import os
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QMessageBox

from .well_importer_dialog import WellImporterDialog
from .history_dialog import HistoryDialog
from .controller import ImportController
from .basemap_catalog import BasemapCatalog
from .basemap_dialog import BasemapCatalogDialog
from .route_command import RoutePlannerCommand
from .route_gpx_command import RouteGpxExportCommand


class WellImporter:
    """Основной класс плагина и его меню QGIS."""

    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.menu_name = "&Well Importer"
        self.actions = []
        self.dialog = None
        self.basemaps = BasemapCatalog(iface)
        self.route_planner = RoutePlannerCommand(iface)
        self.route_gpx = RouteGpxExportCommand(iface, self.route_planner)

    def initGui(self):
        """Создаёт меню управления Well Importer."""
        icon = QIcon(os.path.join(self.plugin_dir, "icon.png"))
        self.action_import = QAction(icon, "Well Importer — главное окно", self.iface.mainWindow())
        self.action_center = QAction(icon, "Центр управления", self.iface.mainWindow())
        self.action_full_workflow = QAction(icon, "Полный рабочий цикл", self.iface.mainWindow())
        self.action_route = QAction(icon, "Планировщик маршрута", self.iface.mainWindow())
        self.action_route_gpx = QAction(icon, "Экспорт маршрута в GPX", self.iface.mainWindow())
        self.action_history = QAction(icon, "История импортов", self.iface.mainWindow())
        self.action_undo = QAction(icon, "Отменить последний импорт", self.iface.mainWindow())
        self.action_help = QAction(icon, "Инструкция по импорту", self.iface.mainWindow())
        self.action_basemaps = QAction(icon, "Каталог фоновых карт", self.iface.mainWindow())
        self.action_basemap_next = QAction(icon, "Следующая фоновая карта", self.iface.mainWindow())

        self.action_import.triggered.connect(self.run)
        self.action_center.triggered.connect(self.open_control_center)
        self.action_full_workflow.triggered.connect(self.run_full_workflow)
        self.action_route.triggered.connect(self.route_planner.run)
        self.action_route_gpx.triggered.connect(self.route_gpx.run)
        self.action_history.triggered.connect(self.show_history)
        self.action_undo.triggered.connect(self.undo_last_import)
        self.action_help.triggered.connect(self.show_help)
        self.action_basemaps.triggered.connect(self.show_basemap_catalog)
        self.action_basemap_next.triggered.connect(self.switch_next_basemap)

        self.actions = [
            self.action_import, self.action_full_workflow, self.action_center,
            self.action_route, self.action_route_gpx, self.action_history, self.action_undo,
            self.action_basemaps, self.action_basemap_next, self.action_help,
        ]
        for action in self.actions:
            self.iface.addPluginToMenu(self.menu_name, action)
        self.iface.addToolBarIcon(self.action_import)
        self.iface.addToolBarIcon(self.action_basemap_next)

    def unload(self):
        for action in self.actions:
            self.iface.removePluginMenu(self.menu_name, action)
        if getattr(self, "action_import", None):
            self.iface.removeToolBarIcon(self.action_import)
        if getattr(self, "action_basemap_next", None):
            self.iface.removeToolBarIcon(self.action_basemap_next)
        self.actions = []

    def run(self):
        self.dialog = WellImporterDialog(self.iface)
        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()

    def run_full_workflow(self):
        self.dialog = WellImporterDialog(self.iface)
        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()
        self.dialog.run_full_workflow()

    def open_control_center(self):
        self.dialog = WellImporterDialog(self.iface)
        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()
        self.dialog.open_control_center()

    def show_history(self):
        controller = ImportController(self.iface)
        HistoryDialog(controller.history.items(), self.iface.mainWindow()).exec_()

    def undo_last_import(self):
        controller = ImportController(self.iface)
        entry = controller.history.last_active()
        if not entry:
            QMessageBox.information(self.iface.mainWindow(), "Well Importer", "Нет импорта, который можно отменить.")
            return
        answer = QMessageBox.question(
            self.iface.mainWindow(), "Отменить последний импорт",
            f"Удалить партию от {entry.get('timestamp', '')}?\nИсточник: {entry.get('source', '')}",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if answer == QMessageBox.Yes:
            try:
                result = controller.undo_last_import()
                QMessageBox.information(
                    self.iface.mainWindow(), "Well Importer",
                    f"Удалено точек: {result['points']}\nУдалено кругов: {result['circles']}"
                )
            except Exception as exc:
                QMessageBox.critical(self.iface.mainWindow(), "Well Importer", str(exc))

    def show_basemap_catalog(self):
        BasemapCatalogDialog(self.basemaps, self.iface.mainWindow()).exec_()

    def switch_next_basemap(self):
        try:
            layer = self.basemaps.next_basemap()
            self.iface.messageBar().pushMessage("Well Importer", f"Фоновая карта: {layer.name()}", duration=3)
        except Exception as exc:
            QMessageBox.critical(self.iface.mainWindow(), "Фоновая карта", str(exc))

    def show_help(self):
        text = (
            "<b>Well Importer — порядок работы</b><br><br>"
            "<b>1. Импорт:</b> буфер Excel, .xlsx/.csv/.txt и перетаскивание файла.<br><br>"
            "<b>2. Координаты:</b> DD, DMS и UTM/проекционные координаты с преобразованием в WGS84.<br><br>"
            "<b>3. Профили:</b> сохранение наборов параметров и рабочих слоёв.<br><br>"
            "<b>4. Контроль:</b> аудит атрибутов, геометрии, пар точка-круг и дублей.<br><br>"
            "<b>5. Выезд:</b> подготовка офлайн-пакетов, синхронизация, планирование и GPX-маршрут.<br><br>"
            "<b>6. Центр управления:</b> обзор, исправление, кадастр, поиск, архив и отчётность."
        )
        QMessageBox.information(self.iface.mainWindow(), "Инструкция Well Importer", text)
