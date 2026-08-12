# -*- coding: utf-8 -*-

import json
from pathlib import Path

from qgis.PyQt import QtCore, QtNetwork
from qgis.PyQt.QtCore import QSettings, QUrl
from qgis.core import (
    Qgis,
    QgsApplication,
    QgsNetworkAccessManager,
    QgsProject,
    QgsRasterLayer,
)


class BasemapCatalog:
    """Каталог фоновых карт, избранное, быстрое переключение и офлайн-кэш.

    Встроенные публичные XYZ-сервисы по умолчанию не разрешены для массового
    скачивания. Пользователь может включить офлайн-кэш только после того, как
    подтвердит наличие права/разрешения на такой способ использования источника.
    Это предотвращает неосознанное нарушение tile usage policy провайдера.
    """

    GROUP = "WellImporter/Basemaps"
    BASEMAP_PROPERTY = "WellImporter/basemap"

    BUILTINS = {
        "OpenStreetMap": {
            "url": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
            "sample_url": "https://tile.openstreetmap.org/0/0/0.png",
            "max_zoom": 19,
            "attribution": "© OpenStreetMap contributors",
            "bulk_cache_default": False,
        },
        "Esri World Imagery": {
            "url": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
            "sample_url": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/0/0/0",
            "max_zoom": 19,
            "attribution": "Esri World Imagery",
            "bulk_cache_default": False,
        },
        "OpenTopoMap": {
            "url": "https://tile.opentopomap.org/{z}/{x}/{y}.png",
            "sample_url": "https://tile.opentopomap.org/0/0/0.png",
            "max_zoom": 17,
            "attribution": "© OpenStreetMap contributors, SRTM | OpenTopoMap",
            "bulk_cache_default": False,
        },
    }

    def __init__(self, iface=None):
        self.iface = iface
        self.project = QgsProject.instance()
        self.settings = QSettings()

    def names(self):
        return list(self.BUILTINS.keys())

    def definition(self, name):
        if name not in self.BUILTINS:
            raise Exception(f"Фоновая карта «{name}» отсутствует в каталоге.")
        result = dict(self.BUILTINS[name])
        result["name"] = name
        result["favorite"] = name in self.favorites()
        result["offline_allowed"] = self.offline_allowed(name)
        return result

    def favorites(self):
        raw = self.settings.value(f"{self.GROUP}/favorites", "[]")
        try:
            values = json.loads(str(raw))
        except Exception:
            values = []
        return [name for name in values if name in self.BUILTINS]

    def set_favorite(self, name, favorite=True):
        self.definition(name)
        values = self.favorites()
        if favorite and name not in values:
            values.append(name)
        elif not favorite and name in values:
            values.remove(name)
        self.settings.setValue(f"{self.GROUP}/favorites", json.dumps(values, ensure_ascii=False))
        return values

    def offline_allowed(self, name):
        definition = self.BUILTINS[name]
        key = f"{self.GROUP}/offline_allowed/{name}"
        default = bool(definition.get("bulk_cache_default", False))
        value = self.settings.value(key, default)
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "yes"}

    def set_offline_allowed(self, name, allowed):
        self.definition(name)
        self.settings.setValue(f"{self.GROUP}/offline_allowed/{name}", bool(allowed))

    def switch(self, name):
        """Подключает выбранную XYZ-карту и скрывает предыдущую карту каталога."""
        definition = self.definition(name)
        target = None
        for layer in self.project.mapLayers().values():
            if str(layer.customProperty(self.BASEMAP_PROPERTY, "")) == name:
                target = layer
                break

        if target is None:
            # QGIS WMS provider принимает type=xyz и шаблон URL.
            source = (
                "type=xyz"
                f"&url={definition['url']}"
                f"&zmax={int(definition['max_zoom'])}"
                "&zmin=0"
            )
            target = QgsRasterLayer(source, name, "wms")
            if not target.isValid():
                raise Exception(f"QGIS не смог подключить фоновую карту «{name}».")
            target.setCustomProperty(self.BASEMAP_PROPERTY, name)
            target.setCustomProperty("WellImporter/attribution", definition.get("attribution", ""))
            self.project.addMapLayer(target, False)
            self.project.layerTreeRoot().insertLayer(0, target)

        root = self.project.layerTreeRoot()
        for layer in self.project.mapLayers().values():
            catalog_name = str(layer.customProperty(self.BASEMAP_PROPERTY, ""))
            if not catalog_name:
                continue
            node = root.findLayer(layer.id())
            if node is not None:
                node.setItemVisibilityChecked(layer.id() == target.id())

        self.settings.setValue(f"{self.GROUP}/last", name)
        if self.iface is not None:
            self.iface.mapCanvas().refresh()
        return target

    def next_basemap(self):
        """Переключает фон одной командой; сначала перебирается избранное."""
        order = self.favorites() or self.names()
        current = str(self.settings.value(f"{self.GROUP}/last", ""))
        try:
            index = order.index(current)
            name = order[(index + 1) % len(order)]
        except Exception:
            name = order[0]
        return self.switch(name)

    def check_availability(self, name, timeout_ms=4500):
        definition = self.definition(name)
        return self._request(definition["sample_url"], timeout_ms)

    def availability_all(self, timeout_ms=4500):
        return [
            dict(self.definition(name), **self.check_availability(name, timeout_ms))
            for name in self.names()
        ]

    def cache_current_extent(self, name, output_path, min_zoom=10, max_zoom=17):
        """Создаёт MBTiles текущего охвата, если пользователь разрешил офлайн-кэш.

        Для совместимости с разными QGIS определяется доступный алгоритм
        ``Generate XYZ tiles (MBTiles)`` динамически. На время рендера видимой
        остаётся только выбранная фоновая карта; исходная видимость слоёв
        восстанавливается даже при ошибке.
        """
        if self.iface is None:
            raise Exception("Офлайн-кэш доступен только из запущенного интерфейса QGIS.")
        if not self.offline_allowed(name):
            raise Exception(
                "Массовый офлайн-кэш для этого публичного источника по умолчанию отключён. "
                "Включите его только если условия провайдера или ваша лицензия разрешают загрузку тайлов."
            )

        layer = self.switch(name)
        output = Path(output_path)
        if output.suffix.lower() != ".mbtiles":
            output = output.with_suffix(".mbtiles")
        output.parent.mkdir(parents=True, exist_ok=True)

        registry = QgsApplication.processingRegistry()
        algorithm_id = None
        for candidate in ("native:tilesxyzmbtiles", "qgis:tilesxyzmbtiles"):
            if registry.algorithmById(candidate) is not None:
                algorithm_id = candidate
                break
        if algorithm_id is None:
            raise Exception(
                "В этой установке QGIS не найден алгоритм «Generate XYZ tiles (MBTiles)»."
            )

        import processing

        root = self.project.layerTreeRoot()
        visibility = {}
        for project_layer in self.project.mapLayers().values():
            node = root.findLayer(project_layer.id())
            if node is not None:
                visibility[project_layer.id()] = node.isVisible()
                node.setItemVisibilityChecked(project_layer.id() == layer.id())

        try:
            extent = self.iface.mapCanvas().extent()
            params = {
                "EXTENT": extent,
                "ZOOM_MIN": int(min_zoom),
                "ZOOM_MAX": min(int(max_zoom), int(self.definition(name)["max_zoom"])),
                "DPI": 96,
                "BACKGROUND_COLOR": QtCore.Qt.transparent,
                "TILE_FORMAT": 0,
                "QUALITY": 85,
                "METATILESIZE": 4,
                "OUTPUT_FILE": str(output),
            }
            result = processing.run(algorithm_id, params)
        finally:
            for layer_id, visible in visibility.items():
                node = root.findLayer(layer_id)
                if node is not None:
                    node.setItemVisibilityChecked(bool(visible))
            self.iface.mapCanvas().refresh()

        self.settings.setValue(f"{self.GROUP}/last_cache_path", str(output))
        self.settings.setValue(f"{self.GROUP}/last_cache_name", name)
        return {
            "name": name,
            "path": str(output),
            "min_zoom": int(min_zoom),
            "max_zoom": int(max_zoom),
            "algorithm": algorithm_id,
            "result": result,
        }

    def last_cache(self):
        """Возвращает последний созданный MBTiles, если файл ещё существует."""
        path = Path(str(self.settings.value(f"{self.GROUP}/last_cache_path", "") or ""))
        if not str(path) or not path.is_file():
            return None
        return {
            "name": str(self.settings.value(f"{self.GROUP}/last_cache_name", "") or ""),
            "path": str(path),
        }

    def _request(self, url, timeout_ms):
        manager = QgsNetworkAccessManager.instance()
        request = QtNetwork.QNetworkRequest(QUrl(url))
        reply = manager.get(request)
        loop = QtCore.QEventLoop()
        timer = QtCore.QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(loop.quit)
        reply.finished.connect(loop.quit)
        timer.start(int(timeout_ms))
        loop.exec_()

        timed_out = not reply.isFinished()
        if timed_out:
            reply.abort()
        status = reply.attribute(QtNetwork.QNetworkRequest.HttpStatusCodeAttribute)
        error = reply.error()
        message = reply.errorString() if error != QtNetwork.QNetworkReply.NoError else ""
        reply.deleteLater()
        return {
            "available": bool(not timed_out and error == QtNetwork.QNetworkReply.NoError),
            "http_status": int(status or 0),
            "timed_out": bool(timed_out),
            "error": message,
        }
