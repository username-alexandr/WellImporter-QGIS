# -*- coding: utf-8 -*-

def classFactory(iface):
    from .well_importer import WellImporter
    return WellImporter(iface)
