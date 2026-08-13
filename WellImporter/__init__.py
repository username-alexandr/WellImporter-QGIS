# -*- coding: utf-8 -*-

def classFactory(iface):
    """Точка входа QGIS для актуальной реализации Well Importer."""
    from .well_importer_v22 import WellImporterV22
    return WellImporterV22(iface)
