# -*- coding: utf-8 -*-

import re
from qgis.PyQt.QtCore import QVariant
from qgis.core import QgsField

DISPLAY_NAME = "Номер скважины"
LEGACY_FIELD = "WI_NUM"


def _normalize(value):
    text = str(value or "").strip().lower().replace("ё", "е").replace("№", "номер")
    return re.sub(r"[^0-9a-zа-я]+", "", text)


def _looks_like_well_number(value):
    value = _normalize(value)
    exact = {
        "номерскважины", "номерскваж", "номерскв", "номскважины", "номскв",
        "скважина", "wellnumber", "wellno", "wellid"
    }
    if value in exact:
        return True
    has_well = "скваж" in value or "скв" in value or "well" in value
    has_number = "номер" in value or value.startswith(("nom", "no", "id"))
    return bool(value and has_well and has_number)


def well_number_field_index(layer):
    fields = layer.fields()
    exact = fields.indexFromName(DISPLAY_NAME)
    if exact >= 0:
        return exact
    for index, field in enumerate(fields):
        if _looks_like_well_number(field.name()) or _looks_like_well_number(field.alias()):
            return index
    return -1


def well_number_field_name(layer):
    index = well_number_field_index(layer)
    return layer.fields()[index].name() if index >= 0 else None


def ensure_well_number_field(layer):
    index = well_number_field_index(layer)
    if index >= 0:
        return index
    before_count = len(layer.fields())
    if not layer.addAttribute(QgsField(DISPLAY_NAME, QVariant.String, len=64)):
        raise Exception(f"Не удалось создать поле «{DISPLAY_NAME}» в слое «{layer.name()}».")
    layer.updateFields()
    index = well_number_field_index(layer)
    if index >= 0:
        try:
            layer.setFieldAlias(index, DISPLAY_NAME)
        except Exception:
            pass
        return index
    if len(layer.fields()) > before_count:
        index = len(layer.fields()) - 1
        try:
            layer.setFieldAlias(index, DISPLAY_NAME)
        except Exception:
            pass
        return index
    raise Exception(f"QGIS не смог определить поле «{DISPLAY_NAME}» в слое «{layer.name()}».")


def feature_well_number(feature, layer, default=""):
    index = well_number_field_index(layer)
    if index < 0:
        return default
    try:
        value = feature[index]
    except Exception:
        return default
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def set_feature_well_number(feature, layer, number):
    index = ensure_well_number_field(layer)
    feature.setAttribute(index, str(number))
    return index
