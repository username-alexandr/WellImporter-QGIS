# -*- coding: utf-8 -*-

import re

from qgis.PyQt.QtCore import QVariant
from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsFeature,
    QgsField,
    QgsGeometry,
    QgsLayerTreeGroup,
    QgsMapLayerType,
    QgsProject,
    QgsSpatialIndex,
    QgsVectorLayer,
    QgsWkbTypes,
)


class ParcelGroupManager:
    """Работает со всеми слоями участков внутри выбранной группы QGIS.

    Группа выбирается пользователем один раз. Для каждой скважины поиск
    выполняется пространственно по каждому полигональному слою внутри группы,
    включая вложенные подгруппы. Если точка попадает более чем в один полигон,
    результат считается конфликтом и не выбирается автоматически.
    """

    PARCEL_FIELD = "WI_PARCEL"
    CADASTRAL_FIELD = "WI_CAD"
    PURPOSE_FIELD = "WI_USE"
    SOURCE_FIELD = "WI_SRC"

    def __init__(self, project=None):
        self.project = project or QgsProject.instance()

    # ------------------------------------------------------------------
    # Группы и источники
    # ------------------------------------------------------------------
    def group_paths(self, excluded_layer_ids=None):
        """Возвращает пути групп, содержащих подходящие полигональные слои."""
        excluded = {str(value) for value in (excluded_layer_ids or []) if value}
        root = self.project.layerTreeRoot()
        result = []

        def walk(group, prefix=""):
            for child in group.children():
                if not isinstance(child, QgsLayerTreeGroup):
                    continue
                path = f"{prefix}/{child.name()}" if prefix else child.name()
                if self.layers_for_group(path, excluded_layer_ids=excluded, allow_empty=True):
                    result.append(path)
                walk(child, path)

        walk(root)
        return sorted(set(result), key=lambda value: value.casefold())

    def find_group(self, group_path):
        path = str(group_path or "").strip().strip("/")
        if not path:
            raise Exception(
                "Не выбрана группа земельных участков. Откройте Центр управления → "
                "Земельные участки и выберите группу слоёв."
            )

        current = self.project.layerTreeRoot()
        for part in [item for item in path.split("/") if item]:
            match = None
            for child in current.children():
                if isinstance(child, QgsLayerTreeGroup) and child.name() == part:
                    match = child
                    break
            if match is None:
                raise Exception(f"Группа земельных участков «{path}» не найдена в проекте.")
            current = match
        return current

    def layers_for_group(self, group_path, excluded_layer_ids=None, allow_empty=False):
        """Возвращает все полигональные vector-слои выбранной группы рекурсивно."""
        excluded = {str(value) for value in (excluded_layer_ids or []) if value}
        try:
            group = self.find_group(group_path)
        except Exception:
            if allow_empty:
                return []
            raise

        layers = []
        for layer_node in group.findLayers():
            layer = layer_node.layer()
            if layer is None or str(layer.id()) in excluded:
                continue
            if layer.type() != QgsMapLayerType.VectorLayer:
                continue
            if QgsWkbTypes.geometryType(layer.wkbType()) != QgsWkbTypes.PolygonGeometry:
                continue
            layers.append(layer)

        layers.sort(key=lambda layer: (layer.name().casefold(), str(layer.id())))
        if not layers and not allow_empty:
            raise Exception(
                f"В группе «{group_path}» не найдено полигональных слоёв земельных участков."
            )
        return layers

    def describe_group(self, group_path, excluded_layer_ids=None):
        layers = self.layers_for_group(group_path, excluded_layer_ids)
        sources = [self._source_definition(layer) for layer in layers]
        return {
            "group_path": group_path,
            "layer_count": len(layers),
            "layers": [
                {
                    "layer_id": item["layer"].id(),
                    "layer_name": item["layer"].name(),
                    "label_field": item["label_field"],
                    "cadastral_field": item["cadastral_field"],
                    "purpose_field": item["purpose_field"],
                }
                for item in sources
            ],
            "cadastral_layers": sum(1 for item in sources if item["cadastral_field"]),
            "purpose_layers": sum(1 for item in sources if item["purpose_field"]),
        }

    # ------------------------------------------------------------------
    # Определение участка для каждой скважины
    # ------------------------------------------------------------------
    def assign_group(self, point_layer, group_path, excluded_layer_ids=None,
                     selected_only=False, include_cadastral=True):
        layers = self.layers_for_group(group_path, excluded_layer_ids)
        sources = self._prepare_sources(point_layer, layers)
        features = (
            list(point_layer.selectedFeatures())
            if selected_only and point_layer.selectedFeatureCount()
            else list(point_layer.getFeatures())
        )

        was_editable = bool(point_layer.isEditable())
        if not was_editable and not point_layer.startEditing():
            raise Exception(f"Не удалось включить редактирование слоя «{point_layer.name()}».")
        self._ensure_fields(point_layer)

        parcel_idx = point_layer.fields().indexFromName(self.PARCEL_FIELD)
        cad_idx = point_layer.fields().indexFromName(self.CADASTRAL_FIELD)
        purpose_idx = point_layer.fields().indexFromName(self.PURPOSE_FIELD)
        source_idx = point_layer.fields().indexFromName(self.SOURCE_FIELD)

        found = 0
        not_found = 0
        conflicts = []
        cadastral_found = 0
        cadastral_empty = 0
        purpose_found = 0

        try:
            for point_feature in features:
                matches = self._all_matches(point_feature, sources)
                if not matches:
                    not_found += 1
                    self._write_values(
                        point_layer, point_feature.id(),
                        parcel_idx, cad_idx, purpose_idx, source_idx,
                        "", "", "", "",
                    )
                    continue

                if len(matches) > 1:
                    conflict = self._conflict_record(point_feature, matches)
                    conflicts.append(conflict)
                    self._write_values(
                        point_layer, point_feature.id(),
                        parcel_idx, cad_idx, purpose_idx, source_idx,
                        "", "", "", "КОНФЛИКТ",
                    )
                    continue

                match = matches[0]
                source = match["source"]
                parcel = match["feature"]
                cadastral = self._field_text(parcel, source["cadastral_field"]) if include_cadastral else ""
                label = self._parcel_label(parcel, source, cadastral)
                purpose = self._purpose_value(parcel, source)
                source_name = source["layer"].name()

                self._write_values(
                    point_layer, point_feature.id(),
                    parcel_idx, cad_idx, purpose_idx, source_idx,
                    label, cadastral, purpose, source_name,
                )
                found += 1
                if cadastral:
                    cadastral_found += 1
                else:
                    cadastral_empty += 1
                if purpose:
                    purpose_found += 1

            if not was_editable:
                self._commit(point_layer, "Не удалось сохранить сведения о земельных участках.")
        except Exception:
            if not was_editable and point_layer.isEditable():
                point_layer.rollBack()
            raise

        point_layer.triggerRepaint()
        return {
            "processed": len(features),
            "found": found,
            "not_found": not_found,
            "conflict_count": len(conflicts),
            "conflicts": conflicts,
            "cadastral_found": cadastral_found,
            "cadastral_empty": cadastral_empty,
            "purpose_found": purpose_found,
            "group_path": group_path,
            "source_layers": [layer.name() for layer in layers],
            "source_layer_count": len(layers),
            "left_uncommitted": was_editable,
        }

    def create_selection_layer(self, point_layer, group_path, excluded_layer_ids=None):
        """Создаёт временный объединённый слой участков для выбора территории выезда."""
        layers = self.layers_for_group(group_path, excluded_layer_ids)
        target_crs = point_layer.crs()
        authid = target_crs.authid() or "EPSG:4326"
        result = QgsVectorLayer(f"Polygon?crs={authid}", "Well Importer — участки выбранной группы", "memory")
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
                feature = QgsFeature(result.fields())
                feature.setGeometry(geom)
                cadastral = self._field_text(parcel, source["cadastral_field"])
                feature["SRC_LAYER"] = layer.name()
                feature["SRC_FID"] = int(parcel.id())
                feature["PARCEL"] = self._parcel_label(parcel, source, cadastral)
                feature["CAD"] = cadastral
                feature["PURPOSE"] = self._purpose_value(parcel, source)
                out_features.append(feature)

        provider.addFeatures(out_features)
        result.updateExtents()
        return result

    # ------------------------------------------------------------------
    # Внутренняя логика
    # ------------------------------------------------------------------
    def _prepare_sources(self, point_layer, layers):
        sources = []
        for layer in layers:
            source = self._source_definition(layer)
            feature_map = {
                feature.id(): feature
                for feature in layer.getFeatures()
                if feature.hasGeometry() and not feature.geometry().isEmpty()
            }
            index = QgsSpatialIndex()
            for feature in feature_map.values():
                index.addFeature(feature)
            source.update({
                "features": feature_map,
                "index": index,
                "transform": QgsCoordinateTransform(point_layer.crs(), layer.crs(), self.project),
            })
            sources.append(source)
        return sources

    def _all_matches(self, point_feature, sources):
        if not point_feature.hasGeometry() or point_feature.geometry().isEmpty():
            return []
        matches = []
        for source in sources:
            geom = QgsGeometry(point_feature.geometry())
            geom.transform(source["transform"])
            for fid in source["index"].intersects(geom.boundingBox()):
                parcel = source["features"].get(fid)
                if parcel is not None and parcel.geometry().intersects(geom):
                    matches.append({"source": source, "feature": parcel})
        return matches

    def _conflict_record(self, point_feature, matches):
        variants = []
        for match in matches:
            source = match["source"]
            parcel = match["feature"]
            cadastral = self._field_text(parcel, source["cadastral_field"])
            variants.append({
                "layer": source["layer"].name(),
                "feature_id": int(parcel.id()),
                "parcel": self._parcel_label(parcel, source, cadastral),
                "cadastral": cadastral,
                "purpose": self._purpose_value(parcel, source),
            })
        return {
            "point_feature_id": int(point_feature.id()),
            "matches": variants,
            "message": "Скважина одновременно попадает в несколько земельных участков.",
        }

    def _source_definition(self, layer):
        cadastral_field, _ = self._best_field(layer, self._cadastral_field_score)
        label_field, _ = self._best_field(layer, self._label_field_score)
        purpose_field, _ = self._best_field(layer, self._purpose_field_score)
        return {
            "layer": layer,
            "label_field": label_field,
            "cadastral_field": cadastral_field,
            "purpose_field": purpose_field,
        }

    def _purpose_value(self, parcel, source):
        value = self._field_text(parcel, source.get("purpose_field"))
        return value or source["layer"].name()

    def _parcel_label(self, parcel, source, cadastral=""):
        value = self._field_text(parcel, source.get("label_field"))
        if value:
            return value
        if cadastral:
            return cadastral
        return f"{source['layer'].name()} / FID {parcel.id()}"

    def _field_text(self, feature, field_name):
        if not field_name:
            return ""
        try:
            return str(feature[field_name] or "").strip()
        except Exception:
            return ""

    def _write_values(self, layer, fid, parcel_idx, cad_idx, purpose_idx, source_idx,
                      parcel, cadastral, purpose, source):
        layer.changeAttributeValue(fid, parcel_idx, parcel)
        layer.changeAttributeValue(fid, cad_idx, cadastral)
        layer.changeAttributeValue(fid, purpose_idx, purpose)
        layer.changeAttributeValue(fid, source_idx, source)

    def _ensure_fields(self, layer):
        existing = set(layer.fields().names())
        definitions = [
            (self.PARCEL_FIELD, "Земельный участок", 160),
            (self.CADASTRAL_FIELD, "Кадастровый номер", 100),
            (self.PURPOSE_FIELD, "Назначение участка", 160),
            (self.SOURCE_FIELD, "Источник участка", 160),
        ]
        added = False
        for name, alias, length in definitions:
            if name not in existing:
                if not layer.addAttribute(QgsField(name, QVariant.String, len=length)):
                    raise Exception(f"Не удалось создать поле {name}.")
                added = True
        if added:
            layer.updateFields()
        for name, alias, _ in definitions:
            index = layer.fields().indexFromName(name)
            if index >= 0:
                try:
                    layer.setFieldAlias(index, alias)
                except Exception:
                    pass

    def _best_field(self, layer, scorer):
        best_name = ""
        best_score = 0
        for field in layer.fields():
            candidates = [field.name()]
            try:
                candidates.append(field.alias())
            except Exception:
                pass
            score = max(scorer(value) for value in candidates)
            if score > best_score:
                best_score = score
                best_name = field.name()
        return best_name, best_score

    def _label_field_score(self, value):
        text = self._normalize(value)
        score = 0
        if "участ" in text:
            score += 35
        if "наимен" in text or "назван" in text:
            score += 30
        if text in {"name", "parcel", "parcelname"}:
            score += 25
        if "земель" in text:
            score += 15
        return score

    def _cadastral_field_score(self, value):
        text = self._normalize(value)
        score = 0
        if "кадастров" in text:
            score += 60
        if "кадастр" in text and "номер" in text:
            score += 35
        if "cadastral" in text:
            score += 40
        if "cad" in text:
            score += 25
        if text in {"cn", "cadnum", "cadnumber", "cadnum"}:
            score += 35
        return score

    def _purpose_field_score(self, value):
        text = self._normalize(value)
        score = 0
        for token, weight in (
            ("назнач", 60),
            ("категор", 50),
            ("видиспольз", 50),
            ("разрешен", 35),
            ("собствен", 35),
            ("владел", 30),
            ("тип", 20),
            ("purpose", 45),
            ("category", 40),
            ("owner", 30),
            ("type", 15),
        ):
            if token in text:
                score += weight
        return score

    def _normalize(self, value):
        return re.sub(
            r"[^0-9a-zа-я]+", "",
            str(value or "").strip().lower().replace("ё", "е"),
        )

    def _commit(self, layer, message):
        if not layer.commitChanges():
            errors = "\n".join(layer.commitErrors())
            layer.rollBack()
            raise Exception(message + ("\n" + errors if errors else ""))
