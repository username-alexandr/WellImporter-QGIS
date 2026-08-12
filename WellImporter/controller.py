# -*- coding: utf-8 -*-

from dataclasses import dataclass
import math
from datetime import datetime
from uuid import uuid4

from qgis.PyQt.QtCore import QVariant
from qgis.core import QgsProject, QgsField, QgsWkbTypes, QgsMapLayerType, QgsVectorLayerUtils

from .geometry import GeometryBuilder
from .archive_export import ArchiveExportManager
from .importer import ClipboardImporter, ExcelFileImporter
from .import_history import ImportHistory
from .logger import ImportLogger
from .progress import Progress
from .quality_checker import QualityChecker
from .validator import Validator
from .severity import Severity
from .attribute_checker import AttributeChecker
from .circle_repair import CircleRepairManager
from .point_repair import PointRepairManager
from .project_audit import ProjectAuditManager
from .pair_integrity import PairIntegrityChecker
from .pair_number_checker import PairNumberConsistencyChecker
from .well_number_validator import WellNumberFormatChecker
from .parcel_tools import ParcelManager
from .well_search import WellSearchManager
from .well_card import WellCardManager
from .well_number_field import (
    DISPLAY_NAME as WELL_NUMBER_DISPLAY_NAME,
    LEGACY_FIELD as LEGACY_WELL_NUMBER_FIELD,
    ensure_well_number_field,
    feature_well_number,
    set_feature_well_number,
    well_number_field_index,
    well_number_field_name,
)


@dataclass
class ImportResult:
    """Итог импорта и идентификатор партии."""
    parsed_records: int = 0
    added_points: int = 0
    added_circles: int = 0
    skipped_duplicates: int = 0
    errors: int = 0
    log_file: str = ""
    batch_id: str = ""
    validation: dict = None
    suspicious_count: int = 0
    intelligent_duplicate_count: int = 0
    preview_severity_counts: dict = None


