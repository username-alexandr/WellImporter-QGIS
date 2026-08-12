# -*- coding: utf-8 -*-

import os
import re
import zipfile
from pathlib import Path
from urllib.parse import unquote
from xml.etree import ElementTree

from qgis.PyQt import QtCore, QtNetwork
from qgis.PyQt.QtCore import QUrl
from qgis.core import QgsNetworkAccessManager, QgsProject

from .severity import Severity


class FieldPreflightChecker:
    """Проверяет интернет-слои и внешние файлы проекта перед выездом."""

    URL_RE = re.compile(r"https?://[^\s'\"<>]+", re.IGNORECASE)
    FILE_EXTENSIONS = {
        ".gpkg", ".shp", ".dbf", ".shx", ".prj", ".qmd", ".qml", ".sld",
        ".tif", ".tiff", ".vrt", ".img", ".asc", ".csv", ".xlsx", ".txt",
        ".svg", ".png", ".jpg", ".jpeg", ".webp", ".mbtiles", ".sqlite",
    }

    def __init__(self, project=None):
        self.project = project or QgsProject.instance()

    def run(self, timeout_ms=3500):
        internet = self.check_internet_layers(timeout_ms)
        external = self.check_external_files()
        issues = []

        for item in internet:
            if item["available"]:
                severity = Severity.INFO
                message = f"Интернет-слой «{item['layer_name']}» доступен."
            else:
                severity = Severity.ERROR
                message = (
                    f"Интернет-слой «{item['layer_name']}» недоступен: "
                    f"{item.get('error') or 'нет ответа сервера'}."
                )
            issues.append({
                "severity": severity,
                "title": "Интернет-слой",
                "message": message,
                "layer_id": item.get("layer_id", ""),
            })

        missing = [item for item in external if not item["exists"]]
        if missing:
            for item in missing:
                issues.append({
                    "severity": Severity.CRITICAL,
                    "title": "Внешний файл",
                    "message": f"Не найден внешний файл: {item['path']}",
                    "source": item.get("source", ""),
                })
        else:
            issues.append({
                "severity": Severity.INFO,
                "title": "Внешние файлы",
                "message": f"Проверено внешних файлов: {len(external)}; отсутствующих нет.",
            })

        return {
            "internet_layers": internet,
            "external_files": external,
            "missing_external_files": len(missing),
            "issues": issues,
            "severity_counts": Severity.counts(item["severity"] for item in issues),
        }

    def check_internet_layers(self, timeout_ms=3500):
        results = []
        for layer in self.project.mapLayers().values():
            source = str(layer.source() or "")
            urls = self._extract_urls(source)
            if not urls:
                continue
            url = self._sample_url(urls[0])
            result = self._request(url, timeout_ms)
            result.update({
                "layer_id": layer.id(),
                "layer_name": layer.name(),
                "provider": layer.providerType(),
                "url": self._safe_url(url),
            })
            results.append(result)
        return results

    def check_external_files(self):
        resources = {}
        project_file = str(self.project.fileName() or "")
        project_dir = Path(project_file).parent if project_file else Path.cwd()

        for layer in self.project.mapLayers().values():
            source = str(layer.source() or "")
            path = self._local_layer_path(source, project_dir)
            if path:
                resources[str(path)] = {
                    "path": str(path),
                    "source": f"слой: {layer.name()}",
                    "exists": path.exists(),
                }

        # Дополнительно читаем XML проекта: там находятся datasource, SVG,
        # внешние картинки и иные пути, которые не всегда видны через layer.source().
        for raw in self._project_xml_paths(project_file):
            path = self._resolve_file(raw, project_dir)
            if path is None:
                continue
            resources.setdefault(str(path), {
                "path": str(path),
                "source": "QGIS-проект",
                "exists": path.exists(),
            })

        return sorted(resources.values(), key=lambda item: item["path"].casefold())

    def _project_xml_paths(self, project_file):
        if not project_file:
            return []
        path = Path(project_file)
        if not path.exists():
            return []
        try:
            if path.suffix.lower() == ".qgz":
                with zipfile.ZipFile(path, "r") as archive:
                    names = [name for name in archive.namelist() if name.lower().endswith(".qgs")]
                    if not names:
                        return []
                    data = archive.read(names[0])
            else:
                data = path.read_bytes()
            root = ElementTree.fromstring(data)
        except Exception:
            return []

        values = []
        for element in root.iter():
            if element.text and element.tag.lower().endswith("datasource"):
                values.append(element.text.strip())
            for key in ("v", "value", "path", "file", "name"):
                value = element.attrib.get(key)
                if value and self._looks_like_file(value):
                    values.append(value)
        return values

    def _local_layer_path(self, source, project_dir):
        text = unquote(str(source or "")).strip()
        if not text or self.URL_RE.search(text):
            return None
        # OGR sources append |layername=...; GDAL can append provider options.
        candidate = text.split("|", 1)[0].strip()
        if candidate.startswith("file:"):
            candidate = candidate[5:]
        # Database connection strings are not ordinary external files.
        if any(token in candidate.lower() for token in ("dbname=", "host=", "service=")):
            match = re.search(r"dbname=['\"]?([^'\"\s]+)", candidate, re.IGNORECASE)
            if not match:
                return None
            candidate = match.group(1)
        return self._resolve_file(candidate, project_dir)

    def _resolve_file(self, value, project_dir):
        text = unquote(str(value or "")).strip().strip("'\"")
        if not text or self.URL_RE.search(text):
            return None
        if "{" in text and "}" in text:
            return None
        if not self._looks_like_file(text):
            return None
        path = Path(os.path.expandvars(os.path.expanduser(text)))
        if not path.is_absolute():
            path = project_dir / path
        try:
            return path.resolve()
        except Exception:
            return path

    def _looks_like_file(self, value):
        text = str(value or "").strip()
        suffix = Path(text.split("?", 1)[0]).suffix.lower()
        return suffix in self.FILE_EXTENSIONS

    def _extract_urls(self, source):
        """Извлекает URL сервиса из provider source, не захватывая соседние параметры."""
        raw = str(source or "").strip()
        if not raw:
            return []
        values = []
        for match in re.finditer(r"(?:^|[&|])url=([^&|]+)", raw, re.IGNORECASE):
            value = unquote(match.group(1)).strip().strip("'\"")
            if value.lower().startswith(("http://", "https://")):
                values.append(value)
        if values:
            return values
        return self.URL_RE.findall(unquote(raw))

    def _sample_url(self, url):
        return (
            str(url)
            .replace("{z}", "0").replace("{x}", "0").replace("{y}", "0")
            .replace("%7Bz%7D", "0").replace("%7Bx%7D", "0").replace("%7By%7D", "0")
        )

    def _safe_url(self, url):
        # Не сохраняем токены/ключи из query-string в отчёте.
        return str(url).split("?", 1)[0]

    def _request(self, url, timeout_ms):
        manager = QgsNetworkAccessManager.instance()
        reply = manager.get(QtNetwork.QNetworkRequest(QUrl(url)))
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
        error_code = reply.error()
        error = reply.errorString() if error_code != QtNetwork.QNetworkReply.NoError else ""
        available = bool(not timed_out and error_code == QtNetwork.QNetworkReply.NoError)
        reply.deleteLater()
        return {
            "available": available,
            "http_status": int(status or 0),
            "timed_out": bool(timed_out),
            "error": error,
        }
