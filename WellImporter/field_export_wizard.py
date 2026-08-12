# -*- coding: utf-8 -*-

from qgis.PyQt import QtCore, QtGui, QtWidgets

from .field_scope import FieldRectangleSelectionTool, FieldScopeManager
from .severity import Severity


class FieldExportWizard(QtWidgets.QWizard):
    """Мастер выезда: анализ → рекомендации → территория → упаковка.

    Выбор территории выполняется прямо из мастера. Для режимов «участки» и
    «область скважин» окно временно скрывается, пользователь рисует рамку на
    основной карте QGIS, после чего мастер автоматически возвращается.
    """

    def __init__(
        self,
        preparation_report,
        selected_count=0,
        parent=None,
        iface=None,
        point_layer=None,
        parcel_layer=None,
    ):
        super().__init__(parent)
        self.report = preparation_report or {}
        self.iface = iface
        self.point_layer = point_layer
        self.parcel_layer = parcel_layer
        self.selected_count = int(
            point_layer.selectedFeatureCount()
            if point_layer is not None else (selected_count or 0)
        )
        self.selected_parcel_count = int(
            parcel_layer.selectedFeatureCount() if parcel_layer is not None else 0
        )
        self._map_tool = None
        self._previous_map_tool = None

        self.setWindowTitle("Мастер подготовки проекта для выезда — Well Importer")
        self.resize(880, 650)
        self.setOption(QtWidgets.QWizard.NoBackButtonOnStartPage, True)

        self._build_analysis_page()
        self._build_recommendations_page()
        self._build_scope_page()
        self._build_package_page()

    def _build_analysis_page(self):
        page = QtWidgets.QWizardPage()
        page.setTitle("1. Анализ проекта")
        layout = QtWidgets.QVBoxLayout(page)

        counts = self.report.get("severity_counts", {})
        summary = QtWidgets.QLabel(
            "Перед упаковкой Well Importer анализирует рабочие слои и проект. "
            f"Критических: <b>{counts.get(Severity.CRITICAL, 0)}</b>; "
            f"ошибок: <b>{counts.get(Severity.ERROR, 0)}</b>; "
            f"предупреждений: <b>{counts.get(Severity.WARNING, 0)}</b>."
        )
        summary.setWordWrap(True)
        layout.addWidget(summary)

        checks = self.report.get("checks", [])
        self.analysis_table = QtWidgets.QTableWidget(len(checks), 3, page)
        self.analysis_table.setHorizontalHeaderLabels(["Серьёзность", "Проверка", "Результат"])
        self.analysis_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.analysis_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.analysis_table.verticalHeader().setVisible(False)
        for row, check in enumerate(checks):
            severity = Severity.normalize(check.get("severity"))
            values = [Severity.label(severity), check.get("title", ""), check.get("message", "")]
            color = QtGui.QColor(*Severity.COLORS[severity])
            for col, value in enumerate(values):
                item = QtWidgets.QTableWidgetItem(str(value))
                item.setBackground(color)
                self.analysis_table.setItem(row, col, item)
        header = self.analysis_table.horizontalHeader()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.Stretch)
        layout.addWidget(self.analysis_table, 1)
        self.addPage(page)

    def _build_recommendations_page(self):
        page = QtWidgets.QWizardPage()
        page.setTitle("2. Рекомендации перед выездом")
        layout = QtWidgets.QVBoxLayout(page)
        recommendations = self._recommendations()
        intro = QtWidgets.QLabel(
            "Рекомендации сформированы автоматически из результатов анализа. "
            "Критические проблемы блокируют упаковку; остальные можно устранить до выезда или принять осознанно."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.recommendations = QtWidgets.QTreeWidget()
        self.recommendations.setHeaderLabels(["Приоритет", "Рекомендация"])
        self.recommendations.setRootIsDecorated(False)
        for item in recommendations:
            severity = Severity.normalize(item.get("severity"))
            row = QtWidgets.QTreeWidgetItem([
                Severity.label(severity), str(item.get("message", "")),
            ])
            color = QtGui.QColor(*Severity.COLORS[severity])
            row.setBackground(0, color)
            row.setBackground(1, color)
            self.recommendations.addTopLevelItem(row)
        self.recommendations.header().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        self.recommendations.header().setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        layout.addWidget(self.recommendations, 1)
        if not recommendations:
            ok = QtWidgets.QLabel("Проект готов к переходу к этапу упаковки. Существенных рекомендаций нет.")
            ok.setWordWrap(True)
            layout.addWidget(ok)
        self.addPage(page)

    def _build_scope_page(self):
        page = QtWidgets.QWizardPage()
        page.setTitle("3. Территория и объекты для упаковки")
        layout = QtWidgets.QVBoxLayout(page)

        self.radio_all = QtWidgets.QRadioButton("Все объекты рабочих слоёв")
        self.radio_selected = QtWidgets.QRadioButton()
        self.radio_parcels = QtWidgets.QRadioButton()
        self.radio_map_area = QtWidgets.QRadioButton()
        self._update_scope_labels()

        self.radio_selected.setEnabled(self.selected_count > 0)
        self.radio_parcels.setEnabled(self.parcel_layer is not None)
        self.radio_map_area.setEnabled(self.point_layer is not None and self.iface is not None)

        self.radio_selected.setChecked(self.selected_count > 0)
        self.radio_all.setChecked(self.selected_count <= 0)

        layout.addWidget(self.radio_all)
        layout.addWidget(self.radio_selected)

        parcel_box = QtWidgets.QGroupBox("Область по земельным участкам")
        parcel_layout = QtWidgets.QVBoxLayout(parcel_box)
        parcel_layout.addWidget(self.radio_parcels)
        self.btnSelectParcels = QtWidgets.QPushButton("Выбрать один или несколько участков рамкой на карте")
        self.btnSelectParcels.setEnabled(self.parcel_layer is not None and self.iface is not None)
        self.btnSelectParcels.clicked.connect(self._select_parcels_on_map)
        parcel_layout.addWidget(self.btnSelectParcels)
        parcel_note = QtWidgets.QLabel(
            "После выбора участков Well Importer автоматически включит в пакет все скважины, "
            "расположенные внутри выбранных полигонов."
        )
        parcel_note.setWordWrap(True)
        parcel_layout.addWidget(parcel_note)
        layout.addWidget(parcel_box)

        area_box = QtWidgets.QGroupBox("Область по скважинам")
        area_layout = QtWidgets.QVBoxLayout(area_box)
        area_layout.addWidget(self.radio_map_area)
        self.btnSelectArea = QtWidgets.QPushButton("Выделить область скважин рамкой на карте")
        self.btnSelectArea.setEnabled(self.point_layer is not None and self.iface is not None)
        self.btnSelectArea.clicked.connect(self._select_wells_area_on_map)
        area_layout.addWidget(self.btnSelectArea)
        layout.addWidget(area_box)

        cad_note = QtWidgets.QLabel(
            "Перед упаковкой земельный участок и кадастровый номер будут определены автоматически. "
            "Поля WI_PARCEL и WI_CAD попадут в выездной GeoPackage вместе со скважинами."
        )
        cad_note.setWordWrap(True)
        layout.addWidget(cad_note)
        layout.addStretch(1)
        self.scope_page_id = self.addPage(page)

    def _build_package_page(self):
        page = QtWidgets.QWizardPage()
        page.setTitle("4. Упаковка выездного комплекта")
        layout = QtWidgets.QVBoxLayout(page)

        self.chk_store_styles = QtWidgets.QCheckBox("Сохранить оформление слоёв внутри GeoPackage")
        self.chk_store_styles.setChecked(True)
        self.chk_create_project = QtWidgets.QCheckBox("Создать отдельный проект QGIS (.qgz)")
        self.chk_create_project.setChecked(True)
        self.chk_relative_paths = QtWidgets.QCheckBox("Использовать относительные пути в выездном проекте")
        self.chk_relative_paths.setChecked(True)
        self.chk_readme = QtWidgets.QCheckBox("Создать памятку README с результатами анализа")
        self.chk_readme.setChecked(True)
        layout.addWidget(self.chk_store_styles)
        layout.addWidget(self.chk_create_project)
        layout.addWidget(self.chk_relative_paths)
        layout.addWidget(self.chk_readme)

        counts = self.report.get("severity_counts", {})
        self.lblPackageState = QtWidgets.QLabel()
        self.lblPackageState.setWordWrap(True)
        if counts.get(Severity.CRITICAL, 0):
            self.lblPackageState.setText(
                "<b>Упаковка заблокирована:</b> в анализе остались критические проблемы. "
                "Вернитесь к рекомендациям, устраните их и запустите мастер повторно."
            )
        else:
            self.lblPackageState.setText(
                "Анализ, рекомендации и выбор территории завершены. После нажатия «Готово» будет создан выездной комплект."
            )
        layout.addWidget(self.lblPackageState)
        layout.addStretch(1)
        self.addPage(page)

    def _select_parcels_on_map(self):
        if self.parcel_layer is None:
            return
        self.radio_parcels.setChecked(True)
        self._start_rectangle_selection(self.parcel_layer, "parcels")

    def _select_wells_area_on_map(self):
        if self.point_layer is None:
            return
        self.radio_map_area.setChecked(True)
        self._start_rectangle_selection(self.point_layer, "wells")

    def _start_rectangle_selection(self, layer, kind):
        canvas = self.iface.mapCanvas()
        self._previous_map_tool = canvas.mapTool()
        self._map_tool = FieldRectangleSelectionTool(canvas, layer)
        self._map_tool.selectionFinished.connect(
            lambda ids: self._rectangle_selection_finished(kind, ids)
        )
        self._map_tool.selectionCanceled.connect(self._rectangle_selection_canceled)
        self.iface.setActiveLayer(layer)
        self.hide()
        canvas.setMapTool(self._map_tool)
        self.iface.messageBar().pushMessage(
            "Well Importer",
            "Нарисуйте прямоугольник левой кнопкой мыши. Esc или правая кнопка — отмена.",
            level=0,
            duration=6,
        )

    def _rectangle_selection_finished(self, kind, ids):
        if kind == "parcels":
            self.selected_parcel_count = len(ids)
            self.radio_parcels.setChecked(True)
        else:
            self.selected_count = len(ids)
            self.radio_map_area.setChecked(True)
        self._update_scope_labels()
        self._restore_after_map_tool()

    def _rectangle_selection_canceled(self):
        self._restore_after_map_tool()

    def _restore_after_map_tool(self):
        if self.iface is not None:
            canvas = self.iface.mapCanvas()
            if self._map_tool is not None:
                canvas.unsetMapTool(self._map_tool)
            if self._previous_map_tool is not None:
                try:
                    canvas.setMapTool(self._previous_map_tool)
                except Exception:
                    pass
        self._map_tool = None
        self._previous_map_tool = None
        self.show()
        self.raise_()
        self.activateWindow()

    def _update_scope_labels(self):
        if hasattr(self, "radio_selected"):
            self.radio_selected.setText(
                f"Использовать уже выделенные скважины ({self.selected_count})"
            )
        if hasattr(self, "radio_parcels"):
            self.radio_parcels.setText(
                f"Выбранные земельные участки ({self.selected_parcel_count}) → автоматически выбрать скважины внутри"
            )
        if hasattr(self, "radio_map_area"):
            count = self.point_layer.selectedFeatureCount() if self.point_layer is not None else self.selected_count
            self.radio_map_area.setText(
                f"Область скважин, выделенная рамкой ({int(count)})"
            )

    def _recommendations(self):
        recommendations = []
        for check in self.report.get("checks", []):
            severity = Severity.normalize(check.get("severity"))
            if severity == Severity.INFO:
                continue
            title = str(check.get("title", "Проверка") or "Проверка")
            message = str(check.get("message", "") or "")
            action = self._action_for(title, severity)
            recommendations.append({
                "severity": severity,
                "message": f"{title}: {action} {message}".strip(),
            })
        recommendations.sort(
            key=lambda item: (
                -Severity.ORDER.get(Severity.normalize(item["severity"]), 0),
                item["message"].casefold(),
            )
        )
        return recommendations

    def _action_for(self, title, severity):
        title_lower = title.lower()
        if "редакт" in title_lower:
            return "Сохраните изменения перед упаковкой."
        if "связ" in title_lower:
            return "Исправьте пары точка/круг в Центре управления."
        if "геометр" in title_lower:
            return "Запустите полный аудит и мастер исправления геометрии."
        if "файл проекта" in title_lower:
            return "Сохраните рабочий QGIS-проект."
        if "оформ" in title_lower:
            return "Проверьте стили и внешние ресурсы оформления."
        if severity == Severity.CRITICAL:
            return "Устраните проблему до выезда."
        return "Проверьте замечание перед выездом."

    def scope_mode(self):
        if self.radio_parcels.isChecked():
            return FieldScopeManager.MODE_SELECTED_PARCELS
        if self.radio_map_area.isChecked():
            return FieldScopeManager.MODE_MAP_AREA
        if self.radio_selected.isChecked():
            return FieldScopeManager.MODE_SELECTED_WELLS
        return FieldScopeManager.MODE_ALL

    def validateCurrentPage(self):
        if self.currentId() == self.scope_page_id:
            mode = self.scope_mode()
            if mode == FieldScopeManager.MODE_SELECTED_PARCELS:
                count = self.parcel_layer.selectedFeatureCount() if self.parcel_layer is not None else 0
                if count <= 0:
                    QtWidgets.QMessageBox.warning(
                        self, "Территория выезда", "Выберите хотя бы один земельный участок."
                    )
                    return False
            elif mode in (FieldScopeManager.MODE_SELECTED_WELLS, FieldScopeManager.MODE_MAP_AREA):
                count = self.point_layer.selectedFeatureCount() if self.point_layer is not None else self.selected_count
                if count <= 0:
                    QtWidgets.QMessageBox.warning(
                        self, "Территория выезда", "Для выбранного режима нет выделенных скважин."
                    )
                    return False
        return super().validateCurrentPage()

    def accept(self):
        counts = self.report.get("severity_counts", {})
        if counts.get(Severity.CRITICAL, 0):
            QtWidgets.QMessageBox.critical(
                self,
                "Подготовка к выезду",
                "Упаковка невозможна, пока в анализе проекта есть критические замечания."
            )
            return
        super().accept()

    def reject(self):
        if self._map_tool is not None:
            self._restore_after_map_tool()
        super().reject()

    def options(self):
        mode = self.scope_mode()
        return {
            "scope_mode": mode,
            "selected_only": mode != FieldScopeManager.MODE_ALL,
            "store_styles": bool(self.chk_store_styles.isChecked()),
            "create_project": bool(self.chk_create_project.isChecked()),
            "relative_paths": bool(self.chk_relative_paths.isChecked()),
            "include_readme": bool(self.chk_readme.isChecked()),
        }
