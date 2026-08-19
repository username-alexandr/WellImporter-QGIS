# -*- coding: utf-8 -*-

from qgis.PyQt.QtCore import QVariant
from qgis.core import QgsCoordinateTransform, QgsFeature, QgsField, QgsGeometry, QgsVectorLayer

from .parcel_group_manager import ParcelGroupManager


class ParcelGroupManagerV224(ParcelGroupManager):
    """Защитные runtime-дополнения групповой логики 2.2.4."""

    def assign_group(self, point_layer, group_path, excluded_layer_ids=None,
                     selected_only=False, include_cadastral=True):
        if selected_only and int(point_layer.selectedFeatureCount()) <= 0:
            raise Exception(
                "Включён режим «только выделенные скважины», но в слое нет выделенных объектов."
            )
        return super().assign_group(
            point_layer,
            group_path,
            excluded_layer_ids=excluded_layer_ids,
            selected_only=selected_only,
            include_cadastral=include_cadastral,
        )

    def create_selection_layer(self, point_layer, group_path, excluded_layer_ids=None):
        """Создаёт multipart-совместимый временный слой всех участков группы."""
        layers = self.layers_for_group(group_path, excluded_layer_ids)
        target_crs = point_layer.crs()
        authid = target_crs.authid() or "EPSG:4326"
        result = QgsVectorLayer(
            f"MultiPolygon?crs={authid}",
            "Well Importer — участки выбранной группы",
            "memory",
        )
        provider = result.dataProvider()
        provider.addAttributes([
            QgsField("SRC_LAYER", QVariant.String, len=120),
            QgsField("SRC_FID", QVariant.LongLong),
            QgsField("PARCEL", QVariant.String, len=160),
            QgsField("CAD", QVariant.String, len=100),
            QgsField("PURPOSE", QVariant.String, len=160),
        ])
        result.updateFields()

        out_features = []
        for layer in layers:
            source = self._source_definition(layer)
            transform = QgsCoordinateTransform(layer.crs(), target_crs, self.project)
            for parcel in layer.getFeatures():
                if not parcel.hasGeometry() or parcel.geometry().isEmpty():
                    continue
                geom = QgsGeometry(parcel.geometry())
                geom.transform(transform)
                if not geom.isMultipart():
                    geom.convertToMultiType()
                feature = QgsFeature(result.fields())
                feature.setGeometry(geom)
                cadastral = self._field_text(parcel, source["cadastral_field"])
                feature["SRC_LAYER"] = layer.name()
                feature["SRC_FID"] = int(parcel.id())
                feature["PARCEL"] = self._parcel_label(parcel, source, cadastral)
                feature["CAD"] = cadastral
                feature["PURPOSE"] = self._purpose_value(parcel, source)
                out_features.append(feature)

        ok, _ = provider.addFeatures(out_features)
        if not ok and out_features:
            raise Exception("Не удалось создать временный объединённый слой земельных участков.")
        result.updateExtents()
        return result
