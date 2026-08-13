# -*- coding: utf-8 -*-

import os
from qgis.PyQt import QtCore
from qgis.PyQt.QtGui import QIcon, QKeySequence
from qgis.PyQt.QtWidgets import QAction

from .command_palette import CommandPaletteDialog
from .command_registry import CommandRegistry
from .gpx_track_command import GpxTrackImportCommand
from .well_importer import WellImporter


class WellImporterV22(WellImporter):
    """Расширения интерфейса ветки Well Importer 2.2.0."""

    def __init__(self, iface):
        super().__init__(iface)
        self.gpx_track = GpxTrackImportCommand(iface)
        self.command_registry = CommandRegistry()
        self.palette_dialog = None

    def initGui(self):
        super().initGui()
        icon = QIcon(os.path.join(self.plugin_dir, "icon.png"))

        self.action_track_gpx = QAction(
            icon, "Импорт фактического GPS-трека", self.iface.mainWindow()
        )
        self.action_track_gpx.triggered.connect(self.gpx_track.run)
        self.actions.append(self.action_track_gpx)
        self.iface.addPluginToMenu(self.menu_name, self.action_track_gpx)

        self.action_palette = QAction(
            icon, "Командная палитра", self.iface.mainWindow()
        )
        self.action_palette.setShortcut(QKeySequence("Ctrl+Shift+P"))
        self.action_palette.setShortcutContext(QtCore.Qt.ApplicationShortcut)
        self.action_palette.triggered.connect(self.show_command_palette)
        self.actions.append(self.action_palette)
        self.iface.addPluginToMenu(self.menu_name, self.action_palette)

        self._register_commands()

    def _register_commands(self):
        registry = CommandRegistry()
        specs = [
            ("main_window", self.action_import, "импорт скважин excel xlsx csv txt буфер вставить"),
            ("full_workflow", self.action_full_workflow, "полный рабочий цикл импорт проверка"),
            ("control_center", self.action_center, "центр управление аудит исправление статистика кадастр поиск выезд"),
            ("route_plan", self.action_route, "маршрут объезд оптимизация скважин"),
            ("route_export_gpx", self.action_route_gpx, "gpx экспорт маршрут навигатор"),
            ("track_import_gpx", self.action_track_gpx, "gps gpx трек выезд импорт фактический"),
            ("history", self.action_history, "история импорт партии"),
            ("undo_import", self.action_undo, "отмена откат импорт"),
            ("basemap_catalog", self.action_basemaps, "фон карта osm esri opentopomap"),
            ("basemap_next", self.action_basemap_next, "фон следующая карта переключить"),
            ("help", self.action_help, "инструкция помощь справка"),
        ]
        for command_id, action, keywords in specs:
            registry.register_action(command_id, action, keywords)
        self.command_registry = registry

    def show_command_palette(self):
        if self.palette_dialog is not None and self.palette_dialog.isVisible():
            self.palette_dialog.raise_()
            self.palette_dialog.activateWindow()
            return
        self.palette_dialog = CommandPaletteDialog(
            self.command_registry, self.iface.mainWindow()
        )
        self.palette_dialog.show()
        self.palette_dialog.raise_()
        self.palette_dialog.activateWindow()
