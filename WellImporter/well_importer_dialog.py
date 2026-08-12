# -*- coding: utf-8 -*-

from qgis.PyQt import QtWidgets
from qgis.core import QgsProject, QgsWkbTypes

from .controller import ImportController
from .settings import PluginSettings
from .ui_well_importer import Ui_WellImporterDialog


class WellImporterDialog(QtWidgets.QDialog):
    DEFAULT_POINT_LAYER = "Скважины солевая съёмка"
    DEFAULT_POLYGON_LAYER = "Площадные круги"

    def __init__(self, iface, parent=None):
        super().__init__(parent or iface.mainWindow())
        self.iface = iface
        self.ui = Ui_WellImporterDialog()
        self.ui.setupUi(self)
        self.controller = ImportController(iface)
        self.settings = PluginSettings()

        self.ui.btnImport.clicked.connect(self.import_clicked)
        self.ui.btnRefreshLayers.clicked.connect(self.refresh_layers)
        self.ui.btnClose.clicked.connect(self.close)

        self.refresh_layers()
        self.restore_settings()

    def refresh_layers(self):
        point_text = self.ui.cmbPoints.currentText()
        polygon_text = self.ui.cmbCircles.currentText()

        self.ui.cmbPoints.clear()
        self.ui.cmbCircles.clear()

        for layer in QgsProject.instance().mapLayers().values():
            geom_type = QgsWkbTypes.geometryType(layer.wkbType())
            if geom_type == QgsWkbTypes.PointGeometry:
                self.ui.cmbPoints.addItem(layer.name(), layer.id())
            elif geom_type == QgsWkbTypes.PolygonGeometry:
                self.ui.cmbCircles.addItem(layer.name(), layer.id())

        self._select_combo_text(self.ui.cmbPoints, point_text or self.DEFAULT_POINT_LAYER)
        self._select_combo_text(self.ui.cmbCircles, polygon_text or self.DEFAULT_POLYGON_LAYER)

    def restore_settings(self):
        values = self.settings.load()
        self.ui.txtYear.setText(str(values["year"]))
        self.ui.spinArea.setValue(float(values["area"]))
        self.ui.chkSkipDuplicates.setChecked(bool(values["skip_duplicates"]))
        self._select_combo_text(self.ui.cmbPoints, values["point_layer"] or self.DEFAULT_POINT_LAYER)
        self._select_combo_text(self.ui.cmbCircles, values["polygon_layer"] or self.DEFAULT_POLYGON_LAYER)

    def save_settings(self):
        self.settings.save(
            self.ui.txtYear.text().strip(),
            self.ui.spinArea.value(),
            self.ui.cmbPoints.currentText(),
            self.ui.cmbCircles.currentText(),
            self.ui.chkSkipDuplicates.isChecked(),
        )

    def import_clicked(self):
        try:
            year = self.ui.txtYear.text().strip()
            if not year:
                raise Exception("Укажите год бурения.")

            point_layer_id = self.ui.cmbPoints.currentData()
            polygon_layer_id = self.ui.cmbCircles.currentData()
            if not point_layer_id:
                raise Exception("Не выбран точечный слой.")
            if not polygon_layer_id:
                raise Exception("Не выбран полигональный слой.")

            self.save_settings()

            result = self.controller.execute(
                point_layer_id=point_layer_id,
                polygon_layer_id=polygon_layer_id,
                year=year,
                area=self.ui.spinArea.value(),
                skip_duplicates=self.ui.chkSkipDuplicates.isChecked(),
            )

            message = (
                f"Готово. Строк: {result.parsed_records}; "
                f"точек: {result.added_points}; кругов: {result.added_circles}; "
                f"дублей пропущено: {result.skipped_duplicates}; ошибок: {result.errors}."
            )
            self.ui.lblStatus.setText(message)
            QtWidgets.QMessageBox.information(self, "Well Importer", message)
        except Exception as exc:
            self.ui.lblStatus.setText(f"Ошибка: {exc}")
            QtWidgets.QMessageBox.critical(self, "Well Importer", str(exc))

    def _select_combo_text(self, combo, text):
        index = combo.findText(text)
        if index >= 0:
            combo.setCurrentIndex(index)
