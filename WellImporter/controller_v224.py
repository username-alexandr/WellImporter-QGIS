# -*- coding: utf-8 -*-

from qgis.core import QgsProject

from .controller import ImportController
from .parcel_group_manager_v224 import ParcelGroupManagerV224
from .settings import PluginSettings
from .spatial_circle_repair import SpatialCircleRepairManager


class ImportControllerV224(ImportController):
    """Контроллер 2.2.4 с групповой системой земельных участков."""

    def __init__(self, iface):
        super().__init__(iface)
        # Сохраняем runtime-исправление 2.2.2 независимо от старой цепочки UI.
        self.circle_repair = SpatialCircleRepairManager()
        self.parcels = ParcelGroupManagerV224(self.project)
        self.settings_v224 = PluginSettings()
        self._field_parcel_selection_layer_id = ""

    def parcel_group_path(self):
        return self.settings_v224.parcel_group_path().strip()

    def set_parcel_group_path(self, group_path):
        self.settings_v224.set_parcel_group_path(group_path)

    def _require_parcel_group(self):
        group_path = self.parcel_group_path()
        if not group_path:
            raise Exception(
                "Не выбрана группа земельных участков. Откройте Центр управления → "
                "Земельные участки, выберите группу и сохраните выбор."
            )
        return group_path

    def detect_parcel_source(self, polygon_layer_id=None, require_cadastral=False):
        """Проверяет выбранную группу вместо выбора одного глобального слоя."""
        group_path = self._require_parcel_group()
        excluded = [polygon_layer_id] if polygon_layer_id else []
        report = self.parcels.describe_group(group_path, excluded)
        if require_cadastral and report.get("cadastral_layers", 0) <= 0:
            raise Exception(
                f"В группе «{group_path}» не найдено ни одного поля кадастрового номера."
            )
        return {
            "group_path": group_path,
            "layer_id": "",
            "layer_name": group_path,
            "label_field": "определяется отдельно для каждого слоя",
            "cadastral_field": "определяется отдельно для каждого слоя",
            "score": report.get("layer_count", 0),
            "layers": report.get("layers", []),
            "layer_count": report.get("layer_count", 0),
            "cadastral_layers": report.get("cadastral_layers", 0),
            "purpose_layers": report.get("purpose_layers", 0),
        }

    def assign_parcel_names_auto(self, point_layer_id, polygon_layer_id=None, selected_only=False):
        point_layer = self.layer_by_id(point_layer_id)
        group_path = self._require_parcel_group()
        excluded = [polygon_layer_id] if polygon_layer_id else []
        result = self.parcels.assign_group(
            point_layer,
            group_path,
            excluded_layer_ids=excluded,
            selected_only=selected_only,
            include_cadastral=False,
        )
        self._refresh_layer(point_layer)
        self.iface.mapCanvas().refresh()
        self.logger.write(
            f"Определение участков по группе «{group_path}»: найдено {result.get('found', 0)}, "
            f"конфликтов {result.get('conflict_count', 0)}"
        )
        return result

    def assign_parcels_auto(self, point_layer_id, polygon_layer_id=None, selected_only=False):
        """Определяет участок/кадастр/назначение по всем слоям выбранной группы."""
        point_layer = self.layer_by_id(point_layer_id)
        group_path = self._require_parcel_group()
        excluded = [polygon_layer_id] if polygon_layer_id else []
        result = self.parcels.assign_group(
            point_layer,
            group_path,
            excluded_layer_ids=excluded,
            selected_only=selected_only,
            include_cadastral=True,
        )
        self._refresh_layer(point_layer)
        self.iface.mapCanvas().refresh()
        self.logger.write(
            f"Участки/кадастр по группе «{group_path}»: найдено {result.get('found', 0)}, "
            f"кадастровых {result.get('cadastral_found', 0)}, "
            f"конфликтов {result.get('conflict_count', 0)}"
        )
        return result

    def create_field_parcel_selection_layer(self, point_layer_id, polygon_layer_id=None):
        """Создаёт временный объединённый слой участков выбранной группы для мастера выезда."""
        self.cleanup_field_parcel_selection_layer()
        point_layer = self.layer_by_id(point_layer_id)
        group_path = self._require_parcel_group()
        excluded = [polygon_layer_id] if polygon_layer_id else []
        layer = self.parcels.create_selection_layer(point_layer, group_path, excluded)
        QgsProject.instance().addMapLayer(layer)
        self._field_parcel_selection_layer_id = layer.id()
        return layer

    def field_parcel_selection_layer(self):
        if not self._field_parcel_selection_layer_id:
            return None
        return QgsProject.instance().mapLayer(self._field_parcel_selection_layer_id)

    def cleanup_field_parcel_selection_layer(self):
        layer_id = str(self._field_parcel_selection_layer_id or "")
        self._field_parcel_selection_layer_id = ""
        if layer_id and QgsProject.instance().mapLayer(layer_id) is not None:
            QgsProject.instance().removeMapLayer(layer_id)

    def prepare_field_scope(self, point_layer_id, polygon_layer_id, mode):
        """Подготавливает выезд по выбранной группе и объединённому слою участков."""
        point_layer = self.layer_by_id(point_layer_id)
        parcel_layer = self.field_parcel_selection_layer()
        if str(mode) == self.field_scope.MODE_SELECTED_PARCELS and parcel_layer is None:
            parcel_layer = self.create_field_parcel_selection_layer(point_layer_id, polygon_layer_id)

        scope = self.field_scope.prepare(mode, point_layer, parcel_layer)
        cadastral = self.assign_parcels_auto(
            point_layer_id,
            polygon_layer_id,
            selected_only=bool(scope.get("selected_only")),
        )
        self._refresh_layer(point_layer)
        self.iface.mapCanvas().refresh()
        self.logger.write(
            f"Территория выезда по группе «{self.parcel_group_path()}»: режим {scope.get('mode')}, "
            f"скважин {scope.get('selected_wells', 0)}, "
            f"кадастровых номеров {cadastral.get('cadastral_found', 0)}"
        )
        return {
            "scope": scope,
            "cadastral": cadastral,
            "parcel_group_path": self.parcel_group_path(),
            "parcel_layer_id": parcel_layer.id() if parcel_layer is not None else "",
            "parcel_layer_name": parcel_layer.name() if parcel_layer is not None else self.parcel_group_path(),
        }
