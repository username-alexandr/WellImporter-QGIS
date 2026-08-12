# -*- coding: utf-8 -*-

import math

from qgis.PyQt.QtCore import QVariant
from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsField,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsVectorLayerUtils,
)

from .geometry import GeometryBuilder
from .quality_checker import QualityChecker
from .well_number_field import (
    ensure_well_number_field,
    set_feature_well_number,
    well_number_field_name,
)


class CircleRepairManager:
    """
    Автоматически перестраивает круги и синхронизирует их атрибуты.

    Исправление геометрии и строки атрибутивной таблицы выполняются одной
    операцией. После перестроения круга обновляются площадь, радиус и
    смещение центра.
    """

    WGS84 = QgsCoordinateReferenceSystem("EPSG:4326")
    NUMBER_FIELDS = ("Номер скважины",)

    AREA_HA_FIELD = "WI_AREA_HA"
    AREA_M2_FIELD = "WI_AREA_M2"
    RADIUS_M_FIELD = "WI_RADIUS_M"
    CENTER_M_FIELD = "WI_CENTER_M"

    HECTARE_FIELD_NAMES = {
        "wi_area_ha",
        "площадь",
        "площадь га",
        "площадь, га",
        "площадь_га",
        "площадь (га)",
        "area_ha",
        "area ha",
        "s_ha",
    }

    M2_FIELD_NAMES = {
        "wi_area_m2",
        "площадь м2",
        "площадь, м2",
        "площадь_м2",
        "площадь м²",
        "площадь, м²",
        "площадь (м²)",
        "area_m2",
        "area m2",
        "s_m2",
    }

    RADIUS_FIELD_NAMES = {
        "wi_radius_m",
        "радиус",
        "радиус м",
        "радиус, м",
        "радиус_м",
        "radius",
        "radius_m",
    }

    CENTER_FIELD_NAMES = {
        "wi_center_m",
        "смещение центра",
        "смещение центра м",
        "смещение центра, м",
        "center_offset",
        "center_offset_m",
    }

    def __init__(self):
        self.project = QgsProject.instance()
        self.geometry = GeometryBuilder()
        self.quality = QualityChecker()

    def create_missing_circles(
        self,
        point_layer,
        polygon_layer,
        expected_area_ha=33.0,
    ):
        """Создаёт отсутствующие круги для точек, у которых есть номер."""
        point_field = well_number_field_name(point_layer)
        if not point_field:
            raise Exception(
                "В слое точек отсутствует поле «Номер скважины»."
            )

        if not polygon_layer.isEditable() and not polygon_layer.startEditing():
            raise Exception(
                f"Не удалось включить редактирование слоя "
                f"«{polygon_layer.name()}»."
            )

        created = 0

        try:
            polygon_number_index = ensure_well_number_field(polygon_layer)
            polygon_number_field = polygon_layer.fields()[
                polygon_number_index
            ].name()

            self._ensure_measurement_fields(polygon_layer)

            existing_numbers = {
                self._key(feature[polygon_number_field])
                for feature in polygon_layer.getFeatures()
                if str(feature[polygon_number_field] or "").strip()
            }

            point_to_wgs = QgsCoordinateTransform(
                point_layer.crs(),
                self.WGS84,
                self.project,
            )

            point_batch_index = point_layer.fields().indexFromName("WI_BATCH")
            polygon_batch_index = polygon_layer.fields().indexFromName(
                "WI_BATCH"
            )

            for point_feature in point_layer.getFeatures():
                number = str(point_feature[point_field] or "").strip()
                if not number:
                    continue

                key = self._key(number)
                if key in existing_numbers:
                    continue

                if (
                    not point_feature.hasGeometry()
                    or point_feature.geometry().isEmpty()
                ):
                    continue

                point = point_feature.geometry().asPoint()
                point_wgs = point_to_wgs.transform(QgsPointXY(point))
                new_geometry = self.geometry.create_circle_for_layer(
                    point_wgs.x(),
                    point_wgs.y(),
                    float(expected_area_ha),
                    polygon_layer,
                )

                feature = QgsVectorLayerUtils.createFeature(
                    polygon_layer,
                    QgsGeometry(new_geometry),
                )
                set_feature_well_number(
                    feature,
                    polygon_layer,
                    number,
                )

                if (
                    point_batch_index >= 0
                    and polygon_batch_index >= 0
                ):
                    batch_value = point_feature[point_batch_index]
                    if batch_value is not None:
                        feature.setAttribute(
                            polygon_batch_index,
                            batch_value,
                        )

                if not polygon_layer.addFeature(feature):
                    raise Exception(
                        f"Не удалось создать площадной круг "
                        f"для скважины №{number}."
                    )

                self._write_measurement_attributes(
                    polygon_layer,
                    feature.id(),
                    float(expected_area_ha),
                    center_offset_m=0.0,
                )

                created += 1
                existing_numbers.add(key)

            if not polygon_layer.commitChanges():
                errors = "\n".join(polygon_layer.commitErrors())
                polygon_layer.rollBack()
                raise Exception(
                    "Не удалось сохранить созданные площадные круги.\n"
                    + errors
                )

        except Exception:
            if polygon_layer.isEditable():
                polygon_layer.rollBack()
            raise

        polygon_layer.updateFields()
        polygon_layer.updateExtents()
        polygon_layer.triggerRepaint()

        return {"created": created}

    def repair(
        self,
        point_layer,
        polygon_layer,
        expected_area_ha=33.0,
        area_tolerance_pct=2.0,
        center_tolerance_m=5.0,
        repair_area=True,
        repair_center=True,
    ):
        report = self.quality.validate_all(
            point_layer,
            polygon_layer,
            expected_area_ha,
            area_tolerance_pct=area_tolerance_pct,
            center_tolerance_m=center_tolerance_m,
        )

        point_field = self._number_field(point_layer)
        polygon_field = self._number_field(polygon_layer)

        if not point_field or not polygon_field:
            raise Exception(
                "Для автоматического исправления нужно поле «Номер скважины» в обоих слоях."
            )

        point_by_number = {
            str(feature[point_field]).strip(): feature
            for feature in point_layer.getFeatures()
        }
        polygon_by_number = {
            str(feature[polygon_field]).strip(): feature
            for feature in polygon_layer.getFeatures()
        }

        point_to_wgs = QgsCoordinateTransform(
            point_layer.crs(),
            self.WGS84,
            self.project,
        )

        targets = []
        for item in report.get("items", []):
            number = str(item.get("number", "")).strip()
            should_repair = (
                (repair_area and not item.get("area_ok", False))
                or
                (repair_center and not item.get("center_ok", False))
            )
            if (
                should_repair
                and number in point_by_number
                and number in polygon_by_number
            ):
                targets.append(number)

        if not targets:
            return {
                "repaired": 0,
                "attributes_updated": 0,
                "requested": 0,
                "validation_before": report,
                "validation_after": report,
            }

        if not polygon_layer.isEditable() and not polygon_layer.startEditing():
            raise Exception(
                f"Не удалось включить редактирование слоя "
                f"«{polygon_layer.name()}»."
            )

        repaired = 0
        attributes_updated = 0

        try:
            self._ensure_measurement_fields(polygon_layer)

            for number in targets:
                point_feature = point_by_number[number]
                polygon_feature = polygon_by_number[number]

                point = point_feature.geometry().asPoint()
                point_wgs = point_to_wgs.transform(QgsPointXY(point))

                new_geometry = self.geometry.create_circle_for_layer(
                    point_wgs.x(),
                    point_wgs.y(),
                    float(expected_area_ha),
                    polygon_layer,
                )

                if not polygon_layer.changeGeometry(
                    polygon_feature.id(),
                    QgsGeometry(new_geometry),
                ):
                    raise Exception(
                        f"Не удалось перестроить круг скважины №{number}."
                    )

                # После изменения геометрии обязательно синхронизируем строку
                # атрибутивной таблицы.
                changed = self._write_measurement_attributes(
                    polygon_layer,
                    polygon_feature.id(),
                    float(expected_area_ha),
                    center_offset_m=0.0,
                )
                attributes_updated += changed
                repaired += 1

            if not polygon_layer.commitChanges():
                errors = "\n".join(polygon_layer.commitErrors())
                polygon_layer.rollBack()
                raise Exception(
                    "Не удалось сохранить исправленные круги и их атрибуты.\n"
                    + errors
                )

        except Exception:
            if polygon_layer.isEditable():
                polygon_layer.rollBack()
            raise

        polygon_layer.updateFields()
        polygon_layer.updateExtents()
        polygon_layer.triggerRepaint()

        # Повторная проверка выполняется уже по сохранённому состоянию слоя.
        after = self.quality.validate_all(
            point_layer,
            polygon_layer,
            expected_area_ha,
            area_tolerance_pct=area_tolerance_pct,
            center_tolerance_m=center_tolerance_m,
        )

        # Записываем фактическое смещение центра после проверки. Обычно после
        # перестроения оно близко к нулю, но в таблице сохраняется измеренное
        # значение.
        offsets_by_number = {
            str(item.get("number", "")).strip(): float(
                item.get("center_distance_m", 0.0) or 0.0
            )
            for item in after.get("items", [])
        }

        if polygon_layer.startEditing():
            try:
                for number in targets:
                    feature = polygon_by_number[number]
                    offset = offsets_by_number.get(number, 0.0)
                    attributes_updated += self._write_center_offset(
                        polygon_layer,
                        feature.id(),
                        offset,
                    )

                if not polygon_layer.commitChanges():
                    errors = "\n".join(polygon_layer.commitErrors())
                    polygon_layer.rollBack()
                    raise Exception(
                        "Не удалось сохранить рассчитанное смещение центра.\n"
                        + errors
                    )
            except Exception:
                if polygon_layer.isEditable():
                    polygon_layer.rollBack()
                raise

        polygon_layer.updateFields()
        polygon_layer.updateExtents()
        polygon_layer.triggerRepaint()

        # Ещё раз читаем состояние, чтобы Центр управления и открытая таблица
        # получили уже окончательные значения.
        final_report = self.quality.validate_all(
            point_layer,
            polygon_layer,
            expected_area_ha,
            area_tolerance_pct=area_tolerance_pct,
            center_tolerance_m=center_tolerance_m,
        )

        return {
            "repaired": repaired,
            "attributes_updated": attributes_updated,
            "requested": len(targets),
            "validation_before": report,
            "validation_after": final_report,
        }

    def sync_attributes(
        self,
        point_layer,
        polygon_layer,
        expected_area_ha=33.0,
    ):
        """
        Синхронизирует строки кругов без перестроения геометрии.

        Функция полезна для старых данных, где геометрия уже верная, но
        атрибут «Площадь» или служебные поля не заполнены.
        """
        report = self.quality.validate_all(
            point_layer,
            polygon_layer,
            expected_area_ha,
        )

        polygon_field = self._number_field(polygon_layer)
        if not polygon_field:
            raise Exception(
                "В слое кругов нет поля «Номер скважины»."
            )

        report_by_number = {
            str(item.get("number", "")).strip(): item
            for item in report.get("items", [])
        }

        if not polygon_layer.isEditable() and not polygon_layer.startEditing():
            raise Exception(
                f"Не удалось включить редактирование слоя "
                f"«{polygon_layer.name()}»."
            )

        updated_features = 0
        changed_values = 0

        try:
            self._ensure_measurement_fields(polygon_layer)

            for feature in polygon_layer.getFeatures():
                number = str(feature[polygon_field]).strip()
                item = report_by_number.get(number)
                if not item:
                    continue

                area_m2 = float(item.get("area_m2", 0.0) or 0.0)
                area_ha = area_m2 / 10000.0
                radius_m = math.sqrt(area_m2 / math.pi) if area_m2 > 0 else 0.0
                center_m = float(
                    item.get("center_distance_m", 0.0) or 0.0
                )

                changed = self._write_measurement_attributes(
                    polygon_layer,
                    feature.id(),
                    area_ha,
                    area_m2=area_m2,
                    radius_m=radius_m,
                    center_offset_m=center_m,
                )
                if changed:
                    updated_features += 1
                    changed_values += changed

            if not polygon_layer.commitChanges():
                errors = "\n".join(polygon_layer.commitErrors())
                polygon_layer.rollBack()
                raise Exception(
                    "Не удалось сохранить синхронизацию атрибутов.\n"
                    + errors
                )

        except Exception:
            if polygon_layer.isEditable():
                polygon_layer.rollBack()
            raise

        polygon_layer.updateFields()
        polygon_layer.triggerRepaint()

        return {
            "features_updated": updated_features,
            "values_updated": changed_values,
        }

    def _ensure_measurement_fields(self, layer):
        """Создаёт служебные поля измерений, если их ещё нет."""
        existing = layer.fields().names()
        new_fields = []

        definitions = [
            (self.AREA_HA_FIELD, 6),
            (self.AREA_M2_FIELD, 3),
            (self.RADIUS_M_FIELD, 3),
            (self.CENTER_M_FIELD, 3),
        ]

        for name, precision in definitions:
            if name not in existing:
                new_fields.append(
                    QgsField(
                        name,
                        QVariant.Double,
                        len=20,
                        prec=precision,
                    )
                )

        for field in new_fields:
            if not layer.addAttribute(field):
                raise Exception(
                    f"Не удалось создать поле {field.name()} "
                    f"в слое «{layer.name()}»."
                )

        if new_fields:
            layer.updateFields()

    def _write_measurement_attributes(
        self,
        layer,
        feature_id,
        area_ha,
        area_m2=None,
        radius_m=None,
        center_offset_m=0.0,
    ):
        """Обновляет служебные и пользовательские поля измерений."""
        area_ha = float(area_ha)
        area_m2 = (
            float(area_m2)
            if area_m2 is not None
            else area_ha * 10000.0
        )
        radius_m = (
            float(radius_m)
            if radius_m is not None
            else math.sqrt(area_m2 / math.pi)
        )
        center_offset_m = float(center_offset_m)

        changed = 0

        for index, field in enumerate(layer.fields()):
            normalized = self._normalized_field_name(
                field.name(),
                field.alias(),
            )

            if normalized in self.HECTARE_FIELD_NAMES:
                value = area_ha
            elif normalized in self.M2_FIELD_NAMES:
                value = area_m2
            elif normalized in self.RADIUS_FIELD_NAMES:
                value = radius_m
            elif normalized in self.CENTER_FIELD_NAMES:
                value = center_offset_m
            else:
                continue

            if layer.changeAttributeValue(feature_id, index, value):
                changed += 1

        return changed

    def _write_center_offset(self, layer, feature_id, center_offset_m):
        changed = 0
        for index, field in enumerate(layer.fields()):
            normalized = self._normalized_field_name(
                field.name(),
                field.alias(),
            )
            if normalized in self.CENTER_FIELD_NAMES:
                if layer.changeAttributeValue(
                    feature_id,
                    index,
                    float(center_offset_m),
                ):
                    changed += 1
        return changed

    def _normalized_field_name(self, name, alias=""):
        """Нормализует имя/псевдоним поля для безопасного сопоставления."""
        candidates = [str(name or ""), str(alias or "")]
        for candidate in candidates:
            value = (
                candidate.strip()
                .lower()
                .replace("ё", "е")
                .replace("²", "2")
            )
            value = " ".join(value.split())
            if value:
                if value in (
                    self.HECTARE_FIELD_NAMES
                    | self.M2_FIELD_NAMES
                    | self.RADIUS_FIELD_NAMES
                    | self.CENTER_FIELD_NAMES
                ):
                    return value
        return str(name or "").strip().lower()

    def _key(self, value):
        return str(value or "").strip().casefold()

    def _number_field(self, layer):
        return well_number_field_name(layer)