class ImportController:
    """Центральный модуль импорта и управления партиями."""

    POINT_NUMBER_FIELD = WELL_NUMBER_DISPLAY_NAME
    POINT_YEAR_FIELD = "Год"
    BATCH_FIELD = "WI_BATCH"
    LEGACY_NUMBER_FIELD = LEGACY_WELL_NUMBER_FIELD
    AREA_HA_FIELD = "WI_AREA_HA"
    AREA_M2_FIELD = "WI_AREA_M2"
    RADIUS_M_FIELD = "WI_RADIUS_M"
    CENTER_M_FIELD = "WI_CENTER_M"

    def __init__(self, iface):
        self.iface = iface
        self.project = QgsProject.instance()
        self.importer = ClipboardImporter()
        self.file_importer = ExcelFileImporter()
        self.geometry = GeometryBuilder()
        self.logger = ImportLogger()
        self.history = ImportHistory()
        self.quality = QualityChecker()
        self.archive_export = ArchiveExportManager()
        self.attributes = AttributeChecker()
        self.circle_repair = CircleRepairManager()
        self.point_repair = PointRepairManager()
        self.project_audit = ProjectAuditManager()
        self.pair_integrity = PairIntegrityChecker()
        self.pair_number_consistency = PairNumberConsistencyChecker()
        self.number_format = WellNumberFormatChecker()
        self.parcels = ParcelManager()
        self.well_search = WellSearchManager()
        self.well_cards = WellCardManager()

    def layer_by_id(self, layer_id):
        layer = self.project.mapLayer(layer_id)
        if layer is None:
            raise Exception("Выбранный слой не найден в проекте.")
        return layer

    def execute_records(self, records, point_layer_id, polygon_layer_id, year, area,
                        skip_duplicates=True, source="Буфер обмена", suspicious_count=0,
                        intelligent_duplicate_count=0, preview_severity_counts=None):
        """Записывает предварительно проверенные записи в выбранные слои QGIS."""
        point_layer = self.layer_by_id(point_layer_id)
        polygon_layer = self.layer_by_id(polygon_layer_id)
        self._validate_layers(point_layer, polygon_layer)
        if not records:
            raise Exception("Нет записей для импорта.")

        batch_id = datetime.now().strftime("%Y%m%d%H%M%S") + "_" + uuid4().hex[:8]
        result = ImportResult(
            parsed_records=len(records), log_file=self.logger.file_path,
            batch_id=batch_id, suspicious_count=int(suspicious_count),
            intelligent_duplicate_count=int(intelligent_duplicate_count),
            preview_severity_counts=dict(preview_severity_counts or {}),
        )
        progress = Progress(self.iface, len(records), "Импорт скважин...")

        try:
            self._start_editing(point_layer)
            self._start_editing(polygon_layer)
            self._ensure_fields(point_layer, is_point=True)
            self._ensure_fields(polygon_layer, is_point=False)
            point_number_field = well_number_field_name(point_layer)
            if not point_number_field:
                raise Exception("Не удалось определить поле «Номер скважины» в слое точек.")
            validator = Validator(point_layer, point_number_field)

            for index, record in enumerate(records, start=1):
                progress.set_value(index)
                if progress.was_canceled():
                    self.logger.write("Импорт отменён пользователем.")
                    break
                if skip_duplicates and validator.exists(record.number):
                    result.skipped_duplicates += 1
                    continue
                try:
                    point_feature = self._make_point_feature(point_layer, record, year, batch_id)
                    point_number = feature_well_number(point_feature, point_layer, str(record.number))
                    circle_feature = self._make_circle_feature(
                        polygon_layer, record, area, year, batch_id, point_number
                    )
                    point_added = False
                    circle_added = False
                    try:
                        if not point_layer.addFeature(point_feature):
                            raise Exception("QGIS не добавил точку в слой.")
                        point_added = True
                        if not polygon_layer.addFeature(circle_feature):
                            raise Exception("QGIS не добавил круг в слой.")
                        circle_added = True
                        polygon_number_index = ensure_well_number_field(polygon_layer)
                        if not polygon_layer.changeAttributeValue(
                            circle_feature.id(), polygon_number_index, point_number
                        ):
                            raise Exception(
                                f"Не удалось записать номер скважины {point_number} в площадной круг."
                            )
                    except Exception:
                        if circle_added:
                            polygon_layer.deleteFeature(circle_feature.id())
                        if point_added:
                            point_layer.deleteFeature(point_feature.id())
                        raise
                    validator.remember(point_number)
                    result.added_points += 1
                    result.added_circles += 1
                except Exception as exc:
                    result.errors += 1
                    self.logger.write(f"Ошибка строки {index}, скважина №{record.number}: {exc}")

            self._commit_layer(point_layer)
            self._commit_layer(polygon_layer)
            self._refresh_layer(point_layer)
            self._refresh_layer(polygon_layer)
            self.iface.mapCanvas().refresh()

            validation = self.quality.validate_batch(
                point_layer, polygon_layer, batch_id, expected_area_ha=area
            )
            result.validation = validation

            history_entry = {
                "timestamp": datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
                "batch_id": batch_id,
                "source": source,
                "year": int(year),
                "area_ha": float(area),
                "point_layer_id": point_layer.id(),
                "point_layer_name": point_layer.name(),
                "polygon_layer_id": polygon_layer.id(),
                "polygon_layer_name": polygon_layer.name(),
                "parsed_records": result.parsed_records,
                "well_numbers": [str(record.number) for record in records[:500]],
                "added_points": result.added_points,
                "added_circles": result.added_circles,
                "skipped_duplicates": result.skipped_duplicates,
                "errors": result.errors,
                "suspicious_count": result.suspicious_count,
                "intelligent_duplicate_count": result.intelligent_duplicate_count,
                "preview_severity_counts": result.preview_severity_counts,
                "validation": validation,
                "undone": False,
                "archived": False,
            }
            self.history.add(history_entry)
            self.logger.write(
                f"Партия {batch_id}: точек {result.added_points}, кругов {result.added_circles}, "
                f"умных дублей {result.intelligent_duplicate_count}, "
                f"проверка OK {validation.get('ok', 0)}/{validation.get('total', 0)}"
            )

        except Exception:
            self._rollback_if_editable(point_layer)
            self._rollback_if_editable(polygon_layer)
            raise
        finally:
            progress.close()

        return result

    def undo_last_import(self):
        entry = self.history.last_active()
        if not entry:
            raise Exception("В истории нет импорта, который можно отменить.")
        point_layer = self._resolve_layer(entry.get("point_layer_id"), entry.get("point_layer_name"))
        polygon_layer = self._resolve_layer(entry.get("polygon_layer_id"), entry.get("polygon_layer_name"))
        if point_layer is None or polygon_layer is None:
            raise Exception("Не удалось найти слои последнего импорта в текущем проекте.")
        batch_id = entry["batch_id"]
        point_count = self._delete_batch(point_layer, batch_id)
        polygon_count = self._delete_batch(polygon_layer, batch_id)
        self.history.mark_undone(batch_id)
        self._refresh_layer(point_layer)
        self._refresh_layer(polygon_layer)
        self.iface.mapCanvas().refresh()
        return {"batch_id": batch_id, "points": point_count, "circles": polygon_count, "entry": entry}

    def validate_last_import(self):
        entry = self.history.last_active()
        if not entry:
            raise Exception("В истории нет активного импорта для проверки.")
        point_layer = self._resolve_layer(entry.get("point_layer_id"), entry.get("point_layer_name"))
        polygon_layer = self._resolve_layer(entry.get("polygon_layer_id"), entry.get("polygon_layer_name"))
        if point_layer is None or polygon_layer is None:
            raise Exception("Не удалось найти слои последнего импорта.")
        validation = self.quality.validate_batch(
            point_layer, polygon_layer, entry["batch_id"], entry.get("area_ha", 33.0)
        )
        self.history.update_validation(entry["batch_id"], validation)
        return validation

    def archive_batches(self, point_layer_id, polygon_layer_id, batch_ids, archive_path):
        point_layer = self.layer_by_id(point_layer_id)
        polygon_layer = self.layer_by_id(polygon_layer_id)
        self._validate_layers(point_layer, polygon_layer)
        result = self.archive_export.archive_batches(point_layer, polygon_layer, batch_ids, archive_path)
        self.history.mark_archived(batch_ids, result["archive_path"])
        self._refresh_layer(point_layer)
        self._refresh_layer(polygon_layer)
        self.iface.mapCanvas().refresh()
        self.logger.write(
            f"Архивировано партий: {len(result['batch_ids'])}; точек: {result['points']}; "
            f"кругов: {result['circles']}; файл: {result['archive_path']}"
        )
        return result

    def analyze_field_package(self, point_layer_id, polygon_layer_id):
        """Возвращает результаты мастера проверки проекта перед выездом."""
        point_layer = self.layer_by_id(point_layer_id)
        polygon_layer = self.layer_by_id(polygon_layer_id)
        self._validate_layers(point_layer, polygon_layer, require_editable=False)
        return self.archive_export.analyze_field_package(point_layer, polygon_layer)

    def export_field_package(self, point_layer_id, polygon_layer_id, output_path, selected_only=False,
                             store_styles=True, create_project=True, relative_paths=True,
                             include_readme=True, preparation_report=None):
        point_layer = self.layer_by_id(point_layer_id)
        polygon_layer = self.layer_by_id(polygon_layer_id)
        self._validate_layers(point_layer, polygon_layer, require_editable=False)
        result = self.archive_export.export_field_package(
            point_layer, polygon_layer, output_path,
            selected_only=selected_only,
            store_styles=store_styles,
            create_project=create_project,
            relative_paths=relative_paths,
            include_readme=include_readme,
            preparation_report=preparation_report,
        )
        self.logger.write(
            f"Выездной экспорт: точек {result['points']}, кругов {result['circles']}, "
            f"стилей в GPKG {result.get('styles_stored', 0)}, GeoPackage: {result['gpkg_path']}"
        )
        return result

    def check_required_attributes(self, point_layer_id, polygon_layer_id, point_fields=None, polygon_fields=None):
        point_layer = self.layer_by_id(point_layer_id)
        polygon_layer = self.layer_by_id(polygon_layer_id)
        self._validate_layers(point_layer, polygon_layer, require_editable=False)
        return self.attributes.check(point_layer, polygon_layer, point_fields, polygon_fields)

    def full_project_audit(self, point_layer_id, polygon_layer_id, expected_area_ha=33.0,
                           point_fields=None, polygon_fields=None):
        """
        Выполняет единый аудит выбранных рабочих слоёв проекта.

        Аудит объединяет существующие проверки обязательных атрибутов и
        геометрии/пар точка-круг в один отчёт. Метод только читает данные и
        ничего не исправляет автоматически.
        """
        point_layer = self.layer_by_id(point_layer_id)
        polygon_layer = self.layer_by_id(polygon_layer_id)
        self._validate_layers(point_layer, polygon_layer, require_editable=False)

        attributes = self.attributes.check(
            point_layer, polygon_layer, point_fields, polygon_fields
        )
        quality = self.quality.validate_all(
            point_layer, polygon_layer, expected_area_ha
        )
        pair_report = self.pair_integrity.check(point_layer, polygon_layer)
        number_consistency = self.pair_number_consistency.check(
            point_layer, polygon_layer
        )
        number_format = self.number_format.check(point_layer, polygon_layer)
        report = self.project_audit.build(
            point_layer, polygon_layer, attributes, quality,
            pair_report, number_consistency, number_format
        )
        self.logger.write(
            f"Полный аудит проекта: проблем {report.get('total', 0)}, "
            f"критических {report.get('severity_counts', {}).get(Severity.CRITICAL, 0)}, "
            f"ошибок {report.get('severity_counts', {}).get(Severity.ERROR, 0)}, "
            f"предупреждений {report.get('severity_counts', {}).get(Severity.WARNING, 0)}"
        )
        return report

    def validate_all_circles(self, point_layer_id, polygon_layer_id, expected_area_ha=33.0,
                             area_tolerance_pct=2.0, center_tolerance_m=5.0):
        point_layer = self.layer_by_id(point_layer_id)
        polygon_layer = self.layer_by_id(polygon_layer_id)
        self._validate_layers(point_layer, polygon_layer, require_editable=False)
        return self.quality.validate_all(
            point_layer, polygon_layer, expected_area_ha,
            area_tolerance_pct=area_tolerance_pct,
            center_tolerance_m=center_tolerance_m,
        )

    def repair_project(self, point_layer_id, polygon_layer_id, default_year, expected_area_ha=33.0,
                     point_fields=None, polygon_fields=None, plan=None):
        """Выполняет выбранный мастером план исправлений и повторный полный аудит."""
        plan = dict(plan or {})
        if not any((
            plan.get("repair_points"),
            plan.get("create_missing_circles"),
            plan.get("repair_circles"),
            plan.get("sync_circle_attributes"),
        )):
            raise Exception("Не выбрана ни одна операция исправления.")

        before = self.full_project_audit(
            point_layer_id, polygon_layer_id, expected_area_ha,
            point_fields, polygon_fields,
        )
        operations = {}

        # Сначала восстанавливаем точки: последующее исправление кругов
        # уже использует дополненные пары точка/круг.
        if plan.get("repair_points"):
            operations["points"] = self.repair_points(
                point_layer_id, polygon_layer_id, default_year
            )

        if plan.get("create_missing_circles"):
            operations["missing_circles"] = self.create_missing_circles(
                point_layer_id, polygon_layer_id, expected_area_ha
            )

        if plan.get("repair_circles"):
            operations["circles"] = self.repair_circles(
                point_layer_id, polygon_layer_id, expected_area_ha,
                repair_area=bool(plan.get("repair_area", True)),
                repair_center=bool(plan.get("repair_center", True)),
                create_missing=False,
            )

        if plan.get("sync_circle_attributes"):
            operations["circle_attributes"] = self.sync_circle_attributes(
                point_layer_id, polygon_layer_id, expected_area_ha
            )

        after = self.full_project_audit(
            point_layer_id, polygon_layer_id, expected_area_ha,
            point_fields, polygon_fields,
        )
        self.logger.write(
            f"Мастер исправления: проблем до {before.get('total', 0)}, "
            f"после {after.get('total', 0)}"
        )
        return {
            "before": before,
            "after": after,
            "operations": operations,
            "fixed": max(0, int(before.get("total", 0)) - int(after.get("total", 0))),
        }

    def create_missing_circles(self, point_layer_id, polygon_layer_id, expected_area_ha=33.0):
        """Создаёт круги только для тех существующих точек, у которых их ещё нет."""
        point_layer = self.layer_by_id(point_layer_id)
        polygon_layer = self.layer_by_id(polygon_layer_id)
        self._validate_layers(point_layer, polygon_layer)
        result = self.circle_repair.create_missing_circles(
            point_layer, polygon_layer, expected_area_ha
        )
        self._refresh_layer(polygon_layer)
        self.iface.mapCanvas().refresh()
        self.logger.write(
            f"Создание отсутствующих кругов: создано {result.get('created', 0)}"
        )
        return result

    def repair_circles(self, point_layer_id, polygon_layer_id, expected_area_ha=33.0,
                       repair_area=True, repair_center=True,
                       area_tolerance_pct=2.0, center_tolerance_m=5.0,
                       create_missing=True):
        """
        Исправляет площадные круги и создаёт отсутствующие круги
        для существующих точек с номером скважины.
        """
        point_layer = self.layer_by_id(point_layer_id)
        polygon_layer = self.layer_by_id(polygon_layer_id)
        self._validate_layers(point_layer, polygon_layer)

        created = {"created": 0}
        if create_missing:
            created = self.circle_repair.create_missing_circles(
                point_layer,
                polygon_layer,
                expected_area_ha,
            )

        result = self.circle_repair.repair(
            point_layer, polygon_layer, expected_area_ha,
            area_tolerance_pct=area_tolerance_pct,
            center_tolerance_m=center_tolerance_m,
            repair_area=repair_area, repair_center=repair_center,
        )
        result["created"] = created.get("created", 0)

        self._refresh_layer(polygon_layer)
        self.iface.mapCanvas().refresh()
        self.logger.write(
            f"Автоисправление кругов: создано {result.get('created', 0)}, "
            f"перестроено {result.get('repaired', 0)}"
        )
        return result

    def repair_points(self, point_layer_id, polygon_layer_id, default_year):
        """
        Исправляет точки бурения по данным связанных площадных кругов
        и текущему году из главного окна.
        """
        point_layer = self.layer_by_id(point_layer_id)
        polygon_layer = self.layer_by_id(polygon_layer_id)
        self._validate_layers(
            point_layer,
            polygon_layer,
            require_editable=False,
        )

        result = self.point_repair.repair(
            point_layer,
            polygon_layer,
            default_year,
        )
        self._refresh_layer(point_layer)
        self.iface.mapCanvas().refresh()
        self.logger.write(
            f"Автоисправление точек: изменений "
            f"{result.get('total_changes', 0)}"
        )
        return result

    def sync_circle_attributes(self, point_layer_id, polygon_layer_id, expected_area_ha=33.0):
        """Синхронизирует площадь/радиус/центр в атрибутивной таблице кругов."""
        point_layer = self.layer_by_id(point_layer_id)
        polygon_layer = self.layer_by_id(polygon_layer_id)
        self._validate_layers(point_layer, polygon_layer)
        result = self.circle_repair.sync_attributes(
            point_layer,
            polygon_layer,
            expected_area_ha=expected_area_ha,
        )
        self._refresh_layer(polygon_layer)
        self.iface.mapCanvas().refresh()
        self.logger.write(
            f"Синхронизация атрибутов кругов: объектов {result.get('features_updated', 0)}, "
            f"значений {result.get('values_updated', 0)}"
        )
        return result

    def assign_parcels(self, point_layer_id, parcel_layer_id, cadastral_field,
                       parcel_label_field=None, selected_only=False):
        point_layer = self.layer_by_id(point_layer_id)
        parcel_layer = self.layer_by_id(parcel_layer_id)
        result = self.parcels.assign(
            point_layer, parcel_layer, cadastral_field,
            parcel_label_field=parcel_label_field,
            selected_only=selected_only,
        )
        self._refresh_layer(point_layer)
        self.iface.mapCanvas().refresh()
        self.logger.write(
            f"Определение земельных участков: найдено {result.get('found', 0)}, "
            f"не найдено {result.get('not_found', 0)}"
        )
        return result

    def find_wells(self, point_layer_id, query, auto_zoom=True):
        point_layer = self.layer_by_id(point_layer_id)
        results = self.well_search.find(point_layer, query)
        if auto_zoom and results:
            self.well_search.zoom(self.iface, point_layer, [feature.id() for feature in results])
        return results

    def export_well_card(self, point_layer_id, polygon_layer_id, feature_id, path,
                         area_ha=33.0, image=False):
        point_layer = self.layer_by_id(point_layer_id)
        polygon_layer = self.layer_by_id(polygon_layer_id)
        feature = point_layer.getFeature(int(feature_id))
        if not feature.isValid():
            raise Exception("Выбранная скважина не найдена.")
        if image:
            return self.well_cards.export_map_png(point_layer, polygon_layer, feature, path, area_ha)
        return self.well_cards.export_pdf(point_layer, polygon_layer, feature, path, area_ha)

    def project_status(self, point_layer_id, polygon_layer_id, expected_area_ha=33.0,
                       point_fields=None, polygon_fields=None):
        """Возвращает состояние панели на основе того же единого аудита проекта."""
        point_layer = self.layer_by_id(point_layer_id)
        polygon_layer = self.layer_by_id(polygon_layer_id)
        audit = self.full_project_audit(
            point_layer_id, polygon_layer_id, expected_area_ha,
            point_fields, polygon_fields,
        )
        counts = audit.get("severity_counts", {})
        critical = counts.get(Severity.CRITICAL, 0)
        errors = counts.get(Severity.ERROR, 0) + critical
        warnings = counts.get(Severity.WARNING, 0)
        history_items = self.history.items()
        return {
            "wells": point_layer.featureCount(),
            "circles": polygon_layer.featureCount(),
            "errors": errors,
            "warnings": warnings,
            "critical": critical,
            "imports": len(history_items),
            "latest_import": history_items[0].get("timestamp", "") if history_items else "—",
            "attributes": audit.get("attributes", {}),
            "quality": audit.get("quality", {}),
            "audit": audit,
        }

    def _resolve_layer(self, layer_id, layer_name):
        layer = self.project.mapLayer(layer_id) if layer_id else None
        if layer is not None:
            return layer
        layers = self.project.mapLayersByName(layer_name or "")
        return layers[0] if layers else None

    def _delete_batch(self, layer, batch_id):
        if layer.fields().indexFromName(self.BATCH_FIELD) < 0:
            raise Exception(f"В слое {layer.name()} нет служебного поля {self.BATCH_FIELD}.")
        self._start_editing(layer)
        feature_ids = [feature.id() for feature in layer.getFeatures() if str(feature[self.BATCH_FIELD]) == str(batch_id)]
        for feature_id in feature_ids:
            if not layer.deleteFeature(feature_id):
                raise Exception(f"Не удалось удалить объект {feature_id} из слоя {layer.name()}.")
        self._commit_layer(layer)
        return len(feature_ids)

    def _start_editing(self, layer):
        if not layer.isEditable() and not layer.startEditing():
            raise Exception(f"Не удалось включить редактирование слоя: {layer.name()}")

    def _commit_layer(self, layer):
        if layer.isEditable() and not layer.commitChanges():
            errors = "\n".join(layer.commitErrors())
            raise Exception(f"Не удалось сохранить изменения слоя: {layer.name()}\n{errors}")

    def _rollback_if_editable(self, layer):
        if layer is not None and layer.isEditable():
            layer.rollBack()

    def _refresh_layer(self, layer):
        layer.updateExtents()
        layer.triggerRepaint()

    def _validate_layers(self, point_layer, polygon_layer, require_editable=True):
        if point_layer.type() != QgsMapLayerType.VectorLayer or QgsWkbTypes.geometryType(point_layer.wkbType()) != QgsWkbTypes.PointGeometry:
            raise Exception("Слой скважин должен быть точечным векторным слоем.")
        if polygon_layer.type() != QgsMapLayerType.VectorLayer or QgsWkbTypes.geometryType(polygon_layer.wkbType()) != QgsWkbTypes.PolygonGeometry:
            raise Exception("Слой кругов должен быть полигональным векторным слоем.")
        if require_editable and (point_layer.readOnly() or polygon_layer.readOnly()):
            raise Exception("Один из выбранных слоёв доступен только для чтения.")

    def _normalized_field_text(self, value):
        """Нормализует имя/псевдоним поля для безопасного сопоставления."""
        return (
            str(value or "")
            .strip()
            .lower()
            .replace("ё", "е")
            .replace("№", "номер")
        )

    def _clear_irrigation_system(self, feature):
        """
        Не позволяет значению по умолчанию слоя автоматически выбирать
        оросительную систему для новой точки бурения.
        """
        accepted = {
            "оросительная система",
            "оросит. система",
            "оросит система",
            "орос. система",
            "irrigation system",
        }

        for index, field in enumerate(feature.fields()):
            candidates = {
                self._normalized_field_text(field.name()),
                self._normalized_field_text(field.alias()),
            }
            if candidates & accepted:
                # Явно записываем NULL, чтобы значение по умолчанию,
                # подставленное QgsVectorLayerUtils.createFeature(), не осталось.
                feature[index] = None

    def _set_circle_well_number(self, layer, feature, number):
        """Записывает номер пробуренной скважины в площадной круг."""
        return set_feature_well_number(feature, layer, number)


    def _migrate_legacy_number_field(self, layer):
        """
        Выполняет скрытую миграцию старого WI_NUM в «Номер скважины».

        Значения WI_NUM копируются только в пустые значения канонического поля.
        После этого плагин пытается удалить устаревшее поле. Если провайдер
        не разрешает удаление столбцов, WI_NUM остаётся физически в слое, но
        больше нигде в рабочей логике плагина не используется.
        """
        legacy_index = layer.fields().indexFromName(self.LEGACY_NUMBER_FIELD)
        canonical_index = well_number_field_index(layer)
        if legacy_index < 0 or canonical_index < 0:
            return {"copied": 0, "conflicts": 0, "legacy_removed": legacy_index < 0}

        copied = 0
        conflicts = 0
        for feature in layer.getFeatures():
            legacy_value = str(feature[legacy_index] or "").strip()
            canonical_value = str(feature[canonical_index] or "").strip()
            if not legacy_value:
                continue
            if not canonical_value:
                if layer.changeAttributeValue(feature.id(), canonical_index, legacy_value):
                    copied += 1
            elif canonical_value != legacy_value:
                conflicts += 1

        # Удаление — только после копирования. Не блокируем работу, если
        # конкретный провайдер не умеет удалять поля.
        legacy_removed = False
        legacy_index = layer.fields().indexFromName(self.LEGACY_NUMBER_FIELD)
        if legacy_index >= 0:
            try:
                legacy_removed = bool(layer.deleteAttribute(legacy_index))
                if legacy_removed:
                    layer.updateFields()
            except Exception:
                legacy_removed = False
        else:
            legacy_removed = True

        if conflicts:
            self.logger.write(
                f"Миграция WI_NUM в «{self.POINT_NUMBER_FIELD}» для слоя «{layer.name()}»: "
                f"обнаружено конфликтов {conflicts}; сохранены значения канонического поля."
            )
        return {"copied": copied, "conflicts": conflicts, "legacy_removed": legacy_removed}

    def _ensure_fields(self, layer, is_point):
        ensure_well_number_field(layer)
        existing = layer.fields().names()
        fields = []
        if is_point and self.POINT_YEAR_FIELD not in existing:
            fields.append(QgsField(self.POINT_YEAR_FIELD, QVariant.String, len=16))
        if self.BATCH_FIELD not in existing:
            fields.append(QgsField(self.BATCH_FIELD, QVariant.String, len=32))
        if not is_point:
            if self.AREA_HA_FIELD not in existing:
                fields.append(QgsField(self.AREA_HA_FIELD, QVariant.Double, len=20, prec=6))
            if self.AREA_M2_FIELD not in existing:
                fields.append(QgsField(self.AREA_M2_FIELD, QVariant.Double, len=20, prec=3))
            if self.RADIUS_M_FIELD not in existing:
                fields.append(QgsField(self.RADIUS_M_FIELD, QVariant.Double, len=20, prec=3))
            if self.CENTER_M_FIELD not in existing:
                fields.append(QgsField(self.CENTER_M_FIELD, QVariant.Double, len=20, prec=3))
        for field in fields:
            if not layer.addAttribute(field):
                raise Exception(f"Не удалось создать поле {field.name()} в слое {layer.name()}.")
        if fields:
            layer.updateFields()

        # Скрытая совместимость со слоями старых версий: если WI_NUM ещё
        # существует, его значение переносится в «Номер скважины» автоматически.
        return self._migrate_legacy_number_field(layer)

    def _make_point_feature(self, layer, record, year, batch_id):
        geometry = self.geometry.transform_geometry_to_layer(self.geometry.create_point(record.x, record.y), layer)
        feature = QgsVectorLayerUtils.createFeature(layer, geometry)
        set_feature_well_number(feature, layer, record.number)
        feature[self.POINT_YEAR_FIELD] = str(year)
        feature[self.BATCH_FIELD] = batch_id
        # Не выбираем оросительную систему автоматически.
        self._clear_irrigation_system(feature)

        return feature

    def _make_circle_feature(self, layer, record, area, year, batch_id, point_number):
        geometry = self.geometry.create_circle_for_layer(record.x, record.y, area, layer)
        feature = QgsVectorLayerUtils.createFeature(layer, geometry)
        feature[self.BATCH_FIELD] = batch_id
        # Номер записывается напрямую в единое поле «Номер скважины».
        self._set_circle_well_number(layer, feature, point_number)

        # Атрибуты геометрии записываются сразу при импорте, поэтому
        # атрибутивная таблица не отстаёт от фактического круга.
        area_ha = float(area)
        area_m2 = area_ha * 10000.0
        radius_m = math.sqrt(area_m2 / math.pi)

        if self.AREA_HA_FIELD in feature.fields().names():
            feature[self.AREA_HA_FIELD] = area_ha
        if self.AREA_M2_FIELD in feature.fields().names():
            feature[self.AREA_M2_FIELD] = area_m2
        if self.RADIUS_M_FIELD in feature.fields().names():
            feature[self.RADIUS_M_FIELD] = radius_m
        if self.CENTER_M_FIELD in feature.fields().names():
            feature[self.CENTER_M_FIELD] = 0.0

        # Поддержка уже существующих пользовательских полей.
        aliases_ha = {
            "площадь", "площадь га", "площадь, га", "площадь_га",
            "площадь (га)", "area_ha", "area ha", "s_ha",
        }
        aliases_m2 = {
            "площадь м2", "площадь, м2", "площадь_м2",
            "площадь м²", "площадь, м²", "площадь (м²)",
            "area_m2", "area m2", "s_m2",
        }
        aliases_radius = {
            "радиус", "радиус м", "радиус, м", "радиус_м",
            "radius", "radius_m",
        }

        for index, field in enumerate(feature.fields()):
            names = [
                str(field.name() or "").strip().lower().replace("²", "2"),
                str(field.alias() or "").strip().lower().replace("²", "2"),
            ]
            normalized = next((value for value in names if value), "")
            if any(value in aliases_ha for value in names):
                feature[index] = area_ha
            elif any(value in aliases_m2 for value in names):
                feature[index] = area_m2
            elif any(value in aliases_radius for value in names):
                feature[index] = radius_m

        return feature
