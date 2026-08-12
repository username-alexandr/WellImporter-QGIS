# -*- coding: utf-8 -*-

import re

from qgis.PyQt.QtCore import QVariant
from qgis.core import (
    QgsCoordinateTransform,
    QgsField,
    QgsGeometry,
    QgsMapLayerType,
    QgsProject,
    QgsSpatialIndex,
    QgsWkbTypes,
)


class ParcelManager:
    """Автоматически определяет земельные участки для точек бурения."""

    PARCEL_FIELD = "WI_PARCEL"
    CADASTRAL_FIELD = "WI_CAD"

    def __init__(self):
        self.project = QgsProject.instance()

    def detect_source(self, excluded_layer_ids=None):
        """Автоматически выбирает наиболее вероятный полигональный слой участков.

        Решение принимается по имени слоя, физическим именам полей и псевдонимам.
        Ручной выбор не требуется. При равном рейтинге результат стабилен:
        используется имя слоя, затем его ID.
        """
        excluded = {str(value) for value in (excluded_layer_ids or []) if value}
        candidates = []
        for layer in self.project.mapLayers().values():
            if str(layer.id()) in excluded:
                continue
            if layer.type() != QgsMapLayerType.VectorLayer:
                continue
            if QgsWkbTypes.geometryType(layer.wkbType()) != QgsWkbTypes.PolygonGeometry:
                continue
            if layer.featureCount() <= 0:
                continue

            layer_score = self._layer_score(layer.name())
            cadastral_field, cadastral_score = self._best_field(
                layer, self._cadastral_field_score
            )
            label_field, label_score = self._best_field(
                layer, self._label_field_score
            )
            score = layer_score + cadastral_score + label_score
            if score <= 0:
                continue
            candidates.append({
                "layer": layer,
                "layer_id": layer.id(),
                "layer_name": layer.name(),
                "label_field": label_field,
                "cadastral_field": cadastral_field,
                "score": score,
                "layer_score": layer_score,
                "label_score": label_score,
                "cadastral_score": cadastral_score,
            })

        if not candidates:
            raise Exception(
                "Не удалось автоматически определить полигональный слой земельных участков. "
                "Проверьте, что в проект добавлен слой участков с понятными именами полей."
            )

        candidates.sort(
            key=lambda item: (
                -int(item["score"]),
                str(item["layer_name"]).casefold(),
                str(item["layer_id"]),
            )
        )
        return candidates[0]

    def assign_parcel_names_auto(self, point_layer, excluded_layer_ids=None, selected_only=False):
        """Автоматически определяет участок каждой точки и заполняет WI_PARCEL."""
        source = self.detect_source(excluded_layer_ids)
        parcel_layer = source["layer"]
        label_field = source.get("label_field")
        cadastral_field = source.get("cadastral_field")

        self._ensure_fields(point_layer)
        parcel_idx = point_layer.fields().indexFromName(self.PARCEL_FIELD)
        features = (
            point_layer.selectedFeatures()
            if selected_only and point_layer.selectedFeatureCount()
            else list(point_layer.getFeatures())
        )
        parcel_features, index, transform = self._prepare_index(point_layer, parcel_layer)

        if not point_layer.isEditable() and not point_layer.startEditing():
            raise Exception(f"Не удалось включить редактирование слоя «{point_layer.name()}».")

        found = 0
        not_found = 0
        multiple = 0
        try:
            for point_feature in features:
                matches, point_geom = self._matches(
                    point_feature, parcel_features, index, transform
                )
                if not matches:
                    not_found += 1
                    point_layer.changeAttributeValue(point_feature.id(), parcel_idx, "")
                    continue

                if len(matches) > 1:
                    multiple += 1
                parcel = self._choose_match(matches, point_geom)
                label = self._parcel_label(parcel, label_field, cadastral_field)
                point_layer.changeAttributeValue(point_feature.id(), parcel_idx, label)
                found += 1

            self._commit(point_layer, "Не удалось сохранить сведения о земельных участках.")
        except Exception:
            if point_layer.isEditable():
                point_layer.rollBack()
            raise

        point_layer.triggerRepaint()
        return {
            "processed": len(features),
            "found": found,
            "not_found": not_found,
            "multiple": multiple,
            "source_layer": parcel_layer.name(),
            "source_layer_id": parcel_layer.id(),
            "label_field": label_field or "",
            "cadastral_field": cadastral_field or "",
            "score": source.get("score", 0),
        }

    def assign(self, point_layer, parcel_layer, cadastral_source_field,
               parcel_label_field=None, selected_only=False):
        """Совместимый низкоуровневый метод для старых вызовов плагина."""
        if not cadastral_source_field or parcel_layer.fields().indexFromName(cadastral_source_field) < 0:
            raise Exception("Не выбрано корректное поле кадастрового номера.")
        if parcel_label_field and parcel_layer.fields().indexFromName(parcel_label_field) < 0:
            parcel_label_field = None

        self._ensure_fields(point_layer)
        parcel_features, index, transform = self._prepare_index(point_layer, parcel_layer)
        features = (
            point_layer.selectedFeatures()
            if selected_only and point_layer.selectedFeatureCount()
            else list(point_layer.getFeatures())
        )
        if not point_layer.isEditable() and not point_layer.startEditing():
            raise Exception(f"Не удалось включить редактирование слоя «{point_layer.name()}».")

        parcel_idx = point_layer.fields().indexFromName(self.PARCEL_FIELD)
        cad_idx = point_layer.fields().indexFromName(self.CADASTRAL_FIELD)
        found = 0
        not_found = 0
        multiple = 0
        try:
            for point_feature in features:
                matches, point_geom = self._matches(
                    point_feature, parcel_features, index, transform
                )
                if not matches:
                    not_found += 1
                    point_layer.changeAttributeValue(point_feature.id(), parcel_idx, "")
                    point_layer.changeAttributeValue(point_feature.id(), cad_idx, "")
                    continue
                if len(matches) > 1:
                    multiple += 1
                parcel = self._choose_match(matches, point_geom)
                cadastral = str(parcel[cadastral_source_field] or "").strip()
                label = (
                    str(parcel[parcel_label_field] or "").strip()
                    if parcel_label_field else cadastral
                )
                point_layer.changeAttributeValue(point_feature.id(), parcel_idx, label)
                point_layer.changeAttributeValue(point_feature.id(), cad_idx, cadastral)
                found += 1
            self._commit(point_layer, "Не удалось сохранить сведения о земельных участках.")
        except Exception:
            if point_layer.isEditable():
                point_layer.rollBack()
            raise

        point_layer.triggerRepaint()
        return {
            "processed": len(features),
            "found": found,
            "not_found": not_found,
            "multiple": multiple,
        }

    def _prepare_index(self, point_layer, parcel_layer):
        parcel_features = {feature.id(): feature for feature in parcel_layer.getFeatures()}
        index = QgsSpatialIndex()
        for parcel in parcel_features.values():
            if parcel.hasGeometry() and not parcel.geometry().isEmpty():
                index.addFeature(parcel)
        transform = QgsCoordinateTransform(
            point_layer.crs(), parcel_layer.crs(), self.project
        )
        return parcel_features, index, transform

    def _matches(self, point_feature, parcel_features, index, transform):
        if not point_feature.hasGeometry() or point_feature.geometry().isEmpty():
            return [], QgsGeometry()
        geom = QgsGeometry(point_feature.geometry())
        geom.transform(transform)
        candidates = index.intersects(geom.boundingBox())
        matches = []
        for fid in candidates:
            parcel = parcel_features.get(fid)
            if parcel is not None and parcel.geometry().intersects(geom):
                matches.append(parcel)
        return matches, geom

    def _choose_match(self, matches, point_geom):
        """При перекрывающихся полигонах выбирает ближайший по центроиду участок."""
        if len(matches) <= 1:
            return matches[0]
        return min(
            matches,
            key=lambda parcel: (
                float(parcel.geometry().centroid().distance(point_geom)),
                int(parcel.id()),
            ),
        )

    def _parcel_label(self, parcel, label_field, cadastral_field):
        if label_field:
            value = str(parcel[label_field] or "").strip()
            if value:
                return value
        if cadastral_field:
            value = str(parcel[cadastral_field] or "").strip()
            if value:
                return value
        return str(parcel.id())

    def _best_field(self, layer, scorer):
        best_name = ""
        best_score = 0
        for field in layer.fields():
            score = max(scorer(field.name()), scorer(field.alias()))
            if score > best_score:
                best_name = field.name()
                best_score = score
        return best_name, best_score

    def _layer_score(self, value):
        text = self._normalize(value)
        score = 0
        if "земель" in text:
            score += 35
        if "участ" in text:
            score += 35
        if "кадастр" in text:
            score += 30
        if "parcel" in text:
            score += 30
        if "границ" in text:
            score += 10
        return score

    def _label_field_score(self, value):
        text = self._normalize(value)
        if not text:
            return 0
        score = 0
        if "участ" in text:
            score += 30
        if "наимен" in text:
            score += 25
        if text in {"name", "parcel", "parcelname", "название"}:
            score += 25
        if "земель" in text:
            score += 20
        return score

    def _cadastral_field_score(self, value):
        text = self._normalize(value)
        if not text:
            return 0
        score = 0
        if "кадастров" in text:
            score += 50
        if "номер" in text and "кадастр" in text:
            score += 30
        if "cad" in text:
            score += 25
        if "cadastral" in text:
            score += 35
        if text in {"cn", "cadnum", "cadnumber", "cad_num"}:
            score += 30
        return score

    def _normalize(self, value):
        return re.sub(r"[^0-9a-zа-я]+", "", str(value or "").strip().lower().replace("ё", "е"))

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

    def _commit(self, layer, message):
        if not layer.commitChanges():
            errors = "\n".join(layer.commitErrors())
            layer.rollBack()
            raise Exception(message + "\n" + errors)
