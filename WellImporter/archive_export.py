# -*- coding: utf-8 -*-

from datetime import datetime
from pathlib import Path

from qgis.core import (
    Qgis,
    QgsFeature,
    QgsGeometry,
    QgsMapLayerStyle,
    QgsProject,
    QgsVectorFileWriter,
    QgsVectorLayer,
    QgsWkbTypes,
)

from .severity import Severity
from .well_number_field import well_number_field_name


class ArchiveExportManager:
    """Архивирование партий и подготовка переносимого выездного комплекта."""

    BATCH_FIELD = "WI_BATCH"
    NUMBER_FIELD = "Номер скважины"

    def __init__(self):
        self.project = QgsProject.instance()

    def archive_batches(self, point_layer, polygon_layer, batch_ids, gpkg_path):
        """Архивирует выбранные партии и удаляет их только после успешной записи."""
        batch_ids = {str(value) for value in batch_ids if value}
        if not batch_ids:
            raise Exception("Не выбраны партии для архивирования.")

        self._require_field(point_layer, self.BATCH_FIELD)
        self._require_field(polygon_layer, self.BATCH_FIELD)
        point_features = [f for f in point_layer.getFeatures() if str(f[self.BATCH_FIELD]) in batch_ids]
        polygon_features = [f for f in polygon_layer.getFeatures() if str(f[self.BATCH_FIELD]) in batch_ids]
        if not point_features and not polygon_features:
            raise Exception("В рабочих слоях не найдены объекты выбранных партий.")

        gpkg_path = self._normalize_gpkg_path(gpkg_path)
        point_subset = self._memory_subset(point_layer, point_features, "Скважины_архив")
        polygon_subset = self._memory_subset(polygon_layer, polygon_features, "Площадные_круги_архив")
        self._write_two_layers(point_subset, polygon_subset, gpkg_path, "Скважины_архив", "Площадные_круги_архив")

        point_deleted = self._delete_features(point_layer, [f.id() for f in point_features])
        polygon_deleted = self._delete_features(polygon_layer, [f.id() for f in polygon_features])
        return {
            "archive_path": str(gpkg_path),
            "batch_ids": sorted(batch_ids),
            "points": point_deleted,
            "circles": polygon_deleted,
        }

    def analyze_field_package(self, point_layer, polygon_layer):
        """Выполняет предварительный аудит перед созданием выездного пакета."""
        checks = []

        def add(severity, title, message):
            checks.append({"severity": severity, "title": title, "message": message})

        if not point_layer.isValid() or not polygon_layer.isValid():
            add(Severity.CRITICAL, "Доступность слоёв", "Один из выбранных слоёв недействителен.")
        else:
            add(Severity.INFO, "Доступность слоёв", "Оба выбранных слоя доступны.")

        if not point_layer.crs().isValid() or not polygon_layer.crs().isValid():
            add(Severity.CRITICAL, "Системы координат", "У одного из слоёв отсутствует корректная CRS.")
        else:
            add(Severity.INFO, "Системы координат", f"Точки: {point_layer.crs().authid()}; круги: {polygon_layer.crs().authid()}.")

        if point_layer.isEditable() or polygon_layer.isEditable():
            add(Severity.ERROR, "Несохранённые изменения", "Один из слоёв находится в режиме редактирования. Перед выездным экспортом рекомендуется сохранить правки.")
        else:
            add(Severity.INFO, "Несохранённые изменения", "Слои не находятся в режиме редактирования.")

        project_file = self.project.fileName()
        if project_file:
            add(Severity.INFO, "Файл проекта", f"Рабочий проект сохранён: {Path(project_file).name}.")
        else:
            add(Severity.WARNING, "Файл проекта", "Текущий QGIS-проект ещё не сохранён. Выездной проект всё равно будет создан, но рекомендуется сохранить рабочий проект.")

        point_number_field = self._number_field(point_layer)
        polygon_number_field = self._number_field(polygon_layer)
        if not point_number_field or not polygon_number_field:
            add(Severity.ERROR, "Связь точек и кругов", "Не найдено единое поле «Номер скважины» в одном из слоёв. Экспорт выделенных скважин может быть неполным.")
        else:
            point_numbers = {str(f[point_number_field]).strip() for f in point_layer.getFeatures() if str(f[point_number_field]).strip()}
            polygon_numbers = {str(f[polygon_number_field]).strip() for f in polygon_layer.getFeatures() if str(f[polygon_number_field]).strip()}
            missing_circles = point_numbers - polygon_numbers
            orphan_circles = polygon_numbers - point_numbers
            if missing_circles or orphan_circles:
                severity = Severity.ERROR if missing_circles else Severity.WARNING
                add(
                    severity,
                    "Связь точек и кругов",
                    f"Скважин без круга: {len(missing_circles)}; кругов без скважины: {len(orphan_circles)}."
                )
            else:
                add(Severity.INFO, "Связь точек и кругов", "Для всех номеров найдены парные объекты.")

        empty_points = sum(1 for f in point_layer.getFeatures() if f.geometry() is None or f.geometry().isEmpty())
        empty_polygons = sum(1 for f in polygon_layer.getFeatures() if f.geometry() is None or f.geometry().isEmpty())
        invalid_polygons = 0
        for feature in polygon_layer.getFeatures():
            geometry = feature.geometry()
            if geometry is not None and not geometry.isEmpty():
                try:
                    if not geometry.isGeosValid():
                        invalid_polygons += 1
                except Exception:
                    pass
        if empty_points or empty_polygons:
            add(Severity.CRITICAL, "Геометрия", f"Пустых точек: {empty_points}; пустых кругов: {empty_polygons}.")
        elif invalid_polygons:
            add(Severity.ERROR, "Геометрия", f"Некорректных полигональных геометрий: {invalid_polygons}.")
        else:
            add(Severity.INFO, "Геометрия", "Пустые или явно некорректные геометрии не обнаружены.")

        selected_count = int(point_layer.selectedFeatureCount())
        add(Severity.INFO, "Выделение", f"Сейчас выделено скважин: {selected_count}.")

        style_notes = []
        if point_layer.renderer() is None:
            style_notes.append("у слоя скважин отсутствует рендерер")
        if polygon_layer.renderer() is None:
            style_notes.append("у слоя кругов отсутствует рендерер")
        if style_notes:
            add(Severity.WARNING, "Оформление", "; ".join(style_notes) + ".")
        else:
            labels = []
            try:
                if point_layer.labelsEnabled():
                    labels.append("подписи скважин включены")
                if polygon_layer.labelsEnabled():
                    labels.append("подписи кругов включены")
            except Exception:
                pass
            add(Severity.INFO, "Оформление", "Стили слоёв доступны для переноса" + ("; " + ", ".join(labels) if labels else "") + ".")

        other_layers = max(0, len(self.project.mapLayers()) - 2)
        if other_layers:
            add(Severity.WARNING, "Состав проекта", f"В текущем проекте есть ещё {other_layers} слой(ёв). В выездной GeoPackage попадут только выбранные скважины и площадные круги.")
        else:
            add(Severity.INFO, "Состав проекта", "Дополнительных слоёв, не входящих в пакет, не обнаружено.")

        counts = Severity.counts(item["severity"] for item in checks)
        highest = Severity.max(*(item["severity"] for item in checks)) if checks else Severity.INFO
        return {
            "checks": checks,
            "severity_counts": counts,
            "highest_severity": highest,
            "selected_count": selected_count,
        }

    def export_field_package(self, point_layer, polygon_layer, gpkg_path, selected_only=False,
                             store_styles=True, create_project=True, relative_paths=True,
                             include_readme=True, preparation_report=None):
        """Создаёт GeoPackage, встроенные стили, QGIS-проект и памятку."""
        gpkg_path = self._normalize_gpkg_path(gpkg_path)

        if selected_only:
            point_features = list(point_layer.getSelectedFeatures())
            if not point_features:
                raise Exception("В точечном слое нет выделенных скважин.")
            numbers = self._feature_numbers(point_layer, point_features)
            polygon_features = self._polygons_for_numbers(polygon_layer, numbers)
        else:
            point_features = list(point_layer.getFeatures())
            polygon_features = list(polygon_layer.getFeatures())

        if not point_features:
            raise Exception("В выбранном точечном слое нет объектов для экспорта.")

        point_subset = self._memory_subset(point_layer, point_features, "Скважины")
        polygon_subset = self._memory_subset(polygon_layer, polygon_features, "Площадные_круги")
        self._write_two_layers(point_subset, polygon_subset, gpkg_path, "Скважины", "Площадные_круги")

        style_result = {"stored": 0, "errors": []}
        if store_styles:
            style_result = self._store_styles_in_gpkg(gpkg_path, point_layer, polygon_layer)

        qgz_path = gpkg_path.with_suffix(".qgz")
        project_created = False
        if create_project:
            project_created = self._create_field_project(
                gpkg_path, qgz_path, point_layer, polygon_layer, relative_paths=relative_paths
            )

        info_path = gpkg_path.with_name(gpkg_path.stem + "_README.txt")
        if include_readme:
            self._write_field_info(
                info_path, gpkg_path, qgz_path if project_created else None,
                len(point_features), len(polygon_features), selected_only,
                style_result, preparation_report or {}
            )
        else:
            info_path = None

        return {
            "gpkg_path": str(gpkg_path),
            "project_path": str(qgz_path) if project_created else "",
            "info_path": str(info_path) if info_path else "",
            "points": len(point_features),
            "circles": len(polygon_features),
            "selected_only": bool(selected_only),
            "styles_stored": int(style_result.get("stored", 0)),
            "style_errors": list(style_result.get("errors", [])),
        }

    def _store_styles_in_gpkg(self, gpkg_path, point_source, polygon_source):
        """Сохраняет стили как стили по умолчанию непосредственно в GeoPackage."""
        mapping = [
            (point_source, "Скважины"),
            (polygon_source, "Площадные_круги"),
        ]
        stored = 0
        errors = []

        for source, layer_name in mapping:
            target = QgsVectorLayer(f"{gpkg_path}|layername={layer_name}", layer_name, "ogr")
            if not target.isValid():
                errors.append(f"{layer_name}: экспортированный слой не открылся для записи стиля")
                continue
            try:
                self._copy_style(source, target)
                result = target.saveStyleToDatabase(
                    "Well Importer — оформление",
                    "Оформление перенесено в выездной GeoPackage",
                    True,
                    "",
                )
                if isinstance(result, str) and result.strip():
                    errors.append(f"{layer_name}: {result.strip()}")
                else:
                    stored += 1
            except TypeError:
                try:
                    result = target.saveStyleToDatabase(
                        "Well Importer — оформление",
                        "Оформление перенесено в выездной GeoPackage",
                        True,
                    )
                    if isinstance(result, str) and result.strip():
                        errors.append(f"{layer_name}: {result.strip()}")
                    else:
                        stored += 1
                except Exception as exc:
                    errors.append(f"{layer_name}: {exc}")
            except Exception as exc:
                errors.append(f"{layer_name}: {exc}")
        return {"stored": stored, "errors": errors}

    def _feature_numbers(self, point_layer, point_features):
        field_name = self._number_field(point_layer)
        if not field_name:
            raise Exception("Не удалось определить номера скважин: отсутствует поле «Номер скважины».")
        return {str(feature[field_name]).strip() for feature in point_features}

    def _polygons_for_numbers(self, polygon_layer, numbers):
        field_name = self._number_field(polygon_layer)
        if not field_name:
            raise Exception("В слое площадных кругов отсутствует поле «Номер скважины».")
        return [feature for feature in polygon_layer.getFeatures() if str(feature[field_name]).strip() in numbers]

    def _number_field(self, layer):
        return well_number_field_name(layer)


    def _memory_subset(self, source_layer, features, name):
        geometry_name = QgsWkbTypes.displayString(source_layer.wkbType())
        memory_layer = QgsVectorLayer(geometry_name, name, "memory")
        if not memory_layer.isValid():
            raise Exception(f"Не удалось создать временный слой «{name}».")
        memory_layer.setCrs(source_layer.crs())
        provider = memory_layer.dataProvider()
        if not provider.addAttributes(list(source_layer.fields())):
            raise Exception(f"Не удалось скопировать поля слоя «{source_layer.name()}».")
        memory_layer.updateFields()

        copies = []
        for source_feature in features:
            feature = QgsFeature(memory_layer.fields())
            feature.setGeometry(QgsGeometry(source_feature.geometry()))
            feature.setAttributes(source_feature.attributes())
            copies.append(feature)
        if copies and not provider.addFeatures(copies):
            raise Exception(f"Не удалось подготовить объекты слоя «{source_layer.name()}» к экспорту.")
        memory_layer.updateExtents()
        return memory_layer

    def _write_two_layers(self, point_layer, polygon_layer, gpkg_path, point_name, polygon_name):
        gpkg_path.parent.mkdir(parents=True, exist_ok=True)
        if gpkg_path.exists():
            gpkg_path.unlink()
        self._write_layer(point_layer, gpkg_path, point_name, QgsVectorFileWriter.CreateOrOverwriteFile)
        self._write_layer(polygon_layer, gpkg_path, polygon_name, QgsVectorFileWriter.CreateOrOverwriteLayer)

    def _write_layer(self, layer, gpkg_path, layer_name, action):
        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = "GPKG"
        options.layerName = layer_name
        options.fileEncoding = "UTF-8"
        options.actionOnExistingFile = action
        result = QgsVectorFileWriter.writeAsVectorFormatV3(
            layer, str(gpkg_path), self.project.transformContext(), options
        )
        error_code = result[0] if isinstance(result, tuple) else result
        if error_code != QgsVectorFileWriter.NoError:
            error_message = ""
            if isinstance(result, tuple):
                for value in reversed(result[1:]):
                    if isinstance(value, str) and value:
                        error_message = value
                        break
            raise Exception(f"Не удалось записать слой «{layer_name}» в GeoPackage. Код: {error_code}. {error_message}")

    def _delete_features(self, layer, feature_ids):
        if not feature_ids:
            return 0
        if not layer.isEditable() and not layer.startEditing():
            raise Exception(f"Не удалось включить редактирование слоя «{layer.name()}».")
        for feature_id in feature_ids:
            if not layer.deleteFeature(feature_id):
                layer.rollBack()
                raise Exception(f"Не удалось удалить объект {feature_id} из слоя «{layer.name()}».")
        if not layer.commitChanges():
            errors = "\n".join(layer.commitErrors())
            layer.rollBack()
            raise Exception(f"Не удалось сохранить архивирование слоя «{layer.name()}».\n{errors}")
        layer.updateExtents()
        layer.triggerRepaint()
        return len(feature_ids)

    def _create_field_project(self, gpkg_path, qgz_path, point_source, polygon_source, relative_paths=True):
        project = QgsProject()
        try:
            project.setCrs(self.project.crs())
        except Exception:
            pass
        if relative_paths:
            try:
                project.setFilePathStorage(Qgis.FilePathType.Relative)
            except Exception:
                pass

        point_layer = QgsVectorLayer(f"{gpkg_path}|layername=Скважины", "Скважины", "ogr")
        polygon_layer = QgsVectorLayer(f"{gpkg_path}|layername=Площадные_круги", "Площадные круги", "ogr")
        if not point_layer.isValid() or not polygon_layer.isValid():
            return False

        # Даже если стиль уже записан в GeoPackage, дополнительно применяем его
        # к слоям проекта, чтобы проект выглядел одинаково сразу после открытия.
        self._copy_style(point_source, point_layer)
        self._copy_style(polygon_source, polygon_layer)
        project.addMapLayer(polygon_layer)
        project.addMapLayer(point_layer)
        return bool(project.write(str(qgz_path)))

    def _copy_style(self, source_layer, target_layer):
        """Копирует полный стиль слоя; при сбое использует поэлементный резервный путь."""
        try:
            style = QgsMapLayerStyle()
            style.readFromLayer(source_layer)
            style.writeToLayer(target_layer)
        except Exception:
            try:
                renderer = source_layer.renderer()
                if renderer is not None:
                    target_layer.setRenderer(renderer.clone())
            except Exception:
                pass
            try:
                labeling = source_layer.labeling()
                if labeling is not None:
                    target_layer.setLabeling(labeling.clone())
                    target_layer.setLabelsEnabled(source_layer.labelsEnabled())
            except Exception:
                pass
            try:
                target_layer.setOpacity(source_layer.opacity())
            except Exception:
                pass
        try:
            target_layer.triggerRepaint()
        except Exception:
            pass

    def _write_field_info(self, info_path, gpkg_path, qgz_path, points, circles, selected_only,
                          style_result, preparation_report):
        counts = (preparation_report or {}).get("severity_counts", {})
        lines = [
            "Well Importer — выездной пакет",
            "================================",
            f"Дата создания: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}",
            f"GeoPackage: {gpkg_path.name}",
            f"QGIS-проект: {qgz_path.name if qgz_path else 'не создан'}",
            f"Скважин: {points}",
            f"Площадных кругов: {circles}",
            f"Режим: {'только выделенные скважины' if selected_only else 'все объекты выбранных слоёв'}",
            f"Стилей сохранено внутри GeoPackage: {style_result.get('stored', 0)}",
            "",
            "Проверка готовности перед экспортом:",
            f"Критических: {counts.get(Severity.CRITICAL, 0)}",
            f"Ошибок: {counts.get(Severity.ERROR, 0)}",
            f"Предупреждений: {counts.get(Severity.WARNING, 0)}",
        ]
        checks = (preparation_report or {}).get("checks", [])
        if checks:
            lines.append("")
            lines.append("Детали проверки готовности:")
            for check in checks:
                lines.append(
                    f"- [{Severity.label(check.get('severity'))}] {check.get('title', '')}: {check.get('message', '')}"
                )
        if style_result.get("errors"):
            lines.append("")
            lines.append("Замечания при сохранении стилей:")
            lines.extend(f"- {item}" for item in style_result["errors"])
        lines += [
            "",
            "Для выезда рекомендуется копировать GeoPackage, QGIS-проект и README вместе.",
            "Внешние SVG-значки и нестандартные шрифты, используемые стилями, при необходимости перенесите отдельно.",
        ]
        info_path.write_text("\n".join(lines), encoding="utf-8")

    def _require_field(self, layer, field_name):
        if layer.fields().indexFromName(field_name) < 0:
            raise Exception(f"В слое «{layer.name()}» отсутствует поле {field_name}.")

    def _normalize_gpkg_path(self, path):
        result = Path(path)
        if result.suffix.lower() != ".gpkg":
            result = result.with_suffix(".gpkg")
        return result
