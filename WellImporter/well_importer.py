# -*- coding: utf-8 -*-

import os
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QMessageBox

from .well_importer_dialog import WellImporterDialog
from .history_dialog import HistoryDialog
from .controller import ImportController


class WellImporter:
    """Основной класс плагина и его меню QGIS."""

    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.menu_name = "&Well Importer"
        self.actions = []
        self.dialog = None

    def initGui(self):
        """Создаёт меню управления Well Importer."""
        icon = QIcon(os.path.join(self.plugin_dir, "icon.png"))
        self.action_import = QAction(icon, "Well Importer — главное окно", self.iface.mainWindow())
        self.action_center = QAction(icon, "Центр управления", self.iface.mainWindow())
        self.action_history = QAction(icon, "История импортов", self.iface.mainWindow())
        self.action_undo = QAction(icon, "Отменить последний импорт", self.iface.mainWindow())
        self.action_help = QAction(icon, "Инструкция по импорту", self.iface.mainWindow())

        self.action_import.triggered.connect(self.run)
        self.action_center.triggered.connect(self.open_control_center)
        self.action_history.triggered.connect(self.show_history)
        self.action_undo.triggered.connect(self.undo_last_import)
        self.action_help.triggered.connect(self.show_help)

        self.actions = [
            self.action_import, self.action_center, self.action_history,
            self.action_undo, self.action_help,
        ]
        for action in self.actions:
            self.iface.addPluginToMenu(self.menu_name, action)
        self.iface.addToolBarIcon(self.action_import)

    def unload(self):
        for action in self.actions:
            self.iface.removePluginMenu(self.menu_name, action)
        if getattr(self, "action_import", None):
            self.iface.removeToolBarIcon(self.action_import)
        self.actions = []

    def run(self):
        self.dialog = WellImporterDialog(self.iface)
        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()

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

    def show_help(self):
        text = (
            "<b>Well Importer 2.0.6 — порядок работы</b><br><br>"
            "<b>1. Импорт:</b> поддерживаются буфер Excel, .xlsx/.csv/.txt и перетаскивание файла мышью в окно плагина.<br><br>"
            "<b>2. Координаты:</b> DD, DMS и UTM/проекционные координаты с преобразованием в WGS84.<br><br>"
            "<b>3. Профили:</b> сохраняйте наборы параметров. Встроен профиль «Солевая съёмка 33 га». Последние слои, год и рабочая папка запоминаются.<br><br>"
            "<b>4. Контроль качества:</b> проверяются обязательные атрибуты, площадь кругов, положение центра, дубли и подозрительные координаты.<br><br>"
            "<b>5. Автоисправление:</b> круги с неверной площадью можно перестроить, а смещённые круги — автоматически центрировать по точке скважины.<br><br>"
            "<b>6. Земельные участки:</b> модуль определяет полигон участка, в котором находится скважина, и переносит кадастровый номер в WI_CAD.<br><br>"
            "<b>7. Поиск:</b> поиск скважины по номеру автоматически выделяет объект и приближает карту.<br><br>"
            "<b>8. Карточка и карта-схема:</b> для выбранной скважины создаются PDF-карточка и PNG карта со шкалой масштаба, стрелкой севера и подписью.<br><br>"
            "<b>9. История:</b> поддерживаются поиск и фильтр по году, пакетная отмена и архивирование старых импортов.<br><br>"
            "<b>10. Центр управления:</b> единое окно объединяет обзор состояния, исправление, участки, поиск, архив, выезд и отчётность."
        )
        QMessageBox.information(self.iface.mainWindow(), "Инструкция Well Importer", text)
