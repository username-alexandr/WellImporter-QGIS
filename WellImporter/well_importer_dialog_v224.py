# -*- coding: utf-8 -*-

from datetime import datetime
from pathlib import Path

from qgis.PyQt import QtWidgets

from .controller_v224 import ImportControllerV224
from .field_export_wizard import FieldExportWizard
from .robust_file_importer import RobustExcelFileImporter
from .well_importer_dialog import WellImporterDialog


class WellImporterDialogV224(WellImporterDialog):
    """Главное окно 2.2.4 с групповыми участками и накопленными runtime-исправлениями."""

    def __init__(self, iface, parent=None):
        super().__init__(iface, parent)
        # Явно подключаем исправления 2.2.2/2.2.3 к реально используемому окну,
        # чтобы они не зависели от исторических классов-обёрток.
        self.controller = ImportControllerV224(iface)
        self.file_importer = RobustExcelFileImporter()
        self.refresh_dashboard()

    def _current_profile_data(self):
        data = super()._current_profile_data()
        data["parcel_group_path"] = self.settings.parcel_group_path()
        return data

    def apply_profile(self):
        if self.ui.cmbProfile.currentData() == self.ADD_PROFILE_TOKEN:
            self.create_profile()
            return
        name = self.ui.cmbProfile.currentText().strip()
        profile = self.profiles.get(name)
        super().apply_profile()
        if profile and profile.get("parcel_group_path"):
            self.settings.set_parcel_group_path(profile.get("parcel_group_path"))
            self.controller.set_parcel_group_path(profile.get("parcel_group_path"))

    def export_for_field(self):
        """Запускает мастер выезда с объединённым временным слоем участков выбранной группы."""
        selection_layer = None
        try:
            point_id, polygon_id = self._target_ids()
            point_layer = self.controller.layer_by_id(point_id)

            # До открытия мастера проверяем выбранную группу и создаём временное
            # представление всех её участков в CRS слоя скважин.
            self.controller.detect_parcel_source(polygon_id, require_cadastral=True)
            selection_layer = self.controller.create_field_parcel_selection_layer(
                point_id, polygon_id
            )

            self.set_status("Проверка готовности проекта к выезду...")
            preparation_report = self.controller.analyze_field_package(point_id, polygon_id)

            wizard = FieldExportWizard(
                preparation_report,
                selected_count=point_layer.selectedFeatureCount(),
                parent=self,
                iface=self.iface,
                point_layer=point_layer,
                parcel_layer=selection_layer,
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
            preparation_report["parcel_group_path"] = scope_result.get("parcel_group_path", "")

            default_name = f"WellImporter_Field_{datetime.now().strftime('%Y%m%d_%H%M')}.zip"
            file_path, _ = QtWidgets.QFileDialog.getSaveFileName(
                self,
                "Сохранить выездной комплект",
                str(Path(self._default_output_dir()) / default_name),
                "ZIP архив выезда (*.zip)",
            )
            if not file_path:
                return

            self.set_status("Создание выездного комплекта...")
            result = self.controller.export_field_package(
                point_id,
                polygon_id,
                file_path,
                selected_only=bool(scope_result.get("scope", {}).get("selected_only")),
                store_styles=options["store_styles"],
                create_project=options["create_project"],
                relative_paths=options["relative_paths"],
                include_readme=options["include_readme"],
                preparation_report=preparation_report,
            )
            project_line = result["project_path"] or "не создавался"
            readme_line = result["info_path"] or "не создавался"
            cadastral = scope_result.get("cadastral", {})
            message = (
                f"Выездной комплект создан.\n\n"
                f"Скважин: {result['points']}\n"
                f"Площадных кругов: {result['circles']}\n"
                f"Режим территории: {scope_result.get('scope', {}).get('mode', 'all')}\n"
                f"Группа участков: {scope_result.get('parcel_group_path', '—')}\n"
                f"Кадастровых номеров подготовлено: {cadastral.get('cadastral_found', 0)}\n"
                f"Конфликтов участков: {cadastral.get('conflict_count', 0)}\n"
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
        finally:
            try:
                self.controller.cleanup_field_parcel_selection_layer()
            except Exception:
                pass
