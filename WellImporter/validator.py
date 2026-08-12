# -*- coding: utf-8 -*-


class Validator:
    """Проверка дублей по номеру скважины."""

    def __init__(self, layer, number_field):
        self.layer = layer
        self.number_field = number_field
        self.values = set()
        for feature in layer.getFeatures():
            value = feature[number_field]
            if value is not None:
                self.values.add(self._key(value))

    def exists(self, value):
        return self._key(value) in self.values

    def add(self, value):
        self.values.add(self._key(value))

    def _key(self, value):
        return str(value).strip().lower()
