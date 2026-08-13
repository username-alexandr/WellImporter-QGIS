# -*- coding: utf-8 -*-

def classFactory(iface):
    from .well_importer_v22_interface import WellImporterV22Interface
    return WellImporterV22Interface(iface)
