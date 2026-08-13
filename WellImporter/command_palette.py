# -*- coding: utf-8 -*-

from qgis.PyQt import QtCore, QtWidgets


class CommandPaletteDialog(QtWidgets.QDialog):
    """Быстрый поиск и запуск зарегистрированных команд Well Importer."""

    def __init__(self, registry, parent=None):
        super().__init__(parent)
        self.registry = registry
        self._visible_commands = []
        self.setWindowTitle("Командная палитра — Well Importer")
        self.resize(620, 430)
        self.setModal(False)
        self._build_ui()
        self._refresh("")

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        self.search = QtWidgets.QLineEdit(self)
        self.search.setPlaceholderText("Введите команду: импорт, маршрут, GPX, аудит…")
        self.search.textChanged.connect(self._refresh)
        self.search.returnPressed.connect(self._run_current)
        layout.addWidget(self.search)

        self.list = QtWidgets.QListWidget(self)
        self.list.itemDoubleClicked.connect(lambda _item: self._run_current())
        layout.addWidget(self.list)

        hint = QtWidgets.QLabel(
            "Enter — запустить • ↑/↓ — выбрать • Esc — закрыть • Ctrl+Shift+P — открыть палитру"
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

    def _refresh(self, query):
        query = str(query or "").strip().lower().replace("ё", "е")
        tokens = [token for token in query.split() if token]
        ranked = []
        for command in self.registry.commands():
            text = command.search_text
            if tokens and not all(token in text for token in tokens):
                continue
            title = command.title.lower().replace("ё", "е")
            if not query:
                score = 0
            elif title.startswith(query):
                score = 3
            elif query in title:
                score = 2
            else:
                score = 1
            ranked.append((score, command.title.lower(), command))
        ranked.sort(key=lambda item: (-item[0], item[1]))
        self._visible_commands = [item[2] for item in ranked]

        self.list.clear()
        for command in self._visible_commands:
            item = QtWidgets.QListWidgetItem(command.title)
            item.setData(QtCore.Qt.UserRole, command.command_id)
            self.list.addItem(item)
        if self.list.count():
            self.list.setCurrentRow(0)

    def _run_current(self):
        row = self.list.currentRow()
        if row < 0 or row >= len(self._visible_commands):
            return
        command = self._visible_commands[row]
        self.accept()
        command.trigger()

    def showEvent(self, event):
        super().showEvent(event)
        self.search.setFocus()
        self.search.selectAll()

    def keyPressEvent(self, event):
        if event.key() == QtCore.Qt.Key_Escape:
            self.reject()
            return
        if event.key() in (QtCore.Qt.Key_Down, QtCore.Qt.Key_Up):
            current = self.list.currentRow()
            step = 1 if event.key() == QtCore.Qt.Key_Down else -1
            if self.list.count():
                self.list.setCurrentRow((current + step) % self.list.count())
            return
        super().keyPressEvent(event)
