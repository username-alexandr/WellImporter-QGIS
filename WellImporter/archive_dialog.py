# -*- coding: utf-8 -*-

from qgis.PyQt import QtCore, QtWidgets


class ArchiveDialog(QtWidgets.QDialog):
    """Выбор старых партий импорта для переноса в архив."""

    def __init__(self, history_items, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Архивирование старых импортов — Well Importer")
        self.resize(900, 480)
        self._history_items = [
            item for item in history_items
            if item.get("batch_id") and not item.get("undone") and not item.get("archived")
        ]

        layout = QtWidgets.QVBoxLayout(self)
        info = QtWidgets.QLabel(
            "Выберите партии, которые нужно перенести из рабочих слоёв в отдельный GeoPackage. "
            "Сначала данные записываются в архив, и только после успешной записи удаляются из рабочих слоёв."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        self.table = QtWidgets.QTableWidget(len(self._history_items), 7, self)
        self.table.setHorizontalHeaderLabels([
            "Архив", "Дата", "Источник", "Год", "Площадь, га", "Точек", "Кругов"
        ])
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.verticalHeader().setVisible(False)

        # Самую новую активную партию не отмечаем автоматически.
        for row, item in enumerate(self._history_items):
            checkbox = QtWidgets.QTableWidgetItem()
            checkbox.setFlags(QtCore.Qt.ItemIsUserCheckable | QtCore.Qt.ItemIsEnabled)
            checkbox.setCheckState(QtCore.Qt.Unchecked if row == 0 else QtCore.Qt.Checked)
            checkbox.setData(QtCore.Qt.UserRole, item.get("batch_id"))
            self.table.setItem(row, 0, checkbox)

            values = [
                item.get("timestamp", ""),
                item.get("source", ""),
                str(item.get("year", "")),
                str(item.get("area_ha", "")),
                str(item.get("added_points", 0)),
                str(item.get("added_circles", 0)),
            ]
            for column, value in enumerate(values, start=1):
                self.table.setItem(row, column, QtWidgets.QTableWidgetItem(value))

        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)

        hint = QtWidgets.QLabel(
            "Подсказка: по умолчанию отмечены старые партии, а самая последняя оставлена в рабочих слоях."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        buttons = QtWidgets.QDialogButtonBox(self)
        self.btnArchive = buttons.addButton("Архивировать выбранные", QtWidgets.QDialogButtonBox.AcceptRole)
        buttons.addButton(QtWidgets.QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selected_batch_ids(self):
        """Возвращает идентификаторы отмеченных партий."""
        result = []
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and item.checkState() == QtCore.Qt.Checked:
                batch_id = item.data(QtCore.Qt.UserRole)
                if batch_id:
                    result.append(str(batch_id))
        return result
