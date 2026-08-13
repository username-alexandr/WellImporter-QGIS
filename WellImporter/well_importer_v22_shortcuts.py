# -*- coding: utf-8 -*-

import os
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction

from .shortcut_dialog import ShortcutSettingsDialog
from .shortcut_manager import ShortcutManager
from .well_importer_v22 import WellImporterV22


class WellImporterV22Shortcuts(WellImporterV22):
    """Добавляет пользовательские горячие клавиши поверх командной палитры."""

    def __init__(self, iface):
        super().__init__(iface)
        self.shortcut_manager = ShortcutManager(iface)
        self.shortcut_actions = {}

    def initGui(self):
        super().initGui()
        icon = QIcon(os.path.join(self.plugin_dir, "icon.png"))
        self.action_shortcuts = QAction(
            icon, "Настроить горячие клавиши", self.iface.mainWindow()
        )
        self.action_shortcuts.triggered.connect(self.show_shortcut_settings)
        self.actions.append(self.action_shortcuts)
        self.iface.addPluginToMenu(self.menu_name, self.action_shortcuts)

        self.shortcut_actions = self.shortcut_manager.action_map(
            self.command_registry, self.action_palette
        )
        self.shortcut_manager.apply(self.shortcut_actions)

    def show_shortcut_settings(self):
        ShortcutSettingsDialog(
            self.shortcut_manager, self.shortcut_actions, self.iface.mainWindow()
        ).exec_()
