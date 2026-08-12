# -*- coding: utf-8 -*-

import json
import shutil
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from qgis.core import Qgis, QgsProject, QgsRasterLayer


class FieldPackageBuilder:
    """Создаёт один ZIP, содержащий все материалы для выезда."""

    MANIFEST_NAME = "WellImporter_FIELD_PACKAGE.json"

    def __init__(self, archive_export, web_exporter, sync_manager, preflight, basemaps):
        self.archive_export = archive_export
        self.web_exporter = web_exporter
        self.sync_manager = sync_manager
        self.preflight = preflight
        self.basemaps = basemaps

    def build(
        self,
        point_layer,
        polygon_layer,
        zip_path,
        selected_only=False,
        store_styles=True,
        create_project=True,
        relative_paths=True,
        include_readme=True,
        preparation_report=None,
    ):
        output = Path(zip_path)
        if output.suffix.lower() != ".zip":
            output = output.with_suffix(".zip")
        output.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory(prefix="wellimporter_field_") as temp_dir:
            root = Path(temp_dir)
            base_name = output.stem
            gpkg_path = root / f"{base_name}.gpkg"

            # Снимок создаётся до экспорта: он нужен для трёхстороннего
            # сравнения baseline / офис / выезд при обратной синхронизации.
            baseline = self.sync_manager.build_baseline(
                point_layer, polygon_layer, selected_only=selected_only
            )
            baseline_path = root / self.sync_manager.MANIFEST_NAME
            self.sync_manager.write_baseline(baseline_path, baseline)

            export_result = self.archive_export.export_field_package(
                point_layer,
                polygon_layer,
                gpkg_path,
                selected_only=selected_only,
                store_styles=store_styles,
                create_project=create_project,
                relative_paths=relative_paths,
                include_readme=include_readme,
                preparation_report=preparation_report or {},
            )

            web_result = self.web_exporter.export(
                point_layer,
                polygon_layer,
                root / f"{base_name}_WEB_MAP.html",
                selected_only=selected_only,
            )

            preflight_result = self.preflight.run()
            preflight_path = root / "WellImporter_PREFLIGHT.json"
            preflight_path.write_text(
                json.dumps(preflight_result, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            basemap_manifest = {
                "catalog": [self._safe_basemap_definition(name) for name in self.basemaps.names()],
                "favorites": self.basemaps.favorites(),
                "note": (
                    "Офлайн-кэш публичных тайлов включается только при подтверждённом "
                    "разрешении/лицензии провайдера."
                ),
            }
            basemap_path = root / "WellImporter_BASEMAPS.json"
            basemap_path.write_text(
                json.dumps(basemap_manifest, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            offline_cache_name = ""
            last_cache = self.basemaps.last_cache()
            if last_cache:
                source_cache = Path(last_cache["path"])
                if source_cache.is_file():
                    cache_dir = root / "Basemaps"
                    cache_dir.mkdir(parents=True, exist_ok=True)
                    target_cache = cache_dir / source_cache.name
                    shutil.copy2(source_cache, target_cache)
                    offline_cache_name = target_cache.relative_to(root).as_posix()
                    basemap_manifest["included_offline_cache"] = {
                        "name": last_cache.get("name", ""),
                        "file": offline_cache_name,
                    }
                    basemap_path.write_text(
                        json.dumps(basemap_manifest, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )

            offline_basemap_attached = False
            if offline_cache_name and export_result.get("project_path"):
                offline_basemap_attached = self._attach_offline_basemap(
                    export_result.get("project_path"),
                    root / offline_cache_name,
                    (last_cache or {}).get("name", "Офлайн-фон"),
                )

            package_manifest = {
                "format": 2,
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "selected_only": bool(selected_only),
                "points": int(export_result.get("points", 0)),
                "circles": int(export_result.get("circles", 0)),
                "gpkg": Path(export_result.get("gpkg_path", gpkg_path)).name,
                "qgis_project": Path(export_result["project_path"]).name if export_result.get("project_path") else "",
                "readme": Path(export_result["info_path"]).name if export_result.get("info_path") else "",
                "web_map": Path(web_result["path"]).name,
                "sync_baseline": baseline_path.name,
                "preflight": preflight_path.name,
                "basemap_manifest": basemap_path.name,
                "offline_basemap_cache": offline_cache_name,
                "offline_basemap_attached": bool(offline_basemap_attached),
            }
            manifest_path = root / self.MANIFEST_NAME
            manifest_path.write_text(
                json.dumps(package_manifest, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            if output.exists():
                output.unlink()
            with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
                for file_path in sorted(root.rglob("*")):
                    if file_path.is_file():
                        archive.write(file_path, file_path.relative_to(root).as_posix())

            with zipfile.ZipFile(output, "r") as check_archive:
                files = [item.filename for item in check_archive.infolist()]

        result = dict(export_result)
        result.update({
            "zip_path": str(output),
            "package_files": files,
            "web_map_path": package_manifest["web_map"],
            "preflight": preflight_result,
            "manifest": package_manifest,
            # Эти пути существовали только во временной директории. Внешнему
            # коду сообщаем имена файлов внутри ZIP, а не несуществующие пути.
            "gpkg_path": package_manifest["gpkg"],
            "project_path": package_manifest["qgis_project"],
            "info_path": package_manifest["readme"],
        })
        return result

    def _attach_offline_basemap(self, project_path, cache_path, name):
        """Добавляет MBTiles в выездной QGIS-проект как нижний фоновый слой."""
        project_path = Path(project_path)
        cache_path = Path(cache_path)
        if not project_path.is_file() or not cache_path.is_file():
            return False
        project = QgsProject()
        if not project.read(str(project_path)):
            return False
        try:
            project.setFilePathStorage(Qgis.FilePathType.Relative)
        except Exception:
            pass
        layer = QgsRasterLayer(str(cache_path), f"Фоновая карта — {name}", "gdal")
        if not layer.isValid():
            return False
        project.addMapLayer(layer, False)
        project.layerTreeRoot().addLayer(layer)
        return bool(project.write(str(project_path)))

    def _safe_basemap_definition(self, name):
        definition = self.basemaps.definition(name)
        return {
            "name": name,
            "url": definition.get("url", ""),
            "max_zoom": definition.get("max_zoom", 0),
            "attribution": definition.get("attribution", ""),
            "favorite": bool(definition.get("favorite")),
            "offline_allowed": bool(definition.get("offline_allowed")),
        }
