# -*- coding: utf-8 -*-

import json
import tempfile
import zipfile
from pathlib import Path

from qgis.PyQt import QtCore, QtWidgets
from qgis.core import (
    QgsCoordinateTransform,
    QgsFeature,
    QgsGeometry,
    QgsProject,
    QgsVectorLayer,
)

from .well_number_field import feature_well_number, well_number_field_name


class FieldSyncManager:
    """Сравнивает офисную и выездную версии относительно baseline из пакета."""

    MANIFEST_NAME = "WellImporter_SYNC_BASELINE.json"
    POINT_LAYER_NAME = "Скважины"
    CIRCLE_LAYER_NAME = "Площадные_круги"

    def __init__(self, project=None):
        self.project = project or QgsProject.instance()

    def build_baseline(self, point_layer, polygon_layer, selected_only=False):
        point_features = (
            list(point_layer.getSelectedFeatures())
            if selected_only else list(point_layer.getFeatures())
        )
        if selected_only:
            numbers = {
                feature_well_number(feature, point_layer, "").strip()
                for feature in point_features
            }
            circle_features = [
                feature for feature in polygon_layer.getFeatures()
                if feature_well_number(feature, polygon_layer, "").strip() in numbers
            ]
        else:
            circle_features = list(polygon_layer.getFeatures())

        return {
            "format": 1,
            "points": self._snapshot(point_layer, point_features),
            "circles": self._snapshot(polygon_layer, circle_features),
        }

    def write_baseline(self, path, baseline):
        Path(path).write_text(
            json.dumps(baseline, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return str(path)

    def compare_package(self, package_path, office_point_layer, office_polygon_layer):
        """Показывает только объекты, реально изменённые в выездной версии."""
        with self._open_package(package_path) as package:
            baseline_path = package["root"] / self.MANIFEST_NAME
            if not baseline_path.exists():
                raise Exception(
                    "В выездном пакете отсутствует baseline синхронизации. "
                    "Пакет должен быть создан текущей версией Well Importer."
                )
            baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
            field_points = self._load_field_layer(package["gpkg"], self.POINT_LAYER_NAME)
            field_circles = self._load_field_layer(package["gpkg"], self.CIRCLE_LAYER_NAME)

            field = {
                "points": self._snapshot(field_points),
                "circles": self._snapshot(field_circles),
            }
            office = {
                "points": self._snapshot(office_point_layer),
                "circles": self._snapshot(office_polygon_layer),
            }

        changes = []
        for layer_key, title in (("points", "Скважины"), ("circles", "Площадные круги")):
            base_items = baseline.get(layer_key, {})
            field_items = field.get(layer_key, {})
            office_items = office.get(layer_key, {})
            keys = set(base_items) | set(field_items)
            for number in sorted(keys, key=self._number_sort_key):
                base_value = base_items.get(number)
                field_value = field_items.get(number)
                if field_value == base_value:
                    continue

                office_value = office_items.get(number)
                if base_value is None and field_value is not None:
                    change_type = "Добавлен на выезде"
                elif base_value is not None and field_value is None:
                    change_type = "Удалён на выезде"
                else:
                    change_type = "Изменён на выезде"

                office_changed = office_value != base_value
                conflict = bool(office_changed and office_value != field_value)
                changes.append({
                    "layer_key": layer_key,
                    "layer_title": title,
                    "number": number,
                    "change_type": change_type,
                    "conflict": conflict,
                    "office_changed": office_changed,
                    "baseline": base_value,
                    "field": field_value,
                    "office": office_value,
                })

        return {
            "changes": changes,
            "changed": len(changes),
            "conflicts": sum(1 for item in changes if item["conflict"]),
            "package_path": str(package_path),
        }

    def apply_changes(self, package_path, office_point_layer, office_polygon_layer, changes):
        """Применяет только подтверждённые пользователем изменения."""
        changes = list(changes or [])
        if not changes:
            return {"applied": 0, "deleted": 0, "added": 0, "modified": 0}

        layers = {"points": office_point_layer, "circles": office_polygon_layer}
        started_here = {}
        for key, layer in layers.items():
            started_here[key] = not layer.isEditable()
            if started_here[key] and not layer.startEditing():
                raise Exception(f"Не удалось включить редактирование слоя «{layer.name()}».")

        counters = {"applied": 0, "deleted": 0, "added": 0, "modified": 0}
        try:
            with self._open_package(package_path) as package:
                field_layers = {
                    "points": self._load_field_layer(package["gpkg"], self.POINT_LAYER_NAME),
                    "circles": self._load_field_layer(package["gpkg"], self.CIRCLE_LAYER_NAME),
                }
                for change in changes:
                    key = change["layer_key"]
                    number = str(change["number"])
                    office_layer = layers[key]
                    field_layer = field_layers[key]
                    office_feature = self._find_by_number(office_layer, number)
                    field_feature = self._find_by_number(field_layer, number)

                    if field_feature is None:
                        if office_feature is not None:
                            if not office_layer.deleteFeature(office_feature.id()):
                                raise Exception(f"Не удалось удалить объект №{number}.")
                            counters["deleted"] += 1
                            counters["applied"] += 1
                        continue

                    if office_feature is None:
                        feature = QgsFeature(office_layer.fields())
                        self._copy_feature(field_layer, field_feature, office_layer, feature)
                        if not office_layer.addFeature(feature):
                            raise Exception(f"Не удалось добавить объект №{number}.")
                        counters["added"] += 1
                        counters["applied"] += 1
                    else:
                        self._update_feature(field_layer, field_feature, office_layer, office_feature)
                        counters["modified"] += 1
                        counters["applied"] += 1

            for key, layer in layers.items():
                if started_here[key]:
                    if not layer.commitChanges():
                        errors = "\n".join(layer.commitErrors())
                        layer.rollBack()
                        raise Exception(f"Не удалось сохранить синхронизацию слоя «{layer.name()}».\n{errors}")
                layer.updateExtents()
                layer.triggerRepaint()
        except Exception:
            for key, layer in layers.items():
                if started_here.get(key) and layer.isEditable():
                    layer.rollBack()
            raise

        counters["left_uncommitted"] = [
            layers[key].name() for key, started in started_here.items() if not started
        ]
        return counters

    def _snapshot(self, layer, features=None):
        features = list(features) if features is not None else list(layer.getFeatures())
        field_names = [field.name() for field in layer.fields()]
        result = {}
        for feature in features:
            number = feature_well_number(feature, layer, "").strip()
            if not number:
                continue
            attrs = {
                name: self._json_value(feature[name])
                for name in field_names
                if name not in {"fid", "FID"}
            }
            geometry = ""
            if feature.hasGeometry() and not feature.geometry().isEmpty():
                geometry = bytes(feature.geometry().asWkb()).hex()
            result[number] = {"attributes": attrs, "geometry_wkb": geometry}
        return result

    def _json_value(self, value):
        if value is None:
            return None
        if isinstance(value, (str, int, float, bool)):
            return value
        return str(value)

    def _find_by_number(self, layer, number):
        for feature in layer.getFeatures():
            if feature_well_number(feature, layer, "").strip() == number:
                return feature
        return None

    def _copy_feature(self, source_layer, source_feature, target_layer, target_feature):
        geometry = QgsGeometry(source_feature.geometry())
        if source_layer.crs() != target_layer.crs():
            geometry.transform(QgsCoordinateTransform(
                source_layer.crs(), target_layer.crs(), self.project
            ))
        target_feature.setGeometry(geometry)
        source_fields = set(source_layer.fields().names())
        for index, field in enumerate(target_layer.fields()):
            if field.name() in source_fields:
                target_feature[index] = source_feature[field.name()]

    def _update_feature(self, source_layer, source_feature, target_layer, target_feature):
        geometry = QgsGeometry(source_feature.geometry())
        if source_layer.crs() != target_layer.crs():
            geometry.transform(QgsCoordinateTransform(
                source_layer.crs(), target_layer.crs(), self.project
            ))
        if not target_layer.changeGeometry(target_feature.id(), geometry):
            raise Exception("Не удалось обновить геометрию при обратной синхронизации.")
        source_fields = set(source_layer.fields().names())
        for index, field in enumerate(target_layer.fields()):
            if field.name() not in source_fields:
                continue
            target_layer.changeAttributeValue(
                target_feature.id(), index, source_feature[field.name()]
            )

    def _load_field_layer(self, gpkg_path, layer_name):
        layer = QgsVectorLayer(
            f"{gpkg_path}|layername={layer_name}", layer_name, "ogr"
        )
        if not layer.isValid():
            raise Exception(f"В выездном пакете не найден слой «{layer_name}».")
        return layer

    def _open_package(self, package_path):
        return _PackageContext(package_path)

    def _number_sort_key(self, value):
        text = str(value)
        return (0, int(text), text) if text.isdigit() else (1, 0, text.casefold())


class _PackageContext:
    def __init__(self, package_path):
        self.package_path = Path(package_path)
        self.temp = None
        self.root = None
        self.gpkg = None

    def __enter__(self):
        if not self.package_path.exists():
            raise Exception(f"Файл выездного пакета не найден: {self.package_path}")
        if self.package_path.suffix.lower() == ".zip":
            self.temp = tempfile.TemporaryDirectory(prefix="wellimporter_sync_")
            self.root = Path(self.temp.name)
            with zipfile.ZipFile(self.package_path, "r") as archive:
                archive.extractall(self.root)
            gpkg_files = list(self.root.rglob("*.gpkg"))
            if not gpkg_files:
                raise Exception("В ZIP-пакете не найден GeoPackage.")
            self.gpkg = gpkg_files[0]
        else:
            self.root = self.package_path.parent
            self.gpkg = self.package_path
        return {"root": self.root, "gpkg": self.gpkg}

    def __exit__(self, exc_type, exc, tb):
        if self.temp is not None:
            self.temp.cleanup()


class FieldSyncDialog(QtWidgets.QDialog):
    """Показывает только изменённые на выезде объекты и просит подтверждение."""

    def __init__(self, comparison, parent=None):
        super().__init__(parent)
        self.comparison = comparison or {}
        self.setWindowTitle("Обратная синхронизация — офисная / выездная версия")
        self.resize(900, 560)
        self._build_ui()

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        changes = self.comparison.get("changes", [])
        info = QtWidgets.QLabel(
            f"Изменено на выезде: <b>{len(changes)}</b>; "
            f"конфликтов с офисной версией: <b>{self.comparison.get('conflicts', 0)}</b>. "
            "В списке отсутствуют неизменённые объекты."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        self.table = QtWidgets.QTableWidget(len(changes), 6)
        self.table.setHorizontalHeaderLabels([
            "Применить", "Слой", "Номер", "Изменение", "Конфликт", "Офис изменён после выезда",
        ])
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        for row, change in enumerate(changes):
            check = QtWidgets.QTableWidgetItem()
            check.setFlags(check.flags() | QtCore.Qt.ItemIsUserCheckable | QtCore.Qt.ItemIsEnabled)
            check.setCheckState(QtCore.Qt.Unchecked if change.get("conflict") else QtCore.Qt.Checked)
            check.setData(QtCore.Qt.UserRole, dict(change))
            self.table.setItem(row, 0, check)
            values = [
                change.get("layer_title", ""),
                change.get("number", ""),
                change.get("change_type", ""),
                "ДА — требуется решение" if change.get("conflict") else "нет",
                "да" if change.get("office_changed") else "нет",
            ]
            for column, value in enumerate(values, start=1):
                self.table.setItem(row, column, QtWidgets.QTableWidgetItem(str(value)))
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QtWidgets.QHeaderView.Stretch)
        header.setSectionResizeMode(4, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QtWidgets.QHeaderView.ResizeToContents)
        layout.addWidget(self.table, 1)

        selection = QtWidgets.QHBoxLayout()
        btnAll = QtWidgets.QPushButton("Подтвердить все")
        btnNone = QtWidgets.QPushButton("Снять все")
        btnAll.clicked.connect(lambda: self._set_all(True))
        btnNone.clicked.connect(lambda: self._set_all(False))
        selection.addWidget(btnAll)
        selection.addWidget(btnNone)
        selection.addStretch(1)
        layout.addLayout(selection)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        buttons.button(QtWidgets.QDialogButtonBox.Ok).setText("Применить выбранные изменения")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _set_all(self, checked):
        state = QtCore.Qt.Checked if checked else QtCore.Qt.Unchecked
        for row in range(self.table.rowCount()):
            self.table.item(row, 0).setCheckState(state)

    def selected_changes(self):
        result = []
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item.checkState() == QtCore.Qt.Checked:
                value = item.data(QtCore.Qt.UserRole)
                if isinstance(value, dict):
                    result.append(dict(value))
        return result
