# -*- coding: utf-8 -*-

from qgis.PyQt import QtGui, QtWidgets
from qgis.PyQt.QtGui import QKeySequence


class ShortcutSettingsDialog(QtWidgets.QDialog):
    """Редактор сочетаний клавиш Well Importer с подсветкой конфликтов."""

    def __init__(self, manager, actions, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.actions = dict(actions)
        self.command_ids = list(self.actions)
        self.editors = {}
        self.setWindowTitle("Горячие клавиши — Well Importer")
        self.resize(820, 540)
        self._build_ui()
        self._load_values(manager.load(self.actions))
        self.refresh_conflicts()

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        note = QtWidgets.QLabel(
            "Назначьте сочетания командам Well Importer. Конфликты выделяются красным. "
            "Дубли внутри Well Importer нельзя сохранить; конфликт с QGIS можно сохранить после предупреждения."
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        self.table = QtWidgets.QTableWidget(len(self.command_ids), 3, self)
        self.table.setHorizontalHeaderLabels(["Команда", "Сочетание", "Состояние"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        for row, command_id in enumerate(self.command_ids):
            action = self.actions[command_id]
            title = str(action.text()).replace("&", "").strip()
            title_item = QtWidgets.QTableWidgetItem(title)
            title_item.setData(QtWidgets.QTableWidgetItem.UserType, command_id)
            self.table.setItem(row, 0, title_item)
            editor = QtWidgets.QKeySequenceEdit(self)
            editor.keySequenceChanged.connect(lambda _value: self.refresh_conflicts())
            self.editors[command_id] = editor
            self.table.setCellWidget(row, 1, editor)
            self.table.setItem(row, 2, QtWidgets.QTableWidgetItem(""))
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.Stretch)
        layout.addWidget(self.table)

        tools = QtWidgets.QHBoxLayout()
        clear_button = QtWidgets.QPushButton("Очистить выбранное", self)
        clear_button.clicked.connect(self.clear_selected)
        defaults_button = QtWidgets.QPushButton("По умолчанию", self)
        defaults_button.clicked.connect(self.restore_defaults)
        tools.addWidget(clear_button)
        tools.addWidget(defaults_button)
        tools.addStretch(1)
        layout.addLayout(tools)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Save | QtWidgets.QDialogButtonBox.Cancel, self
        )
        buttons.accepted.connect(self.save_changes)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self):
        return {
            command_id: self.manager.normalize(editor.keySequence())
            for command_id, editor in self.editors.items()
        }

    def _load_values(self, values):
        for command_id, editor in self.editors.items():
            editor.blockSignals(True)
            editor.setKeySequence(QKeySequence(values.get(command_id, "")))
            editor.blockSignals(False)

    def refresh_conflicts(self):
        conflicts = self.manager.conflicts(self.actions, self.values())
        id_to_title = {
            command_id: str(action.text()).replace("&", "").strip()
            for command_id, action in self.actions.items()
        }
        red = QtGui.QColor(255, 210, 210)
        normal = QtGui.QBrush()
        for row, command_id in enumerate(self.command_ids):
            internal = conflicts["internal"].get(command_id, [])
            external = conflicts["external"].get(command_id, [])
            messages = []
            if internal:
                messages.append("Well Importer: " + ", ".join(id_to_title[item] for item in internal))
            if external:
                messages.append("QGIS: " + ", ".join(external[:3]))
            conflicted = bool(messages)
            status = self.table.item(row, 2)
            status.setText("Конфликт — " + "; ".join(messages) if conflicted else "OK")
            title = self.table.item(row, 0)
            if conflicted:
                title.setBackground(red)
                status.setBackground(red)
                self.editors[command_id].setStyleSheet("QKeySequenceEdit { background: #ffd2d2; }")
            else:
                title.setBackground(normal)
                status.setBackground(normal)
                self.editors[command_id].setStyleSheet("")
        return conflicts

    def clear_selected(self):
        rows = sorted({index.row() for index in self.table.selectionModel().selectedRows()})
        for row in rows:
            command_id = self.command_ids[row]
            self.editors[command_id].setKeySequence(QKeySequence())
        self.refresh_conflicts()

    def restore_defaults(self):
        self._load_values(self.manager.defaults(self.actions))
        self.refresh_conflicts()

    def save_changes(self):
        values = self.values()
        conflicts = self.refresh_conflicts()
        internal = any(conflicts["internal"].get(command_id) for command_id in self.command_ids)
        if internal:
            QtWidgets.QMessageBox.warning(
                self, "Горячие клавиши",
                "Есть одинаковые сочетания у команд Well Importer. Устраните красные конфликты перед сохранением."
            )
            return
        external = any(conflicts["external"].get(command_id) for command_id in self.command_ids)
        if external:
            answer = QtWidgets.QMessageBox.question(
                self, "Конфликт с QGIS",
                "Некоторые сочетания уже используются QGIS и выделены красным. Сохранить их несмотря на конфликт?",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No,
            )
            if answer != QtWidgets.QMessageBox.Yes:
                return
        self.manager.save(values)
        self.manager.apply(self.actions, values)
        self.accept()
