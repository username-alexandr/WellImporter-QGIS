# -*- coding: utf-8 -*-

def classFactory(iface):
    """Точка входа QGIS для актуальной реализации Well Importer."""
    from .well_importer_v22_shortcuts import WellImporterV22Shortcuts
    return WellImporterV22Shortcuts(iface)
