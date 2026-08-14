from pathlib import Path
import importlib.util

module_path = Path(__file__).resolve().parents[1] / "WellImporter" / "spatial_pairing.py"
spec = importlib.util.spec_from_file_location("spatial_pairing", module_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
greedy_unique_pairs = module.greedy_unique_pairs


def check(name, condition):
    if not condition:
        raise AssertionError(name)
    print(f"OK: {name}")


pairs = greedy_unique_pairs([
    (2.0, 2025, 101),
    (3.0, 2026, 102),
], 50.0)
check(
    "independent points pair by geometry, not by shared well number",
    set(pairs) == {2025, 2026},
)

pairs = greedy_unique_pairs([
    (1.0, 1, 100),
    (2.0, 2, 100),
], 50.0)
check(
    "one circle cannot satisfy two points",
    pairs == {1: {"circle_id": 100, "distance_m": 1.0}},
)

pairs = greedy_unique_pairs([
    (5.0, 1, 100),
    (1.0, 1, 101),
    (2.0, 2, 100),
], 50.0)
check(
    "closest one-to-one assignment wins",
    pairs[1]["circle_id"] == 101 and pairs[2]["circle_id"] == 100,
)

pairs = greedy_unique_pairs([(51.0, 1, 100)], 50.0)
check("far circle does not block missing-circle creation", pairs == {})

pairs = greedy_unique_pairs([(-1.0, 1, 100), (0.0, 2, 101)], 50.0)
check(
    "invalid negative distance ignored and exact center accepted",
    set(pairs) == {2},
)
