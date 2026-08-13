# -*- coding: utf-8 -*-

from dataclasses import dataclass
from math import asin, cos, radians, sin, sqrt


@dataclass(frozen=True)
class RouteStop:
    """Одна скважина в задаче маршрутизации."""
    feature_id: int
    number: str
    lon: float
    lat: float


@dataclass
class RoutePlan:
    """Результат оптимизации порядка объезда."""
    stops: list
    mode: str
    start_point: tuple = None
    closed: bool = False
    distance_m: float = 0.0

    def ordered_numbers(self):
        return [str(stop.number) for stop in self.stops]


class RouteOptimizer:
    """Оффлайн-оптимизатор маршрута: ближайший сосед + локальный 2-opt."""

    MODE_FIRST = "FIRST_SELECTED"
    MODE_MAP_POINT = "MAP_POINT"
    MODE_CLOSED = "CLOSED"
    EARTH_RADIUS_M = 6371008.8

    def optimize(self, stops, mode=MODE_FIRST, start_point=None):
        stops = list(stops or [])
        if len(stops) < 2:
            raise ValueError("Для оптимизации маршрута выберите минимум две скважины.")
        if mode not in (self.MODE_FIRST, self.MODE_MAP_POINT, self.MODE_CLOSED):
            raise ValueError("Неизвестный режим оптимизации маршрута.")
        if mode == self.MODE_MAP_POINT and start_point is None:
            raise ValueError("Для этого режима сначала укажите стартовую точку на карте.")

        first_fixed = mode in (self.MODE_FIRST, self.MODE_CLOSED)
        anchor = tuple(start_point) if mode == self.MODE_MAP_POINT else None
        closed = mode == self.MODE_CLOSED

        order = self._nearest_neighbor(stops, anchor=anchor, first_fixed=first_fixed)
        order = self._two_opt(order, anchor=anchor, closed=closed, first_fixed=first_fixed)
        return RoutePlan(
            stops=order,
            mode=mode,
            start_point=anchor,
            closed=closed,
            distance_m=self.route_distance(order, anchor=anchor, closed=closed),
        )

    def _nearest_neighbor(self, stops, anchor=None, first_fixed=False):
        remaining = list(stops)
        ordered = []

        if first_fixed:
            current = remaining.pop(0)
            ordered.append(current)
        elif anchor is not None:
            current = min(remaining, key=lambda stop: self.distance_point_stop(anchor, stop))
            remaining.remove(current)
            ordered.append(current)
        else:
            current = remaining.pop(0)
            ordered.append(current)

        while remaining:
            next_stop = min(remaining, key=lambda stop: self.distance(current, stop))
            remaining.remove(next_stop)
            ordered.append(next_stop)
            current = next_stop
        return ordered

    def _two_opt(self, order, anchor=None, closed=False, first_fixed=False, max_passes=8):
        """Улучшает маршрут перестановкой участков без полного пересчёта каждого кандидата."""
        best = list(order)
        count = len(best)
        if count < 4:
            return best

        for _ in range(max_passes):
            improved = False
            start_i = 1 if first_fixed else 0
            for i in range(start_i, count - 1):
                for j in range(i + 1, count):
                    delta = self._two_opt_delta(best, i, j, anchor=anchor, closed=closed)
                    if delta < -0.01:
                        best[i:j + 1] = reversed(best[i:j + 1])
                        improved = True
            if not improved:
                break
        return best

    def _two_opt_delta(self, order, i, j, anchor=None, closed=False):
        """Возвращает изменение длины при развороте сегмента [i..j]."""
        count = len(order)
        old_cost = 0.0
        new_cost = 0.0

        if i == 0:
            if anchor is not None:
                old_cost += self.distance_point_stop(anchor, order[i])
                new_cost += self.distance_point_stop(anchor, order[j])
        else:
            left = order[i - 1]
            old_cost += self.distance(left, order[i])
            new_cost += self.distance(left, order[j])

        if j == count - 1:
            if closed and count > 1:
                first = order[0]
                old_cost += self.distance(order[j], first)
                new_cost += self.distance(order[i], first)
        else:
            right = order[j + 1]
            old_cost += self.distance(order[j], right)
            new_cost += self.distance(order[i], right)

        return new_cost - old_cost

    def route_distance(self, stops, anchor=None, closed=False):
        stops = list(stops or [])
        if not stops:
            return 0.0

        total = 0.0
        if anchor is not None:
            total += self.distance_point_stop(anchor, stops[0])
        for left, right in zip(stops, stops[1:]):
            total += self.distance(left, right)
        if closed and len(stops) > 1:
            total += self.distance(stops[-1], stops[0])
        return total

    def segment_distances(self, plan):
        """Длины переходов к каждой скважине в порядке плана."""
        result = []
        previous = None
        for index, stop in enumerate(plan.stops):
            if index == 0 and plan.start_point is not None:
                result.append(self.distance_point_stop(plan.start_point, stop))
            elif previous is None:
                result.append(0.0)
            else:
                result.append(self.distance(previous, stop))
            previous = stop
        return result

    def distance(self, left, right):
        return self.haversine(left.lon, left.lat, right.lon, right.lat)

    def distance_point_stop(self, point, stop):
        return self.haversine(float(point[0]), float(point[1]), stop.lon, stop.lat)

    def haversine(self, lon1, lat1, lon2, lat2):
        lon1, lat1, lon2, lat2 = map(radians, map(float, (lon1, lat1, lon2, lat2)))
        dlon = lon2 - lon1
        dlat = lat2 - lat1
        a = sin(dlat / 2.0) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2.0) ** 2
        return 2.0 * self.EARTH_RADIUS_M * asin(min(1.0, sqrt(a)))
