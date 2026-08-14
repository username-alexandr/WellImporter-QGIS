# -*- coding: utf-8 -*-

from .spatial_circle_repair import SpatialCircleRepairManager
from .well_importer_dialog import WellImporterDialog


class WellImporterDialogV222(WellImporterDialog):
    """Главное окно с исправленной пространственной достройкой кругов."""

    def __init__(self, iface, parent=None):
        super().__init__(iface, parent)
        self.controller.circle_repair = SpatialCircleRepairManager()
