# -*- coding: utf-8 -*-

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QProgressDialog


class Progress:
    """Окно прогресса импорта с возможностью отмены."""

    def __init__(self, iface, maximum, title="Выполнение..."):
        """Создаёт окно прогресса."""
        self.dialog = QProgressDialog(title, "Отмена", 0, max(1, int(maximum)), iface.mainWindow())
        self.dialog.setWindowModality(Qt.WindowModal)
        self.dialog.setMinimumDuration(0)
        self.dialog.setAutoClose(False)
        self.dialog.setAutoReset(False)

    def set_value(self, value):
        """Устанавливает текущее значение."""
        self.dialog.setValue(value)

    def was_canceled(self):
        """Проверяет отмену пользователем."""
        return self.dialog.wasCanceled()

    def close(self):
        """Закрывает окно прогресса."""
        self.dialog.close()
