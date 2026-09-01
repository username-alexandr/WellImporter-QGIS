# -*- coding: utf-8 -*-

from .control_center_v224 import ControlCenterDialogV224
from .well_importer_dialog_v224 import WellImporterDialogV224
from .well_importer_v22_interface import WellImporterV22Interface


class WellImporterV224Interface(WellImporterV22Interface):
    """Фактически подключает runtime-логику 2.2.4 к интерфейсу плагина."""

    def _new_dialog(self):
        dialog = WellImporterDialogV224(self.iface)
        self._apply_main_dialog_mode(dialog)
        try:
            dialog.ui.btnControlCenter.clicked.disconnect()
        except Exception:
            pass
        dialog.ui.btnControlCenter.clicked.connect(lambda: self._open_center(dialog))
        return dialog

    def _open_center(self, main_dialog):
        center = ControlCenterDialogV224(main_dialog, main_dialog)
        if self.is_compact():
            keep = ("импорт", "обзор", "контроль", "поиск")
            for index in range(center.tabs.count() - 1, -1, -1):
                title = center.tabs.tabText(index).lower()
                if not any(token in title for token in keep):
                    center.tabs.removeTab(index)
        center.exec_()
        main_dialog.refresh_dashboard()
