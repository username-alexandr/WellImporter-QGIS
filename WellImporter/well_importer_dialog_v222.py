# -*- coding: utf-8 -*-

from .spatial_circle_repair import SpatialCircleRepairManager
from .well_importer_dialog import WellImporterDialog
from .robust_file_importer import RobustExcelFileImporter


class WellImporterDialogV222(WellImporterDialog):
    """Главное окно с исправленной достройкой кругов и устойчивым CSV/TXT-декодером."""

    def __init__(self, iface, parent=None):
        super().__init__(iface, parent)
        self.controller.circle_repair = SpatialCircleRepairManager()
        self.file_importer = RobustExcelFileImporter()
