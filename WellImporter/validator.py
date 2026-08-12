# -*- coding: utf-8 -*-

class Validator:
    """
    Модуль проверки дублей.

    Загружает существующие номера скважин и проверяет, есть ли такой номер.
    """

    def __init__(self, layer, number_field):
        """Сохраняет слой и имя поля."""
        self.layer = layer
        self.number_field = number_field
        self._existing = None

    def _load_existing(self):
        """Загружает номера скважин в память."""
        if self._existing is not None:
            return
        self._existing = set()
        if self.layer.fields().indexFromName(self.number_field) < 0:
            return
        for feature in self.layer.getFeatures():
            value = feature[self.number_field]
            if value is not None:
                self._existing.add(str(value).strip())

    def exists(self, number):
        """Проверяет наличие номера."""
        self._load_existing()
        return str(number).strip() in self._existing

    def remember(self, number):
        """Запоминает добавленный номер."""
        self._load_existing()
        self._existing.add(str(number).strip())
