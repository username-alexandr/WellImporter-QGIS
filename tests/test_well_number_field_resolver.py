# -*- coding: utf-8 -*-
"""Regression test for logical «Номер скважины» field resolution without QGIS."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType
import sys


# Minimal QGIS stubs: the resolver itself only needs QVariant.String and QgsField
# at import time. This keeps the regression test runnable in ordinary CI.
qgis = ModuleType("qgis")
pyqt = ModuleType("qgis.PyQt")
qtcore = ModuleType("qgis.PyQt.QtCore")
core = ModuleType("qgis.core")


class QVariant:
    String = 10


class QgsField:
    def __init__(self, name, *_args, **_kwargs):
        self._name = name

    def name(self):
        return self._name


qtcore.QVariant = QVariant
core.QgsField = QgsField
sys.modules.setdefault("qgis", qgis)
sys.modules.setdefault("qgis.PyQt", pyqt)
sys.modules.setdefault("qgis.PyQt.QtCore", qtcore)
sys.modules.setdefault("qgis.core", core)

module_path = Path(__file__).resolve().parents[1] / "WellImporter" / "well_number_field.py"
spec = spec_from_file_location("well_number_field_under_test", module_path)
resolver = module_from_spec(spec)
spec.loader.exec_module(resolver)


class FakeField:
    def __init__(self, name, alias=None):
        self._name = name
        self._alias = alias

    def name(self):
        return self._name

    # Some QGIS/provider combinations expose no useful QgsField alias. The
    # resolver must still read the alias stored at QgsVectorLayer level.
    def alias(self):
        return self._alias or ""


class FakeFields(list):
    def indexFromName(self, name):
        for index, field in enumerate(self):
            if field.name() == name:
                return index
        return -1


class FakeLayer:
    def __init__(self, names, layer_aliases=None, field_aliases=None):
        self._fields = FakeFields(
            FakeField(name, (field_aliases or {}).get(index))
            for index, name in enumerate(names)
        )
        self._layer_aliases = dict(layer_aliases or {})

    def fields(self):
        return self._fields

    def fieldAlias(self, index):
        return self._layer_aliases.get(index, "")

    def attributeDisplayName(self, index):
        return self._layer_aliases.get(index) or self._fields[index].name()


def check(name, condition):
    if not condition:
        raise AssertionError(name)
    print("OK:", name)


# 1. Canonical physical field.
layer = FakeLayer(["id", "Номер скважины", "Год"])
check("canonical physical field", resolver.well_number_field_index(layer) == 1)

# 2. Exact user-visible alias exists only at QgsVectorLayer level. This is the
# runtime case that caused the Repair Wizard false error in QGIS.
layer = FakeLayer(["id", "well_num", "year"], layer_aliases={1: "Номер скважины"})
check("QGIS layer alias", resolver.well_number_field_index(layer) == 1)
check("physical name returned for alias", resolver.well_number_field_name(layer) == "well_num")

# 3. DBF/Shapefile-like truncated physical field name.
layer = FakeLayer(["id", "Номер сква", "Год"])
check("truncated Cyrillic field", resolver.well_number_field_index(layer) == 1)

# 4. Common transliterated physical name.
layer = FakeLayer(["id", "nomer_skv", "year"])
check("transliterated field", resolver.well_number_field_index(layer) == 1)

# 5. Unrelated fields must not be mistaken for a well number.
layer = FakeLayer(["id", "Год", "Площадь"])
check("unrelated fields rejected", resolver.well_number_field_index(layer) == -1)
