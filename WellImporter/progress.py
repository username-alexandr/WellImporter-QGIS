# -*- coding: utf-8 -*-

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QProgressDialog


class Progress:
    def __init__(self, iface, maximum, title):
        self.dialog = QProgressDialog(title, "Отмена", 0, maximum, iface.mainWindow())
        self.dialog.setWindowTitle("Well Importer")
        self.dialog.setWindowModality(Qt.WindowModal)
        self.dialog.setMinimumDuration(0)
        self.dialog.setValue(0)

    def set_value(self, value):
        self.dialog.setValue(value)

    def was_canceled(self):
        return self.dialog.wasCanceled()

    def close(self):
        self.dialog.close()
