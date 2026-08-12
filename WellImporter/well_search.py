# -*- coding: utf-8 -*-

from .well_number_field import well_number_field_name


class WellSearchManager:
    """Поиск скважин по номеру и автоматическое приближение карты."""

    NUMBER_FIELDS = ("Номер скважины",)

    def find(self, layer, query):
        query = str(query).strip()
        if not query:
            return []
        field = self._number_field(layer)
        if not field:
            raise Exception("В точечном слое отсутствует поле номера скважины.")

        exact = []
        partial = []
        normalized_query = self._key(query)
        for feature in layer.getFeatures():
            value = str(feature[field]).strip()
            if self._key(value) == normalized_query:
                exact.append(feature)
            elif query.lower() in value.lower():
                partial.append(feature)
        return exact or partial

    def zoom(self, iface, layer, feature_ids):
        if not feature_ids:
            return
        layer.selectByIds([int(fid) for fid in feature_ids])
        canvas = iface.mapCanvas()
        canvas.zoomToSelected(layer)
        canvas.refresh()

    def _number_field(self, layer):
        return well_number_field_name(layer)

    def _key(self, value):
        text = str(value).strip().lower().replace("№", "").replace(" ", "")
        if text.isdigit():
            return text.lstrip("0") or "0"
        return text
