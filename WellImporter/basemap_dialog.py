# -*- coding: utf-8 -*-

from pathlib import Path

from qgis.PyQt import QtWidgets


class BasemapCatalogDialog(QtWidgets.QDialog):
    """Интерфейс каталога фоновых карт и подготовки разрешённого офлайн-кэша."""

    def __init__(self, catalog, parent=None):
        super().__init__(parent)
        self.catalog = catalog
        self.setWindowTitle("Каталог фоновых карт — Well Importer")
        self.resize(620, 420)
        self._build_ui()
        self._refresh()

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        note = QtWidgets.QLabel(
            "Быстро подключайте OSM, спутниковую и топографическую карту. Избранные источники "
            "переключаются одной кнопкой. Массовый офлайн-кэш включайте только при наличии права "
            "на скачивание тайлов выбранного сервиса."
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        form = QtWidgets.QFormLayout()
        self.cmb = QtWidgets.QComboBox()
        self.cmb.currentIndexChanged.connect(self._source_changed)
        form.addRow("Фоновая карта:", self.cmb)
        self.lblAttribution = QtWidgets.QLabel("—")
        self.lblAttribution.setWordWrap(True)
        form.addRow("Источник/атрибуция:", self.lblAttribution)
        layout.addLayout(form)

        self.chkFavorite = QtWidgets.QCheckBox("Добавить в избранные")
        self.chkOffline = QtWidgets.QCheckBox(
            "У меня есть разрешение на массовый офлайн-кэш этого источника"
        )
        self.chkFavorite.toggled.connect(self._favorite_changed)
        self.chkOffline.toggled.connect(self._offline_changed)
        layout.addWidget(self.chkFavorite)
        layout.addWidget(self.chkOffline)

        row = QtWidgets.QHBoxLayout()
        btnSwitch = QtWidgets.QPushButton("Показать на карте")
        btnCheck = QtWidgets.QPushButton("Проверить доступность")
        btnSwitch.clicked.connect(self._switch)
        btnCheck.clicked.connect(self._check)
        row.addWidget(btnSwitch)
        row.addWidget(btnCheck)
        layout.addLayout(row)

        cache_box = QtWidgets.QGroupBox("Офлайн-кэш текущей области")
        cache_layout = QtWidgets.QFormLayout(cache_box)
        self.spinMin = QtWidgets.QSpinBox()
        self.spinMin.setRange(0, 24)
        self.spinMin.setValue(10)
        self.spinMax = QtWidgets.QSpinBox()
        self.spinMax.setRange(0, 24)
        self.spinMax.setValue(17)
        cache_layout.addRow("Минимальный zoom:", self.spinMin)
        cache_layout.addRow("Максимальный zoom:", self.spinMax)
        self.btnCache = QtWidgets.QPushButton("Создать MBTiles для текущей области карты")
        self.btnCache.clicked.connect(self._cache)
        cache_layout.addRow(self.btnCache)
        layout.addWidget(cache_box)

        self.lblStatus = QtWidgets.QLabel("Готово.")
        self.lblStatus.setWordWrap(True)
        layout.addWidget(self.lblStatus)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.clicked.connect(self.accept)
        layout.addWidget(buttons)

    def _refresh(self, selected=None):
        favorites = self.catalog.favorites()
        names = favorites + [name for name in self.catalog.names() if name not in favorites]
        current = selected or self.cmb.currentText()
        self.cmb.blockSignals(True)
        self.cmb.clear()
        for name in names:
            suffix = " ★" if name in favorites else ""
            self.cmb.addItem(name + suffix, name)
        index = self.cmb.findData(current)
        if index < 0 and self.cmb.count():
            index = 0
        if index >= 0:
            self.cmb.setCurrentIndex(index)
        self.cmb.blockSignals(False)
        self._source_changed()

    def _name(self):
        return str(self.cmb.currentData() or "")

    def _source_changed(self):
        name = self._name()
        if not name:
            return
        definition = self.catalog.definition(name)
        self.lblAttribution.setText(definition.get("attribution", "—"))
        self.chkFavorite.blockSignals(True)
        self.chkOffline.blockSignals(True)
        self.chkFavorite.setChecked(bool(definition.get("favorite")))
        self.chkOffline.setChecked(bool(definition.get("offline_allowed")))
        self.chkFavorite.blockSignals(False)
        self.chkOffline.blockSignals(False)
        self.spinMax.setMaximum(int(definition.get("max_zoom", 24)))
        if self.spinMax.value() > self.spinMax.maximum():
            self.spinMax.setValue(self.spinMax.maximum())
        self.btnCache.setEnabled(bool(definition.get("offline_allowed")))

    def _favorite_changed(self, checked):
        name = self._name()
        if name:
            self.catalog.set_favorite(name, checked)
            self._refresh(name)

    def _offline_changed(self, checked):
        name = self._name()
        if not name:
            return
        if checked:
            answer = QtWidgets.QMessageBox.question(
                self,
                "Офлайн-кэш фоновой карты",
                "Подтвердите, что условия сервиса или ваша лицензия разрешают массовое скачивание "
                "тайлов для офлайн-использования. Well Importer не меняет условия провайдера.",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No,
            )
            if answer != QtWidgets.QMessageBox.Yes:
                self.chkOffline.blockSignals(True)
                self.chkOffline.setChecked(False)
                self.chkOffline.blockSignals(False)
                return
        self.catalog.set_offline_allowed(name, checked)
        self.btnCache.setEnabled(bool(checked))

    def _switch(self):
        try:
            layer = self.catalog.switch(self._name())
            self.lblStatus.setText(f"Активная фоновая карта: {layer.name()}")
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "Фоновая карта", str(exc))

    def _check(self):
        try:
            self.lblStatus.setText("Проверка подключения...")
            QtWidgets.QApplication.processEvents()
            result = self.catalog.check_availability(self._name())
            if result.get("available"):
                self.lblStatus.setText(
                    f"Источник доступен. HTTP {result.get('http_status', 0) or 'OK'}."
                )
            else:
                self.lblStatus.setText(
                    f"Источник недоступен: {result.get('error') or 'таймаут/нет ответа'}."
                )
        except Exception as exc:
            self.lblStatus.setText(str(exc))

    def _cache(self):
        try:
            name = self._name()
            default = Path.home() / f"WellImporter_{name.replace(' ', '_')}.mbtiles"
            path, _ = QtWidgets.QFileDialog.getSaveFileName(
                self, "Сохранить офлайн-кэш", str(default), "MBTiles (*.mbtiles)"
            )
            if not path:
                return
            self.lblStatus.setText("Создание офлайн-кэша. Операция может занять значительное время...")
            QtWidgets.QApplication.processEvents()
            result = self.catalog.cache_current_extent(
                name, path, self.spinMin.value(), self.spinMax.value()
            )
            self.lblStatus.setText(f"Офлайн-кэш создан: {result['path']}")
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "Офлайн-кэш", str(exc))
