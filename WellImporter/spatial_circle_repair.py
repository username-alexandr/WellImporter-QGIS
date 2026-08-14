# -*- coding: utf-8 -*-

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsDistanceArea,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsSpatialIndex,
    QgsVectorLayerUtils,
)

from .circle_repair import CircleRepairManager
from .spatial_pairing import greedy_unique_pairs
from .well_number_field import (
    ensure_well_number_field,
    feature_well_number,
    set_feature_well_number,
    well_number_field_name,
)


class SpatialCircleRepairManager(CircleRepairManager):
    """Достраивает отсутствующие круги по фактической пространственной паре.

    Старый алгоритм считал круг существующим, если такой номер встречался где-либо
    в полигональном слое. Это ломало старые данные и повторяющиеся номера разных
    лет. Здесь существующие точки и круги сначала сопоставляются 1:1 по расстоянию
    между точкой и центром круга, после чего круг создаётся только для реально
    оставшейся без пары точки.
    """

    WGS84 = QgsCoordinateReferenceSystem("EPSG:4326")

    def __init__(self, max_pair_distance_m=50.0, nearest_candidates=16):
        super().__init__()
        self.max_pair_distance_m = float(max_pair_distance_m)
        self.nearest_candidates = max(1, int(nearest_candidates))
        self.project = QgsProject.instance()

    def create_missing_circles(
        self,
        point_layer,
        polygon_layer,
        expected_area_ha=33.0,
    ):
        point_field = well_number_field_name(point_layer)
        if not point_field:
            raise Exception("В слое точек отсутствует поле «Номер скважины».")

        if not polygon_layer.isEditable() and not polygon_layer.startEditing():
            raise Exception(
                f"Не удалось включить редактирование слоя «{polygon_layer.name()}»."
            )

        created = 0
        skipped_existing = 0
        skipped_without_number = 0
        skipped_without_geometry = 0

        try:
            ensure_well_number_field(polygon_layer)
            self._ensure_measurement_fields(polygon_layer)

            point_features = list(point_layer.getFeatures())
            polygon_features = list(polygon_layer.getFeatures())

            point_to_wgs = QgsCoordinateTransform(
                point_layer.crs(), self.WGS84, self.project
            )
            point_to_polygon = QgsCoordinateTransform(
                point_layer.crs(), polygon_layer.crs(), self.project
            )
            polygon_to_wgs = QgsCoordinateTransform(
                polygon_layer.crs(), self.WGS84, self.project
            )

            distance_meter = QgsDistanceArea()
            distance_meter.setSourceCrs(
                self.WGS84, self.project.transformContext()
            )
            distance_meter.setEllipsoid("WGS84")

            spatial_index = QgsSpatialIndex()
            polygon_centers_wgs = {}
            for polygon in polygon_features:
                if not polygon.hasGeometry() or polygon.geometry().isEmpty():
                    continue
                centroid_geometry = polygon.geometry().centroid()
                if centroid_geometry.isEmpty():
                    continue
                spatial_index.addFeature(polygon)
                centroid = centroid_geometry.asPoint()
                polygon_centers_wgs[polygon.id()] = polygon_to_wgs.transform(
                    QgsPointXY(centroid)
                )

            valid_points = {}
            point_centers_wgs = {}
            candidates = []

            for point_feature in point_features:
                number = feature_well_number(
                    point_feature, point_layer, ""
                ).strip()
                if not number:
                    skipped_without_number += 1
                    continue
                if (
                    not point_feature.hasGeometry()
                    or point_feature.geometry().isEmpty()
                ):
                    skipped_without_geometry += 1
                    continue

                point = point_feature.geometry().asPoint()
                point_wgs = point_to_wgs.transform(QgsPointXY(point))
                point_polygon = point_to_polygon.transform(QgsPointXY(point))
                point_id = point_feature.id()
                valid_points[point_id] = (point_feature, number)
                point_centers_wgs[point_id] = point_wgs

                for polygon_id in spatial_index.nearestNeighbor(
                    QgsPointXY(point_polygon), self.nearest_candidates
                ):
                    polygon_wgs = polygon_centers_wgs.get(polygon_id)
                    if polygon_wgs is None:
                        continue
                    distance_m = float(
                        distance_meter.measureLine(point_wgs, polygon_wgs)
                    )
                    if distance_m <= self.max_pair_distance_m:
                        candidates.append((distance_m, point_id, polygon_id))

            existing_pairs = greedy_unique_pairs(
                candidates, max_distance_m=self.max_pair_distance_m
            )

            point_batch_index = point_layer.fields().indexFromName("WI_BATCH")
            polygon_batch_index = polygon_layer.fields().indexFromName("WI_BATCH")

            for point_id, (point_feature, number) in valid_points.items():
                if point_id in existing_pairs:
                    skipped_existing += 1
                    continue

                point_wgs = point_centers_wgs[point_id]
                new_geometry = self.geometry.create_circle_for_layer(
                    point_wgs.x(), point_wgs.y(),
                    float(expected_area_ha), polygon_layer,
                )
                feature = QgsVectorLayerUtils.createFeature(
                    polygon_layer, QgsGeometry(new_geometry)
                )
                set_feature_well_number(feature, polygon_layer, number)

                if point_batch_index >= 0 and polygon_batch_index >= 0:
                    batch_value = point_feature[point_batch_index]
                    if batch_value is not None:
                        feature.setAttribute(polygon_batch_index, batch_value)

                if not polygon_layer.addFeature(feature):
                    raise Exception(
                        f"Не удалось создать площадной круг для скважины №{number}."
                    )

                self._write_measurement_attributes(
                    polygon_layer,
                    feature.id(),
                    float(expected_area_ha),
                    center_offset_m=0.0,
                )
                created += 1

            if not polygon_layer.commitChanges():
                errors = "\n".join(polygon_layer.commitErrors())
                polygon_layer.rollBack()
                raise Exception(
                    "Не удалось сохранить созданные площадные круги.\n" + errors
                )

        except Exception:
            if polygon_layer.isEditable():
                polygon_layer.rollBack()
            raise

        polygon_layer.updateFields()
        polygon_layer.updateExtents()
        polygon_layer.triggerRepaint()

        return {
            "created": created,
            "skipped_existing": skipped_existing,
            "skipped_without_number": skipped_without_number,
            "skipped_without_geometry": skipped_without_geometry,
            "max_pair_distance_m": self.max_pair_distance_m,
        }
