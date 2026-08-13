# -*- coding: utf-8 -*-

from dataclasses import dataclass
from math import asin, cos, radians, sin, sqrt
from pathlib import Path
import xml.etree.ElementTree as ET


@dataclass
class GpxTrackData:
    """Разобранный фактический GPS-трек."""
    source_name: str
    track_name: str
    segments: list
    point_count: int
    distance_m: float


class GpxTrackImporter:
    """Читает GPX track/trkseg/trkpt без внешних зависимостей."""

    EARTH_RADIUS_M = 6371008.8

    def parse(self, file_path):
        path = Path(file_path)
        if not path.exists():
            raise ValueError(f"GPX-файл не найден: {path}")
        if path.suffix.lower() != ".gpx":
            raise ValueError("Для GPS-трека требуется файл с расширением .gpx.")
        try:
            root = ET.parse(path).getroot()
        except ET.ParseError as exc:
            raise ValueError(f"Некорректный GPX/XML: {exc}") from exc

        track_name = ""
        segments = []
        for track in self._children(root, "trk"):
            if not track_name:
                name_node = self._first_child(track, "name")
                track_name = (name_node.text or "").strip() if name_node is not None else ""
            for segment in self._children(track, "trkseg"):
                points = []
                for node in self._children(segment, "trkpt"):
                    try:
                        lat = float(node.attrib["lat"])
                        lon = float(node.attrib["lon"])
                    except (KeyError, TypeError, ValueError):
                        continue
                    if -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0:
                        points.append((lon, lat))
                if len(points) >= 2:
                    segments.append(points)

        if not segments:
            raise ValueError("В GPX не найдено ни одного трека минимум из двух точек.")

        point_count = sum(len(segment) for segment in segments)
        distance_m = sum(self.segment_distance(segment) for segment in segments)
        return GpxTrackData(
            source_name=path.name,
            track_name=track_name or path.stem,
            segments=segments,
            point_count=point_count,
            distance_m=distance_m,
        )

    def segment_distance(self, points):
        return sum(self.haversine(*left, *right) for left, right in zip(points, points[1:]))

    def haversine(self, lon1, lat1, lon2, lat2):
        lon1, lat1, lon2, lat2 = map(radians, map(float, (lon1, lat1, lon2, lat2)))
        dlon = lon2 - lon1
        dlat = lat2 - lat1
        value = sin(dlat / 2.0) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2.0) ** 2
        return 2.0 * self.EARTH_RADIUS_M * asin(min(1.0, sqrt(value)))

    def _children(self, node, local_name):
        return [child for child in list(node) if self._local_name(child.tag) == local_name]

    def _first_child(self, node, local_name):
        for child in list(node):
            if self._local_name(child.tag) == local_name:
                return child
        return None

    def _local_name(self, tag):
        return str(tag).rsplit("}", 1)[-1]
