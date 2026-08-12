# -*- coding: utf-8 -*-

def classFactory(iface):
    """
    Точка входа QGIS.

    QGIS вызывает эту функцию при загрузке плагина. Функция возвращает
    экземпляр основного класса плагина WellImporter.
    """
    from .well_importer import WellImporter
    return WellImporter(iface)
