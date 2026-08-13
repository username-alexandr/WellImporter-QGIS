# -*- coding: utf-8 -*-

import os
from qgis.PyQt.QtCore import QSettings
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QMessageBox

from .command_palette import CommandPaletteDialog
from .command_registry import CommandRegistry
from .control_center import ControlCenterDialog
from .well_importer_dialog import WellImporterDialog
from .well_importer_v22_shortcuts import WellImporterV22Shortcuts


class WellImporterV22Interface(WellImporterV22Shortcuts):
    """Добавляет компактный и расширенный режимы интерфейса."""

    MODE_KEY = "WellImporter/interface_mode"
    COMPACT = "compact"
    EXPANDED = "expanded"

    def __init__(self, iface):
        super().__init__(iface)
        self.mode_settings = QSettings()

    def initGui(self):
        super().initGui()
        icon = QIcon(os.path.join(self.plugin_dir, "icon.png"))
        self.action_compact = QAction(icon, "Компактный интерфейс", self.iface.mainWindow())
        self.action_compact.setCheckable(True)
        self.action_compact.setChecked(self.is_compact())
        self.action_compact.toggled.connect(self.set_compact_mode)
        self.actions.append(self.action_compact)
        self.iface.addPluginToMenu(self.menu_name, self.action_compact)
        self.command_registry.register_action(
            "interface_mode", self.action_compact,
            "интерфейс компактный расширенный режим"
        )
        self.shortcut_actions = self.shortcut_manager.action_map(
            self.command_registry, self.action_palette
        )
        self.shortcut_manager.apply(self.shortcut_actions)
        self._apply_menu_mode()

    def is_compact(self):
        return self.mode_settings.value(self.MODE_KEY, self.EXPANDED, type=str) == self.COMPACT

    def set_compact_mode(self, checked):
        self.mode_settings.setValue(self.MODE_KEY, self.COMPACT if checked else self.EXPANDED)
        self.mode_settings.sync()
        self._apply_menu_mode()
        if self.dialog is not None:
            self._apply_main_dialog_mode(self.dialog)
        QMessageBox.information(
            self.iface.mainWindow(), "Well Importer",
            "Включён компактный режим." if checked else "Включён расширенный режим."
        )

    def _apply_menu_mode(self):
        compact = self.is_compact()
        self.action_full_workflow.setVisible(not compact)
        self.action_full_workflow.setEnabled(not compact)
        if hasattr(self, "action_compact"):
            self.action_compact.blockSignals(True)
            self.action_compact.setChecked(compact)
            self.action_compact.blockSignals(False)

    def _new_dialog(self):
        dialog = WellImporterDialog(self.iface)
        self._apply_main_dialog_mode(dialog)
        try:
            dialog.ui.btnControlCenter.clicked.disconnect()
        except Exception:
            pass
        dialog.ui.btnControlCenter.clicked.connect(lambda: self._open_center(dialog))
        return dialog

    def _apply_main_dialog_mode(self, dialog):
        compact = self.is_compact()
        for name in ("btnArchive", "btnExportField"):
            widget = getattr(dialog.ui, name, None)
            if widget is not None:
                widget.setVisible(not compact)
        dialog.setWindowTitle(
            "Well Importer — " + ("компактный режим" if compact else "расширенный режим")
        )

    def _open_center(self, main_dialog):
        center = ControlCenterDialog(main_dialog, main_dialog)
        if self.is_compact():
            keep = ("импорт", "обзор", "контроль", "поиск")
            for index in range(center.tabs.count() - 1, -1, -1):
                title = center.tabs.tabText(index).lower()
                if not any(token in title for token in keep):
                    center.tabs.removeTab(index)
        center.exec_()
        main_dialog.refresh_dashboard()

    def run(self):
        self.dialog = self._new_dialog()
        self.dialog.show(); self.dialog.raise_(); self.dialog.activateWindow()

    def run_full_workflow(self):
        self.dialog = self._new_dialog()
        self.dialog.show(); self.dialog.raise_(); self.dialog.activateWindow()
        self.dialog.run_full_workflow()

    def open_control_center(self):
        self.dialog = self._new_dialog()
        self.dialog.show(); self.dialog.raise_(); self.dialog.activateWindow()
        self._open_center(self.dialog)

    def show_command_palette(self):
        visible_registry = CommandRegistry()
        for command in self.command_registry.commands():
            if command.action.isVisible() and command.action.isEnabled():
                visible_registry.register_action(
                    command.command_id, command.action, command.keywords
                )
        self.palette_dialog = CommandPaletteDialog(
            visible_registry, self.iface.mainWindow()
        )
        self.palette_dialog.show(); self.palette_dialog.raise_(); self.palette_dialog.activateWindow()
