# -*- coding: utf-8 -*-

import os

from qgis.PyQt.QtCore import QCoreApplication, QSettings, QTranslator, qVersion
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction

from .well_importer_dialog import WellImporterDialog


class WellImporter:
    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.action = None
        self.dialog = None

    def tr(self, message):
        return QCoreApplication.translate("WellImporter", message)

    def initGui(self):
        icon_path = os.path.join(self.plugin_dir, "icon.png")
        self.action = QAction(QIcon(icon_path), self.tr("Well Importer"), self.iface.mainWindow())
        self.action.setObjectName("WellImporterAction")
        self.action.setStatusTip(self.tr("Импорт скважин из Excel и построение площадных кругов"))
        self.action.triggered.connect(self.run)

        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToVectorMenu(self.tr("Well Importer"), self.action)

    def unload(self):
        if self.action:
            self.iface.removePluginVectorMenu(self.tr("Well Importer"), self.action)
            self.iface.removeToolBarIcon(self.action)
            self.action = None
        if self.dialog:
            try:
                self.dialog.close()
            except Exception:
                pass
            self.dialog = None

    def run(self):
        if self.dialog is None:
            self.dialog = WellImporterDialog(self.iface)
        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()
