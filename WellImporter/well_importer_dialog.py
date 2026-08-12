# -*- coding: utf-8 -*-

from pathlib import Path
from datetime import datetime

from qgis.PyQt import QtCore, QtWidgets
from qgis.core import QgsProject, QgsWkbTypes, QgsMapLayerType

from .controller import ImportController
from .archive_dialog import ArchiveDialog
from .coordinate_checker import CoordinateChecker
from .duplicate_checker import DuplicateChecker
from .field_export_wizard import FieldExportWizard
from .field_sync import FieldSyncDialog
from .basemap_dialog import BasemapCatalogDialog
from .history_dialog import HistoryDialog
from .importer import ClipboardImporter, ExcelFileImporter
from .preview_dialog import PreviewDialog
from .settings import PluginSettings
from .severity import Severity
from .ui_well_importer import Ui_WellImporterDialog
from .profile_manager import ProfileManager
from .control_center import ControlCenterDialog


class WellImporterDialog(QtWidgets.QDialog):
    ADD_PROFILE_TOKEN = "__ADD_PROFILE__"
    ADD_PROFILE_LABEL = "+ Добавить профиль…"

    """Главное окно импорта скважин и управления данными."""

    DEFAULT_POINT_LAYER = "Скважины солевая съёмка"
    DEFAULT_POLYGON_LAYER = "Площадные круги"

    def __init__(self, iface, parent=None):
        super().__init__(parent or iface.mainWindow())
        self.iface = iface
        self.ui = Ui_WellImporterDialog()
        self.ui.setupUi(self)
        self.settings = PluginSettings()
        self.controller = ImportController(iface)
        self.coordinate_checker = CoordinateChecker()
        self.duplicate_checker = DuplicateChecker()
        self.clipboard_importer = ClipboardImporter()
        self.file_importer = ExcelFileImporter()
        self.profiles = ProfileManager()
        self.setAcceptDrops(True)
        self.ui.txtExcelPath.setAcceptDrops(False)
        self._connect_signals()
        self.refresh_layers()
        self.restore_settings()
        self.refresh_profiles()
        self.refresh_favorite_folders()
        self.refresh_dashboard()
        self.set_status("Готов к импорту.")

    def _connect_signals(self):
        self.ui.btnImport.clicked.connect(self.import_clicked)
        self.ui.btnCheckClipboard.clicked.connect(self.check_clipboard_clicked)
        self.ui.btnBrowseExcel.clicked.connect(self.browse_excel_clicked)
        self.ui.btnImportFile.clicked.connect(self.import_file_clicked)
        self.ui.btnRefreshLayers.clicked.connect(self.refresh_layers)
        self.ui.btnHistory.clicked.connect(self.show_history)
        self.ui.btnUndo.clicked.connect(self.undo_last_import)
        self.ui.btnArchive.clicked.connect(self.archive_old_imports)
        self.ui.btnExportField.clicked.connect(self.export_for_field)
        self.ui.btnDashboardRefresh.clicked.connect(self.refresh_dashboard)
        self.ui.btnControlCenter.clicked.connect(self.open_control_center)
        self.ui.btnSearchWell.clicked.connect(self.quick_search_well)
        self.ui.btnApplyProfile.clicked.connect(self.apply_profile)
        self.ui.cmbProfile.activated.connect(self.profile_combo_activated)
        self.ui.btnSaveProfile.clicked.connect(self.save_profile)
        self.ui.btnDeleteProfile.clicked.connect(self.delete_profile)
        self.ui.btnAddFavoriteFolder.clicked.connect(self.add_favorite_folder)
        self.ui.btnRemoveFavoriteFolder.clicked.connect(self.remove_favorite_folder)
        self.ui.cmbFavoriteFolder.currentIndexChanged.connect(self.favorite_folder_changed)
        self.ui.chkAutoCurrentYear.toggled.connect(self.auto_year_toggled)
        self.ui.btnClose.clicked.connect(self.close)

    def restore_settings(self):
        auto_year = self.settings.auto_current_year()
        self.ui.chkAutoCurrentYear.blockSignals(True)
        self.ui.chkAutoCurrentYear.setChecked(auto_year)
        self.ui.chkAutoCurrentYear.blockSignals(False)
        self.ui.spinYear.setValue(datetime.now().year if auto_year else self.settings.year())
        self.ui.spinArea.setValue(self.settings.area())
        self.ui.chkSkipDuplicates.setChecked(self.settings.skip_duplicates())
        self._select_combo_text(self.ui.cmbPoints, self.settings.point_layer_name() or self.DEFAULT_POINT_LAYER)
        self._select_combo_text(self.ui.cmbCircles, self.settings.polygon_layer_name() or self.DEFAULT_POLYGON_LAYER)
        mode = self.settings.coordinate_mode()
        index = self.ui.cmbCoordinateFormat.findData(mode)
        if index >= 0:
            self.ui.cmbCoordinateFormat.setCurrentIndex(index)
        self.ui.txtSourceCrs.setText(self.settings.source_crs() or "EPSG:4326")

    def save_settings(self):
        self.settings.save(
            self.ui.spinYear.value(),
            self.ui.spinArea.value(),
            self.ui.cmbPoints.currentText(),
            self.ui.cmbCircles.currentText(),
            self.ui.chkSkipDuplicates.isChecked(),
            self.ui.cmbCoordinateFormat.currentData() or "AUTO",
            self.ui.txtSourceCrs.text().strip() or "EPSG:4326",
            self.ui.chkAutoCurrentYear.isChecked(),
        )

    def refresh_layers(self):
        point_text = self.ui.cmbPoints.currentText()
        polygon_text = self.ui.cmbCircles.currentText()
        self.ui.cmbPoints.clear()
        self.ui.cmbCircles.clear()
        for layer in QgsProject.instance().mapLayers().values():
            if layer.type() != QgsMapLayerType.VectorLayer:
                continue
            geom = QgsWkbTypes.geometryType(layer.wkbType())
            if geom == QgsWkbTypes.PointGeometry:
                self.ui.cmbPoints.addItem(layer.name(), layer.id())
            elif geom == QgsWkbTypes.PolygonGeometry:
                self.ui.cmbCircles.addItem(layer.name(), layer.id())
        self._select_combo_text(self.ui.cmbPoints, point_text or self.DEFAULT_POINT_LAYER)
        self._select_combo_text(self.ui.cmbCircles, polygon_text or self.DEFAULT_POLYGON_LAYER)
        self.set_status("Список слоёв обновлён.")
        if hasattr(self.ui, "lblDashWells"):
            self.refresh_dashboard()

    def _select_combo_text(self, combo, text):
        index = combo.findText(text) if text else -1
        if index >= 0:
            combo.setCurrentIndex(index)

    def set_status(self, text):
        self.ui.lblStatus.setText(text)

    def append_log(self, text):
        self.ui.txtLog.appendPlainText(str(text))

    def _target_ids(self):
        point_id = self.ui.cmbPoints.currentData()
        polygon_id = self.ui.cmbCircles.currentData()
        if not point_id:
            raise Exception("Не выбран точечный слой.")
        if not polygon_id:
            raise Exception("Не выбран слой кругов.")
        return point_id, polygon_id

    def _coordinate_options(self):
        return (
            self.ui.cmbCoordinateFormat.currentData() or "AUTO",
            self.ui.txtSourceCrs.text().strip() or "EPSG:4326",
        )

    def _current_point_layer(self):
        layer_id = self.ui.cmbPoints.currentData()
        return QgsProject.instance().mapLayer(layer_id) if layer_id else None

    def _preview(self, records, source_title, allow_import=True):
        """Проверяет координаты и интеллектуально ищет дубли перед импортом."""
        checks = self.coordinate_checker.analyze(records)
        duplicate_checks = self.duplicate_checker.analyze(records, self._current_point_layer())
        dialog = PreviewDialog(
            records, checks, duplicate_checks, source_title,
            allow_import=allow_import, parent=self
        )
        accepted = dialog.exec_() == QtWidgets.QDialog.Accepted if allow_import else False
        return accepted, checks, duplicate_checks

    def check_clipboard_clicked(self):
        try:
            mode, source_crs = self._coordinate_options()
            records = self.clipboard_importer.parse(mode, source_crs)
            self._preview(records, "Буфер обмена", allow_import=False)
            self.append_log(f"Предпросмотр буфера: {len(records)} строк.")
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, "Проверка буфера", str(exc))

    def browse_excel_clicked(self):
        start_dir = self._preferred_input_folder()
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Выберите файл с координатами скважин", start_dir,
            "Файлы данных (*.xlsx *.csv *.txt);;Excel XLSX (*.xlsx);;CSV (*.csv);;Text (*.txt)"
        )
        if file_path:
            self._set_input_file(file_path)

    def import_clicked(self):
        try:
            mode, source_crs = self._coordinate_options()
            records = self.clipboard_importer.parse(mode, source_crs)
            accepted, checks, duplicate_checks = self._preview(records, "Буфер обмена", allow_import=True)
            if not accepted:
                self.set_status("Импорт отменён на этапе предпросмотра.")
                return
            self._execute_records(records, checks, duplicate_checks, "Буфер обмена")
        except Exception as exc:
            self._show_error(exc)

    def import_file_clicked(self):
        try:
            file_path = self.ui.txtExcelPath.text().strip()
            if not file_path:
                raise Exception("Не выбран файл Excel/CSV/TXT.")
            self.settings.set_last_folder(str(Path(file_path).parent))
            mode, source_crs = self._coordinate_options()
            records = self.file_importer.parse_file(file_path, mode, source_crs)
            source = Path(file_path).name
            accepted, checks, duplicate_checks = self._preview(records, source, allow_import=True)
            if not accepted:
                self.set_status("Импорт отменён на этапе предпросмотра.")
                return
            self._execute_records(records, checks, duplicate_checks, source)
        except Exception as exc:
            self._show_error(exc)

    def _execute_records(self, records, checks, duplicate_checks, source):
        point_id, polygon_id = self._target_ids()
        self.save_settings()
        suspicious = self.coordinate_checker.count_warnings(checks)
        intelligent_duplicates = self.duplicate_checker.count_flagged(duplicate_checks)

        row_severities = []
        coord_by_row = {item.row: item for item in checks}
        duplicate_by_row = {item.row: item for item in duplicate_checks}
        for row in range(1, len(records) + 1):
            coord = coord_by_row.get(row)
            duplicate = duplicate_by_row.get(row)
            row_severities.append(Severity.max(
                coord.severity if coord else Severity.INFO,
                duplicate.severity if duplicate and duplicate.messages else Severity.INFO,
            ))
        preview_counts = Severity.counts(row_severities)

        self.set_status("Выполняется импорт...")
        result = self.controller.execute_records(
            records, point_id, polygon_id,
            self.ui.spinYear.value(), self.ui.spinArea.value(),
            self.ui.chkSkipDuplicates.isChecked(),
            source=source,
            suspicious_count=suspicious,
            intelligent_duplicate_count=intelligent_duplicates,
            preview_severity_counts=preview_counts,
        )
        validation = result.validation or {}
        validation_counts = validation.get("severity_counts", {})
        message = (
            f"Импорт завершён.\n\n"
            f"Прочитано строк: {result.parsed_records}\n"
            f"Добавлено точек: {result.added_points}\n"
            f"Добавлено кругов: {result.added_circles}\n"
            f"Пропущено точных дублей: {result.skipped_duplicates}\n"
            f"Интеллектуально отмечено возможных дублей: {result.intelligent_duplicate_count}\n"
            f"Предупреждений координат: {result.suspicious_count}\n"
            f"Ошибок записи: {result.errors}\n\n"
            f"Проверка кругов: OK {validation.get('ok', 0)}/{validation.get('total', 0)}\n"
            f"Серьёзность проверки: критических {validation_counts.get(Severity.CRITICAL, 0)}, "
            f"ошибок {validation_counts.get(Severity.ERROR, 0)}, "
            f"предупреждений {validation_counts.get(Severity.WARNING, 0)}\n"
            f"Площадь: допуск ±{validation.get('area_tolerance_pct', 2.0)}%\n"
            f"Центр: допуск {validation.get('center_tolerance_m', 5.0)} м"
        )
        self.set_status("Импорт и автоматическая проверка завершены.")
        self.append_log(message)
        QtWidgets.QMessageBox.information(self, "Well Importer", message)
        self.refresh_dashboard()

    def show_history(self):
        HistoryDialog(self.controller.history.items(), self).exec_()

    def undo_last_import(self):
        entry = self.controller.history.last_active()
        if not entry:
            QtWidgets.QMessageBox.information(self, "Отмена импорта", "Нет импорта, который можно отменить.")
            return
        answer = QtWidgets.QMessageBox.question(
            self, "Отменить последний импорт",
            f"Удалить последнюю партию от {entry.get('timestamp', '')}?\n"
            f"Источник: {entry.get('source', '')}\n"
            "Будут удалены только объекты этой партии.",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No
        )
        if answer != QtWidgets.QMessageBox.Yes:
            return
        try:
            result = self.controller.undo_last_import()
            QtWidgets.QMessageBox.information(
                self, "Отмена импорта",
                f"Партия отменена.\nУдалено точек: {result['points']}\nУдалено кругов: {result['circles']}"
            )
            self.refresh_dashboard()
        except Exception as exc:
            self._show_error(exc)

    def validate_last_import(self):
        try:
            result = self.controller.validate_last_import()
            counts = result.get("severity_counts", {})
            lines = [
                f"Проверено кругов: {result.get('total', 0)}",
                f"Без замечаний: {result.get('ok', 0)}",
                f"С замечаниями: {result.get('failed', 0)}",
                f"Критических: {counts.get(Severity.CRITICAL, 0)}",
                f"Ошибок: {counts.get(Severity.ERROR, 0)}",
                f"Предупреждений: {counts.get(Severity.WARNING, 0)}",
            ]
            bad = [item for item in result.get("items", []) if not (item.get("area_ok") and item.get("center_ok"))]
            if bad:
                lines.append("\nПервые замечания:")
                for item in bad[:10]:
                    lines.append(
                        f"№{item.get('number')} [{Severity.label(item.get('severity'))}]: {item.get('message')}"
                    )
            QtWidgets.QMessageBox.information(self, "Проверка площадных кругов", "\n".join(lines))
        except Exception as exc:
            self._show_error(exc)

    def _default_output_dir(self):
        project_file = QgsProject.instance().fileName()
        if project_file:
            return str(Path(project_file).parent)
        return str(Path.home())

    def archive_old_imports(self):
        items = self.controller.history.items()
        available = [
            item for item in items
            if item.get("batch_id") and not item.get("undone") and not item.get("archived")
        ]
        if len(available) <= 1:
            QtWidgets.QMessageBox.information(
                self, "Архивирование",
                "Для архивирования пока нет старых активных партий. Последняя рабочая партия остаётся в проекте."
            )
            return

        dialog = ArchiveDialog(items, self)
        if dialog.exec_() != QtWidgets.QDialog.Accepted:
            return
        batch_ids = dialog.selected_batch_ids()
        if not batch_ids:
            QtWidgets.QMessageBox.warning(self, "Архивирование", "Не выбрана ни одна партия.")
            return

        point_id, polygon_id = self._target_ids()
        default_name = f"WellImporter_Archive_{datetime.now().strftime('%Y%m%d_%H%M')}.gpkg"
        file_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Сохранить архив импортов",
            str(Path(self._default_output_dir()) / default_name),
            "GeoPackage (*.gpkg)",
        )
        if not file_path:
            return

        answer = QtWidgets.QMessageBox.question(
            self, "Подтвердить архивирование",
            f"В архив будет перенесено партий: {len(batch_ids)}.\n"
            "После успешного создания GeoPackage их объекты будут удалены из текущих рабочих слоёв.\n\nПродолжить?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )
        if answer != QtWidgets.QMessageBox.Yes:
            return

        try:
            self.set_status("Архивирование старых импортов...")
            result = self.controller.archive_batches(point_id, polygon_id, batch_ids, file_path)
            message = (
                f"Архивирование завершено.\n\nПартий: {len(result['batch_ids'])}\n"
                f"Перенесено точек: {result['points']}\nПеренесено кругов: {result['circles']}\n"
                f"Архив: {result['archive_path']}"
            )
            self.append_log(message)
            self.set_status("Архивирование завершено.")
            QtWidgets.QMessageBox.information(self, "Архивирование", message)
            self.refresh_dashboard()
        except Exception as exc:
            self._show_error(exc)

    def export_for_field(self):
        """Запускает мастер анализа и подготовки выездного комплекта."""
        try:
            point_id, polygon_id = self._target_ids()
            point_layer = self.controller.layer_by_id(point_id)
            parcel_source = self.controller.detect_parcel_source(
                polygon_id, require_cadastral=True
            )
            parcel_layer = QgsProject.instance().mapLayer(parcel_source.get("layer_id"))
            self.set_status("Проверка готовности проекта к выезду...")
            preparation_report = self.controller.analyze_field_package(point_id, polygon_id)

            wizard = FieldExportWizard(
                preparation_report,
                selected_count=point_layer.selectedFeatureCount(),
                parent=self,
                iface=self.iface,
                point_layer=point_layer,
                parcel_layer=parcel_layer,
            )
            if wizard.exec_() != QtWidgets.QDialog.Accepted:
                self.set_status("Подготовка выездного комплекта отменена.")
                return
            options = wizard.options()
            self.set_status("Подготовка выбранной территории и кадастровых номеров...")
            scope_result = self.controller.prepare_field_scope(
                point_id, polygon_id, options["scope_mode"]
            )
            preparation_report["field_scope"] = scope_result.get("scope", {})
            preparation_report["cadastral"] = scope_result.get("cadastral", {})

            default_name = f"WellImporter_Field_{datetime.now().strftime('%Y%m%d_%H%M')}.zip"
            file_path, _ = QtWidgets.QFileDialog.getSaveFileName(
                self, "Сохранить выездной комплект",
                str(Path(self._default_output_dir()) / default_name),
                "ZIP архив выезда (*.zip)",
            )
            if not file_path:
                return

            self.set_status("Создание выездного комплекта...")
            result = self.controller.export_field_package(
                point_id, polygon_id, file_path,
                selected_only=bool(scope_result.get("scope", {}).get("selected_only")),
                store_styles=options["store_styles"],
                create_project=options["create_project"],
                relative_paths=options["relative_paths"],
                include_readme=options["include_readme"],
                preparation_report=preparation_report,
            )
            project_line = result["project_path"] or "не создавался"
            readme_line = result["info_path"] or "не создавался"
            message = (
                f"Выездной комплект создан.\n\n"
                f"Скважин: {result['points']}\n"
                f"Площадных кругов: {result['circles']}\n"
                f"Режим территории: {scope_result.get('scope', {}).get('mode', 'all')}\n"
                f"Кадастровых номеров подготовлено: {scope_result.get('cadastral', {}).get('cadastral_found', 0)}\n"
                f"Стилей сохранено внутри GeoPackage: {result.get('styles_stored', 0)}\n\n"
                f"ZIP-архив: {result['zip_path']}\n"
                f"GeoPackage внутри архива: {result['gpkg_path']}\n"
                f"Интерактивная веб-карта: {result.get('web_map_path', '—')}\n"
                f"QGIS-проект: {project_line}\n"
                f"Памятка: {readme_line}"
            )
            if result.get("style_errors"):
                message += "\n\nЗамечания по стилям:\n" + "\n".join(result["style_errors"][:5])
            self.append_log(message)
            self.set_status("Выездной комплект создан.")
            QtWidgets.QMessageBox.information(self, "Экспорт для выезда", message)
        except Exception as exc:
            self._show_error(exc)

    def export_management_web_map(self):
        """Экспортирует один автономный HTML-файл, который открывается без QGIS."""
        try:
            point_id, polygon_id = self._target_ids()
            default = str(
                Path(self._default_output_dir()) /
                f"WellImporter_Map_{datetime.now().strftime('%Y%m%d_%H%M')}.html"
            )
            path, _ = QtWidgets.QFileDialog.getSaveFileName(
                self, "Сохранить HTML-карту для руководства", default,
                "HTML (*.html)"
            )
            if not path:
                return
            self.set_status("Подготовка автономной HTML-карты...")
            result = self.controller.export_management_web_map(
                point_id, polygon_id, path
            )
            message = (
                f"HTML-карта создана.\n\n"
                f"Файл: {result.get('path', '')}\n"
                f"Скважин: {result.get('points', 0)}\n"
                f"Площадных кругов: {result.get('circles', 0)}\n\n"
                "В карте доступны поиск по номеру, фильтры по году и участку, "
                "всплывающие карточки и печать выбранной области. QGIS для просмотра не требуется."
            )
            self.append_log(message)
            self.set_status("HTML-карта готова.")
            QtWidgets.QMessageBox.information(self, "HTML-карта", message)
        except Exception as exc:
            self._show_error(exc)

    def import_field_results(self):
        """Сравнивает офисную/выездную версии и применяет только подтверждённые изменения."""
        try:
            point_id, polygon_id = self._target_ids()
            package_path, _ = QtWidgets.QFileDialog.getOpenFileName(
                self, "Выберите пакет после выезда", self._default_output_dir(),
                "Выездной пакет (*.zip *.gpkg);;ZIP (*.zip);;GeoPackage (*.gpkg)"
            )
            if not package_path:
                return
            self.set_status("Сравнение офисной и выездной версий...")
            comparison = self.controller.compare_field_return(
                point_id, polygon_id, package_path
            )
            if not comparison.get("changes"):
                QtWidgets.QMessageBox.information(
                    self, "Обратная синхронизация",
                    "В выездной версии нет изменений относительно исходного пакета."
                )
                self.set_status("Изменений после выезда нет.")
                return
            dialog = FieldSyncDialog(comparison, self)
            if dialog.exec_() != QtWidgets.QDialog.Accepted:
                self.set_status("Обратная синхронизация отменена.")
                return
            changes = dialog.selected_changes()
            if not changes:
                QtWidgets.QMessageBox.information(
                    self, "Обратная синхронизация", "Не выбрано ни одного изменения."
                )
                return
            result = self.controller.apply_field_return(
                point_id, polygon_id, package_path, changes
            )
            message = (
                f"Обратная синхронизация завершена.\n\n"
                f"Подтверждено и применено: {result.get('applied', 0)}\n"
                f"Добавлено: {result.get('added', 0)}\n"
                f"Изменено: {result.get('modified', 0)}\n"
                f"Удалено: {result.get('deleted', 0)}"
            )
            if result.get("left_uncommitted"):
                message += (
                    "\n\nЭти слои уже были в режиме редактирования; изменения оставлены "
                    "в текущей edit-сессии и не зафиксированы автоматически: "
                    + ", ".join(result["left_uncommitted"])
                )
            self.append_log(message)
            self.set_status("Обратная синхронизация завершена.")
            QtWidgets.QMessageBox.information(self, "Обратная синхронизация", message)
            self.refresh_dashboard()
        except Exception as exc:
            self._show_error(exc)

    def open_basemap_catalog(self):
        BasemapCatalogDialog(self.controller.basemaps, self).exec_()

    def check_field_preflight(self):
        try:
            point_id, polygon_id = self._target_ids()
            report = self.controller.analyze_field_package(point_id, polygon_id)
            preflight = report.get("preflight", {})
            internet = preflight.get("internet_layers", [])
            missing = preflight.get("missing_external_files", 0)
            unavailable = sum(1 for item in internet if not item.get("available"))
            QtWidgets.QMessageBox.information(
                self, "Проверка перед выездом",
                f"Интернет-слоёв проверено: {len(internet)}\n"
                f"Недоступных интернет-слоёв: {unavailable}\n"
                f"Отсутствующих внешних файлов: {missing}"
            )
        except Exception as exc:
            self._show_error(exc)

    def refresh_profiles(self, select_name=None):
        """
        Обновляет выпадающий список профилей.

        Последний пункт списка всегда служебный:
        «+ Добавить профиль…».
        """
        current = (
            str(select_name).strip()
            if select_name
            else self.ui.cmbProfile.currentText().strip()
        )
        if current == self.ADD_PROFILE_LABEL:
            current = getattr(
                self,
                "_last_profile_name",
                "Солевая съёмка 33 га",
            )

        names = self.profiles.names()

        self.ui.cmbProfile.blockSignals(True)
        self.ui.cmbProfile.clear()

        for name in names:
            self.ui.cmbProfile.addItem(name, name)

        if names:
            self.ui.cmbProfile.insertSeparator(self.ui.cmbProfile.count())

        self.ui.cmbProfile.addItem(
            self.ADD_PROFILE_LABEL,
            self.ADD_PROFILE_TOKEN,
        )

        target = current or "Солевая съёмка 33 га"
        index = self.ui.cmbProfile.findText(target)
        if index < 0 and names:
            index = 0

        if index >= 0:
            self.ui.cmbProfile.setCurrentIndex(index)
            if self.ui.cmbProfile.currentData() != self.ADD_PROFILE_TOKEN:
                self._last_profile_name = self.ui.cmbProfile.currentText()

        self.ui.cmbProfile.blockSignals(False)
        self._update_profile_buttons()

    def profile_combo_activated(self, index):
        """Обрабатывает выбор обычного профиля или команды добавления."""
        data = self.ui.cmbProfile.itemData(index)

        if data == self.ADD_PROFILE_TOKEN:
            self.create_profile()
            return

        self._last_profile_name = self.ui.cmbProfile.itemText(index)
        self._update_profile_buttons()

    def create_profile(self):
        """
        Создаёт новый профиль из текущих параметров главного окна.

        Пользователю нужно указать только название — остальные параметры
        берутся из текущего состояния Well Importer.
        """
        fallback = getattr(
            self,
            "_last_profile_name",
            "Солевая съёмка 33 га",
        )

        name, ok = QtWidgets.QInputDialog.getText(
            self,
            "Добавить профиль",
            "Название нового профиля:",
        )
        name = str(name or "").strip()

        if not ok or not name:
            self.refresh_profiles(fallback)
            return

        if name == self.ADD_PROFILE_LABEL:
            QtWidgets.QMessageBox.warning(
                self,
                "Добавить профиль",
                "Это название используется служебным пунктом списка. "
                "Введите другое название.",
            )
            self.refresh_profiles(fallback)
            return

        if self.profiles.exists(name):
            answer = QtWidgets.QMessageBox.question(
                self,
                "Профиль уже существует",
                f"Профиль «{name}» уже существует. Перезаписать его "
                "текущими настройками?",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No,
            )
            if answer != QtWidgets.QMessageBox.Yes:
                self.refresh_profiles(fallback)
                return

        self.profiles.save(name, self._current_profile_data())
        self._last_profile_name = name
        self.refresh_profiles(name)
        self.set_status(f"Создан профиль: {name}")

    def _update_profile_buttons(self):
        """Не даёт применить/удалить служебный пункт добавления."""
        is_profile = (
            self.ui.cmbProfile.currentData() != self.ADD_PROFILE_TOKEN
            and bool(self.ui.cmbProfile.currentText().strip())
        )
        self.ui.btnApplyProfile.setEnabled(is_profile)
        self.ui.btnSaveProfile.setEnabled(is_profile)
        self.ui.btnDeleteProfile.setEnabled(is_profile)


    def _current_profile_data(self):
        return {
            "area": self.ui.spinArea.value(),
            "coordinate_mode": self.ui.cmbCoordinateFormat.currentData() or "AUTO",
            "source_crs": self.ui.txtSourceCrs.text().strip() or "EPSG:4326",
            "skip_duplicates": self.ui.chkSkipDuplicates.isChecked(),
            "auto_current_year": self.ui.chkAutoCurrentYear.isChecked(),
            "year": self.ui.spinYear.value(),
            "point_layer_name": self.ui.cmbPoints.currentText(),
            "polygon_layer_name": self.ui.cmbCircles.currentText(),
            "required_point_fields": self.settings.required_point_fields(),
            "required_polygon_fields": self.settings.required_polygon_fields(),
        }

    def apply_profile(self):
        if self.ui.cmbProfile.currentData() == self.ADD_PROFILE_TOKEN:
            self.create_profile()
            return

        name = self.ui.cmbProfile.currentText().strip()
        profile = self.profiles.get(name)
        if not profile:
            return
        self.ui.spinArea.setValue(float(profile.get("area", 33.0)))
        mode_index = self.ui.cmbCoordinateFormat.findData(profile.get("coordinate_mode", "AUTO"))
        if mode_index >= 0:
            self.ui.cmbCoordinateFormat.setCurrentIndex(mode_index)
        self.ui.txtSourceCrs.setText(profile.get("source_crs", "EPSG:4326"))
        self.ui.chkSkipDuplicates.setChecked(bool(profile.get("skip_duplicates", True)))
        auto_year = bool(profile.get("auto_current_year", True))
        self.ui.chkAutoCurrentYear.setChecked(auto_year)
        self.ui.spinYear.setValue(datetime.now().year if auto_year else int(profile.get("year", self.settings.year())))
        self._select_combo_text(self.ui.cmbPoints, profile.get("point_layer_name", ""))
        self._select_combo_text(self.ui.cmbCircles, profile.get("polygon_layer_name", ""))
        if profile.get("required_point_fields") or profile.get("required_polygon_fields"):
            self.settings.set_required_fields(
                profile.get("required_point_fields", ["Номер скважины", "Год"]),
                profile.get("required_polygon_fields", ["Номер скважины"]),
            )
        self.save_settings()
        self.refresh_dashboard()
        self.set_status(f"Применён профиль: {name}")

    def save_profile(self):
        """Сохраняет текущие параметры в уже выбранный профиль."""
        if self.ui.cmbProfile.currentData() == self.ADD_PROFILE_TOKEN:
            self.create_profile()
            return

        name = self.ui.cmbProfile.currentText().strip()
        if not name:
            self.create_profile()
            return

        self.profiles.save(name, self._current_profile_data())
        self._last_profile_name = name
        self.refresh_profiles(name)
        self.set_status(f"Изменения профиля сохранены: {name}")


    def delete_profile(self):
        if self.ui.cmbProfile.currentData() == self.ADD_PROFILE_TOKEN:
            self.refresh_profiles(
                getattr(
                    self,
                    "_last_profile_name",
                    "Солевая съёмка 33 га",
                )
            )
            return

        name = self.ui.cmbProfile.currentText().strip()
        if not name:
            return

        answer = QtWidgets.QMessageBox.question(
            self,
            "Удалить профиль",
            f"Удалить профиль «{name}»?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )
        if answer != QtWidgets.QMessageBox.Yes:
            return

        try:
            self.profiles.delete(name)
            self._last_profile_name = "Солевая съёмка 33 га"
            self.refresh_profiles(self._last_profile_name)
            self.set_status(f"Профиль удалён: {name}")
        except Exception as exc:
            self._show_error(exc)


    def auto_year_toggled(self, checked):
        if checked:
            self.ui.spinYear.setValue(datetime.now().year)
        self.save_settings()

    def refresh_favorite_folders(self):
        folders = self.settings.favorite_folders()
        current = self.ui.cmbFavoriteFolder.currentText()
        self.ui.cmbFavoriteFolder.blockSignals(True)
        self.ui.cmbFavoriteFolder.clear()
        self.ui.cmbFavoriteFolder.addItem("— выберите папку —", "")
        for folder in folders:
            self.ui.cmbFavoriteFolder.addItem(folder, folder)
        idx = self.ui.cmbFavoriteFolder.findText(current)
        if idx >= 0:
            self.ui.cmbFavoriteFolder.setCurrentIndex(idx)
        self.ui.cmbFavoriteFolder.blockSignals(False)

    def add_favorite_folder(self):
        folder = QtWidgets.QFileDialog.getExistingDirectory(self, "Добавить избранную папку", self._preferred_input_folder())
        if not folder:
            return
        folders = self.settings.favorite_folders()
        if folder not in folders:
            folders.append(folder)
            self.settings.set_favorite_folders(folders)
        self.settings.set_last_folder(folder)
        self.refresh_favorite_folders()
        idx = self.ui.cmbFavoriteFolder.findText(folder)
        if idx >= 0:
            self.ui.cmbFavoriteFolder.setCurrentIndex(idx)

    def remove_favorite_folder(self):
        folder = self.ui.cmbFavoriteFolder.currentData()
        if not folder:
            return
        folders = [item for item in self.settings.favorite_folders() if item != folder]
        self.settings.set_favorite_folders(folders)
        self.refresh_favorite_folders()

    def favorite_folder_changed(self):
        folder = self.ui.cmbFavoriteFolder.currentData()
        if folder:
            self.settings.set_last_folder(folder)

    def _preferred_input_folder(self):
        favorite = self.ui.cmbFavoriteFolder.currentData() if hasattr(self.ui, "cmbFavoriteFolder") else ""
        folder = favorite or self.settings.last_folder() or self._default_output_dir()
        return folder if Path(folder).exists() else self._default_output_dir()

    def _set_input_file(self, file_path):
        path = Path(file_path)
        if path.suffix.lower() not in (".xlsx", ".csv", ".txt"):
            raise Exception("Поддерживается перетаскивание только .xlsx, .csv и .txt.")
        self.ui.txtExcelPath.setText(str(path))
        self.settings.set_last_folder(str(path.parent))
        self.set_status(f"Выбран файл: {path.name}")

    def dragEnterEvent(self, event):
        urls = event.mimeData().urls() if event.mimeData().hasUrls() else []
        if any(Path(url.toLocalFile()).suffix.lower() in (".xlsx", ".csv", ".txt") for url in urls):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            if Path(file_path).suffix.lower() in (".xlsx", ".csv", ".txt"):
                try:
                    self._set_input_file(file_path)
                    event.acceptProposedAction()
                except Exception as exc:
                    self._show_error(exc)
                return
        event.ignore()

    def refresh_dashboard(self):
        try:
            point_id, polygon_id = self._target_ids()
            status = self.controller.project_status(
                point_id, polygon_id, self.ui.spinArea.value(),
                self.settings.required_point_fields(), self.settings.required_polygon_fields(),
            )
            self.ui.lblDashWells.setText(f"Скважины\n{status['wells']}")
            self.ui.lblDashCircles.setText(f"Круги\n{status['circles']}")
            self.ui.lblDashErrors.setText(f"Ошибки\n{status['errors']}")
            self.ui.lblDashWarnings.setText(f"Предупреждения\n{status['warnings']}")
            self.ui.lblDashImports.setText(f"Импорты\n{status['imports']}")
            self.ui.lblDashImports.setToolTip(f"Последний импорт: {status.get('latest_import', '—')}")
        except Exception:
            for widget, title in [
                (self.ui.lblDashWells, "Скважины"), (self.ui.lblDashCircles, "Круги"),
                (self.ui.lblDashErrors, "Ошибки"), (self.ui.lblDashWarnings, "Предупреждения"),
                (self.ui.lblDashImports, "Импорты")]:
                widget.setText(f"{title}\n—")

    def open_control_center(self):
        ControlCenterDialog(self, self).exec_()
        self.refresh_dashboard()

    def quick_search_well(self):
        number, ok = QtWidgets.QInputDialog.getText(self, "Поиск скважины", "Введите номер скважины:")
        if not ok or not number.strip():
            return
        try:
            point_id, _ = self._target_ids()
            results = self.controller.find_wells(point_id, number, auto_zoom=True)
            if not results:
                QtWidgets.QMessageBox.information(self, "Поиск скважины", "Скважина не найдена.")
                return
            self.set_status(f"Найдено скважин: {len(results)}. Карта приближена к результату.")
        except Exception as exc:
            self._show_error(exc)

    def _settings_changed(self):
        try:
            self.save_settings()
        except Exception:
            pass

    def closeEvent(self, event):
        try:
            self.save_settings()
        except Exception:
            pass
        super().closeEvent(event)

    def _show_error(self, exc):
        self.set_status("Ошибка.")
        self.append_log(f"Ошибка: {exc}")
        QtWidgets.QMessageBox.critical(self, "Ошибка Well Importer", str(exc))
