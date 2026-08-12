# -*- coding: utf-8 -*-

from qgis.PyQt.QtCore import QVariant
from qgis.core import (
    QgsCoordinateTransform,
    QgsField,
    QgsGeometry,
    QgsProject,
    QgsSpatialIndex,
    QgsVectorLayerUtils,
)

from .well_number_field import (
    ensure_well_number_field,
    feature_well_number,
    set_feature_well_number,
    well_number_field_name,
)


class PointRepairManager:
    """
    Исправляет точки бурения только там, где значение можно восстановить
    однозначно из площадного круга или текущих настроек Well Importer.

    Исправления:
    - создаёт поле «Номер скважины», если его нет;
    - создаёт поле «Год», если его нет;
    - заполняет пустой год текущим годом из главного окна;
    - восстанавливает пустой номер по площадному кругу, содержащему точку;
    - восстанавливает пустую геометрию точки по центру круга с тем же номером;
    - создаёт отсутствующую точку для круга с номером скважины.
    """

    YEAR_FIELD = "Год"
    BATCH_FIELD = "WI_BATCH"

    def __init__(self):
        self.project = QgsProject.instance()

    def repair(self, point_layer, polygon_layer, default_year):
        if not point_layer.isEditable() and not point_layer.startEditing():
            raise Exception(
                f"Не удалось включить редактирование слоя «{point_layer.name()}»."
            )

        created_points = 0
        restored_numbers = 0
        restored_geometry = 0
        filled_years = 0

        try:
            point_number_index = ensure_well_number_field(point_layer)
            year_index = self._ensure_year_field(point_layer)

            polygon_number_field = well_number_field_name(polygon_layer)
            if not polygon_number_field:
                raise Exception(
                    "В слое площадных кругов отсутствует поле «Номер скважины»."
                )

            polygons = list(polygon_layer.getFeatures())
            polygon_by_key = {}
            polygon_by_id = {}
            spatial_index = QgsSpatialIndex()

            for polygon in polygons:
                polygon_by_id[polygon.id()] = polygon
                number = str(polygon[polygon_number_field] or "").strip()
                if number:
                    polygon_by_key[self._key(number)] = polygon
                if polygon.hasGeometry() and not polygon.geometry().isEmpty():
                    spatial_index.addFeature(polygon)

            point_to_polygon = QgsCoordinateTransform(
                point_layer.crs(),
                polygon_layer.crs(),
                self.project,
            )
            polygon_to_point = QgsCoordinateTransform(
                polygon_layer.crs(),
                point_layer.crs(),
                self.project,
            )

            # 1. Исправляем уже существующие точки.
            for feature in list(point_layer.getFeatures()):
                number = feature_well_number(feature, point_layer, "")
                geometry = feature.geometry()

                # Пустой номер: определяем круг, внутри которого находится точка.
                if (
                    not number
                    and feature.hasGeometry()
                    and geometry is not None
                    and not geometry.isEmpty()
                ):
                    point_in_polygon_crs = QgsGeometry(geometry)
                    point_in_polygon_crs.transform(point_to_polygon)

                    candidates = []
                    for fid in spatial_index.intersects(
                        point_in_polygon_crs.boundingBox()
                    ):
                        polygon = polygon_by_id.get(fid)
                        if polygon is None:
                            continue
                        polygon_number = str(
                            polygon[polygon_number_field] or ""
                        ).strip()
                        if not polygon_number:
                            continue
                        polygon_geom = polygon.geometry()
                        if (
                            polygon_geom.contains(point_in_polygon_crs)
                            or polygon_geom.intersects(point_in_polygon_crs)
                        ):
                            centroid = polygon_geom.centroid()
                            distance = centroid.distance(point_in_polygon_crs)
                            candidates.append(
                                (distance, polygon_number, polygon)
                            )

                    if candidates:
                        candidates.sort(key=lambda item: item[0])
                        inferred_number = candidates[0][1]
                        if point_layer.changeAttributeValue(
                            feature.id(),
                            point_number_index,
                            inferred_number,
                        ):
                            restored_numbers += 1
                            number = inferred_number

                # Пустая геометрия: восстанавливаем из центра круга того же номера.
                if (
                    number
                    and (
                        not feature.hasGeometry()
                        or geometry is None
                        or geometry.isEmpty()
                    )
                ):
                    polygon = polygon_by_key.get(self._key(number))
                    if polygon is not None and polygon.hasGeometry():
                        center = polygon.geometry().centroid()
                        center.transform(polygon_to_point)
                        if point_layer.changeGeometry(feature.id(), center):
                            restored_geometry += 1

                # Пустой год: подставляем год из настроек главного окна.
                current_year = feature[year_index]
                if self._is_blank(current_year):
                    if point_layer.changeAttributeValue(
                        feature.id(),
                        year_index,
                        str(default_year),
                    ):
                        filled_years += 1

            # 2. После восстановления номеров определяем, каких точек ещё нет.
            existing_numbers = set()
            for feature in point_layer.getFeatures():
                number = feature_well_number(feature, point_layer, "")
                if number:
                    existing_numbers.add(self._key(number))

            point_batch_index = point_layer.fields().indexFromName(
                self.BATCH_FIELD
            )
            polygon_batch_index = polygon_layer.fields().indexFromName(
                self.BATCH_FIELD
            )

            for polygon in polygons:
                number = str(polygon[polygon_number_field] or "").strip()
                if not number:
                    continue
                key = self._key(number)
                if key in existing_numbers:
                    continue
                if not polygon.hasGeometry() or polygon.geometry().isEmpty():
                    continue

                center = polygon.geometry().centroid()
                center.transform(polygon_to_point)

                new_feature = QgsVectorLayerUtils.createFeature(
                    point_layer,
                    center,
                )
                set_feature_well_number(
                    new_feature,
                    point_layer,
                    number,
                )
                new_feature.setAttribute(year_index, str(default_year))
                self._clear_irrigation_system(new_feature)

                if (
                    point_batch_index >= 0
                    and polygon_batch_index >= 0
                ):
                    batch_value = polygon[polygon_batch_index]
                    if batch_value is not None:
                        new_feature.setAttribute(
                            point_batch_index,
                            batch_value,
                        )

                if not point_layer.addFeature(new_feature):
                    raise Exception(
                        f"Не удалось создать точку для скважины №{number}."
                    )

                created_points += 1
                existing_numbers.add(key)

            if not point_layer.commitChanges():
                errors = "\n".join(point_layer.commitErrors())
                point_layer.rollBack()
                raise Exception(
                    "Не удалось сохранить исправления точек.\n" + errors
                )

        except Exception:
            if point_layer.isEditable():
                point_layer.rollBack()
            raise

        point_layer.updateFields()
        point_layer.updateExtents()
        point_layer.triggerRepaint()

        return {
            "created_points": created_points,
            "restored_numbers": restored_numbers,
            "restored_geometry": restored_geometry,
            "filled_years": filled_years,
            "total_changes": (
                created_points
                + restored_numbers
                + restored_geometry
                + filled_years
            ),
        }

    def _ensure_year_field(self, layer):
        # Сначала ищем по физическому имени.
        index = layer.fields().indexFromName(self.YEAR_FIELD)
        if index >= 0:
            return index

        # Затем по псевдониму.
        for index, field in enumerate(layer.fields()):
            if str(field.alias() or "").strip().lower() == "год":
                return index

        if not layer.addAttribute(
            QgsField(self.YEAR_FIELD, QVariant.String, len=16)
        ):
            raise Exception(
                f"Не удалось создать поле «{self.YEAR_FIELD}» "
                f"в слое «{layer.name()}»."
            )

        layer.updateFields()
        index = layer.fields().indexFromName(self.YEAR_FIELD)
        if index < 0:
            raise Exception("QGIS не смог определить поле «Год».")
        return index

    def _clear_irrigation_system(self, feature):
        accepted = {
            "оросительная система",
            "оросит. система",
            "оросит система",
            "орос. система",
            "irrigation system",
        }

        for index, field in enumerate(feature.fields()):
            candidates = {
                self._normalize(field.name()),
                self._normalize(field.alias()),
            }
            if candidates & accepted:
                feature.setAttribute(index, None)

    def _normalize(self, value):
        return (
            str(value or "")
            .strip()
            .lower()
            .replace("ё", "е")
        )

    def _key(self, value):
        return str(value or "").strip().casefold()

    def _is_blank(self, value):
        return (
            value is None
            or str(value).strip() in ("", "NULL", "None")
        )
