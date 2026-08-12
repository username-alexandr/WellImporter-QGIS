# -*- coding: utf-8 -*-

from qgis.PyQt.QtCore import QVariant
from qgis.core import QgsCoordinateTransform, QgsField, QgsGeometry, QgsProject, QgsSpatialIndex


class ParcelManager:
    """Определяет земельный участок для каждой скважины и переносит кадастровый номер."""

    PARCEL_FIELD = "WI_PARCEL"
    CADASTRAL_FIELD = "WI_CAD"

    def __init__(self):
        self.project = QgsProject.instance()

    def assign(self, point_layer, parcel_layer, cadastral_source_field,
               parcel_label_field=None, selected_only=False):
        if not cadastral_source_field or parcel_layer.fields().indexFromName(cadastral_source_field) < 0:
            raise Exception("Не выбрано корректное поле кадастрового номера.")
        if parcel_label_field and parcel_layer.fields().indexFromName(parcel_label_field) < 0:
            parcel_label_field = None

        self._ensure_fields(point_layer)
        parcel_features = {feature.id(): feature for feature in parcel_layer.getFeatures()}
        index = QgsSpatialIndex()
        for parcel in parcel_features.values():
            index.addFeature(parcel)
        transform = QgsCoordinateTransform(point_layer.crs(), parcel_layer.crs(), self.project)

        features = point_layer.selectedFeatures() if selected_only and point_layer.selectedFeatureCount() else list(point_layer.getFeatures())
        if not point_layer.isEditable() and not point_layer.startEditing():
            raise Exception(f"Не удалось включить редактирование слоя «{point_layer.name()}».")

        parcel_idx = point_layer.fields().indexFromName(self.PARCEL_FIELD)
        cad_idx = point_layer.fields().indexFromName(self.CADASTRAL_FIELD)
        found = 0
        not_found = 0
        multiple = 0
        try:
            for point_feature in features:
                geom = QgsGeometry(point_feature.geometry())
                geom.transform(transform)
                bbox = geom.boundingBox()
                candidates = index.intersects(bbox)
                matches = []
                for fid in candidates:
                    parcel = parcel_features.get(fid)
                    if parcel is None:
                        continue
                    if parcel.geometry().intersects(geom):
                        matches.append(parcel)

                if not matches:
                    not_found += 1
                    point_layer.changeAttributeValue(point_feature.id(), parcel_idx, "")
                    point_layer.changeAttributeValue(point_feature.id(), cad_idx, "")
                    continue

                if len(matches) > 1:
                    multiple += 1
                parcel = matches[0]
                cadastral = str(parcel[cadastral_source_field]).strip()
                label = str(parcel[parcel_label_field]).strip() if parcel_label_field else cadastral
                point_layer.changeAttributeValue(point_feature.id(), parcel_idx, label)
                point_layer.changeAttributeValue(point_feature.id(), cad_idx, cadastral)
                found += 1

            if not point_layer.commitChanges():
                errors = "\n".join(point_layer.commitErrors())
                point_layer.rollBack()
                raise Exception(f"Не удалось сохранить сведения о земельных участках.\n{errors}")
        except Exception:
            if point_layer.isEditable():
                point_layer.rollBack()
            raise

        point_layer.triggerRepaint()
        return {"processed": len(features), "found": found, "not_found": not_found, "multiple": multiple}

    def _ensure_fields(self, layer):
        existing = layer.fields().names()
        if not layer.isEditable() and not layer.startEditing():
            raise Exception(f"Не удалось включить редактирование слоя «{layer.name()}».")
        if self.PARCEL_FIELD not in existing:
            if not layer.addAttribute(QgsField(self.PARCEL_FIELD, QVariant.String, len=120)):
                raise Exception(f"Не удалось создать поле {self.PARCEL_FIELD}.")
        if self.CADASTRAL_FIELD not in existing:
            if not layer.addAttribute(QgsField(self.CADASTRAL_FIELD, QVariant.String, len=80)):
                raise Exception(f"Не удалось создать поле {self.CADASTRAL_FIELD}.")
        layer.updateFields()
        try:
            layer.setFieldAlias(layer.fields().indexFromName(self.PARCEL_FIELD), "Земельный участок")
            layer.setFieldAlias(layer.fields().indexFromName(self.CADASTRAL_FIELD), "Кадастровый номер")
        except Exception:
            pass
