# -*- coding: utf-8 -*-

from qgis.PyQt import QtCore, QtWidgets
from qgis.PyQt.QtGui import QKeySequence


class ShortcutManager:
    """Хранит пользовательские сочетания и обнаруживает конфликты."""

    PREFIX = "WellImporter/shortcuts"
    DEFAULTS = {"command_palette": "Ctrl+Shift+P"}

    def __init__(self, iface):
        self.iface = iface
        self.settings = QtCore.QSettings()

    def action_map(self, registry, palette_action):
        result = {command.command_id: command.action for command in registry.commands()}
        result["command_palette"] = palette_action
        return result

    def load(self, actions):
        result = {}
        for command_id in actions:
            default = self.DEFAULTS.get(command_id, "")
            raw = self.settings.value(f"{self.PREFIX}/{command_id}", default, type=str)
            result[command_id] = self.normalize(raw)
        return result

    def save(self, values):
        for command_id, sequence in values.items():
            self.settings.setValue(f"{self.PREFIX}/{command_id}", self.normalize(sequence))
        self.settings.sync()

    def defaults(self, actions):
        return {command_id: self.DEFAULTS.get(command_id, "") for command_id in actions}

    def apply(self, actions, values=None):
        values = values or self.load(actions)
        for command_id, action in actions.items():
            action.setShortcut(QKeySequence(self.normalize(values.get(command_id, ""))))
            action.setShortcutContext(QtCore.Qt.ApplicationShortcut)

    def conflicts(self, actions, values):
        normalized = {key: self.normalize(value) for key, value in values.items()}
        internal = {key: [] for key in actions}
        external = {key: [] for key in actions}
        reverse = {}
        for command_id, sequence in normalized.items():
            if sequence:
                reverse.setdefault(sequence, []).append(command_id)
        for ids in reverse.values():
            if len(ids) > 1:
                for command_id in ids:
                    internal[command_id] = [other for other in ids if other != command_id]

        managed = {id(action) for action in actions.values()}
        qgis_shortcuts = {}
        for action in self.iface.mainWindow().findChildren(QtWidgets.QAction):
            if id(action) in managed:
                continue
            title = str(action.text() or action.objectName() or "Команда QGIS").replace("&", "").strip()
            try:
                sequences = list(action.shortcuts())
            except Exception:
                sequences = [action.shortcut()]
            for sequence in sequences:
                text = self.normalize(sequence)
                if text:
                    qgis_shortcuts.setdefault(text, set()).add(title)
        for command_id, sequence in normalized.items():
            if sequence in qgis_shortcuts:
                external[command_id] = sorted(qgis_shortcuts[sequence])
        return {"internal": internal, "external": external}

    def normalize(self, sequence):
        key_sequence = sequence if isinstance(sequence, QKeySequence) else QKeySequence(str(sequence or ""))
        return key_sequence.toString(QKeySequence.PortableText)
