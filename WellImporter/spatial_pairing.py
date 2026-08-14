# -*- coding: utf-8 -*-


def greedy_unique_pairs(candidates, max_distance_m=50.0):
    """Возвращает однозначные пары point_id -> circle_id по минимальной дистанции.

    ``candidates`` — последовательность троек ``(distance_m, point_id, circle_id)``.
    Один круг может быть назначен только одной точке и наоборот. Кандидаты дальше
    ``max_distance_m`` игнорируются. Функция не зависит от QGIS и используется
    как детерминированное ядро пространственного сопоставления.
    """
    limit = float(max_distance_m)
    rows = []
    for distance_m, point_id, circle_id in candidates:
        distance_m = float(distance_m)
        if distance_m < 0 or distance_m > limit:
            continue
        rows.append((distance_m, int(point_id), int(circle_id)))

    rows.sort(key=lambda row: (row[0], row[1], row[2]))

    point_to_circle = {}
    used_circles = set()
    for distance_m, point_id, circle_id in rows:
        if point_id in point_to_circle or circle_id in used_circles:
            continue
        point_to_circle[point_id] = {
            "circle_id": circle_id,
            "distance_m": distance_m,
        }
        used_circles.add(circle_id)

    return point_to_circle
