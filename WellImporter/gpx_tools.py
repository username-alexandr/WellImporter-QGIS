# -*- coding: utf-8 -*-

from pathlib import Path
import xml.etree.ElementTree as ET


class GpxRouteExporter:
    """Экспортирует оптимизированный маршрут Well Importer в GPX 1.1."""

    NS = "http://www.topografix.com/GPX/1/1"

    def export(self, plan, file_path, route_name="Маршрут Well Importer"):
        if plan is None or not getattr(plan, "stops", None):
            raise ValueError("Нет рассчитанного маршрута для экспорта.")
        path = Path(file_path)
        if path.suffix.lower() != ".gpx":
            path = path.with_suffix(".gpx")
        path.parent.mkdir(parents=True, exist_ok=True)

        ET.register_namespace("", self.NS)
        root = ET.Element(self._tag("gpx"), {"version": "1.1", "creator": "Well Importer"})

        for index, stop in enumerate(plan.stops, start=1):
            self._validate(stop.lon, stop.lat)
            waypoint = ET.SubElement(root, self._tag("wpt"), self._coords(stop.lon, stop.lat))
            ET.SubElement(waypoint, self._tag("name")).text = f"Скважина {stop.number}"
            ET.SubElement(waypoint, self._tag("desc")).text = f"Порядок объезда: {index}"

        route = ET.SubElement(root, self._tag("rte"))
        ET.SubElement(route, self._tag("name")).text = str(route_name)
        if plan.start_point is not None:
            lon, lat = plan.start_point
            self._validate(lon, lat)
            point = ET.SubElement(route, self._tag("rtept"), self._coords(lon, lat))
            ET.SubElement(point, self._tag("name")).text = "Старт маршрута"

        for stop in plan.stops:
            point = ET.SubElement(route, self._tag("rtept"), self._coords(stop.lon, stop.lat))
            ET.SubElement(point, self._tag("name")).text = f"Скважина {stop.number}"

        if plan.closed and plan.stops:
            stop = plan.stops[0]
            point = ET.SubElement(route, self._tag("rtept"), self._coords(stop.lon, stop.lat))
            ET.SubElement(point, self._tag("name")).text = f"Скважина {stop.number}"

        tree = ET.ElementTree(root)
        try:
            ET.indent(tree, space="  ")
        except AttributeError:
            pass
        tree.write(path, encoding="utf-8", xml_declaration=True)
        return {"path": str(path), "waypoints": len(plan.stops), "route_points": len(route.findall(self._tag("rtept")))}

    def _tag(self, name):
        return f"{{{self.NS}}}{name}"

    def _coords(self, lon, lat):
        return {"lat": f"{float(lat):.6f}", "lon": f"{float(lon):.6f}"}

    def _validate(self, lon, lat):
        if not -180.0 <= float(lon) <= 180.0:
            raise ValueError("Долгота GPX вне диапазона -180..180.")
        if not -90.0 <= float(lat) <= 90.0:
            raise ValueError("Широта GPX вне диапазона -90..90.")
