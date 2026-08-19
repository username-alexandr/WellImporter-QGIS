# -*- coding: utf-8 -*-

def classFactory(iface):
    from .well_importer_v224_interface import WellImporterV224Interface
    return WellImporterV224Interface(iface)
