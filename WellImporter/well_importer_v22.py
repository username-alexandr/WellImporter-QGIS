# -*- coding: utf-8 -*-

import os
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction

from .gpx_track_command import GpxTrackImportCommand
from .well_importer import WellImporter


class WellImporterV22(WellImporter):
    """Расширения интерфейса ветки Well Importer 2.2.0."""

    def __init__(self, iface):
        super().__init__(iface)
        self.gpx_track = GpxTrackImportCommand(iface)

    def initGui(self):
        super().initGui()
        icon = QIcon(os.path.join(self.plugin_dir, "icon.png"))
        action = QAction(icon, "Импорт фактического GPS-трека", self.iface.mainWindow())
        action.triggered.connect(self.gpx_track.run)
        self.action_track_gpx = action
        self.actions.append(action)
        self.iface.addPluginToMenu(self.menu_name, action)
