from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from WellImporter.parcel_group_logic import (
    choose_group_index,
    purpose_or_layer,
    resolve_unique_match,
)


def check(condition, label):
    assert condition, label
    print(f"OK: {label}")


state, match = resolve_unique_match([])
check(state == "not_found" and match is None, "no parcel means not found")

candidate = {"layer": "Гос участки", "fid": 10}
state, match = resolve_unique_match([candidate])
check(state == "matched" and match is candidate, "single parcel is accepted")

state, match = resolve_unique_match([candidate, {"layer": "Земельный фонд", "fid": 20}])
check(state == "conflict" and match is None, "multiple parcels are conflict")

check(
    purpose_or_layer("Государственная собственность", "Гос участки") == "Государственная собственность",
    "explicit purpose has priority",
)
check(
    purpose_or_layer("", "Участки земельного фонда") == "Участки земельного фонда",
    "layer name is purpose fallback",
)

check(
    choose_group_index([], "") == -1,
    "empty group list has no selection",
)
check(
    choose_group_index(["Земельные участки"], "") == 0,
    "single group may be selected automatically",
)
check(
    choose_group_index(["Гос участки", "Земельный фонд"], "") == -1,
    "multiple groups require explicit user selection",
)
check(
    choose_group_index(["Гос участки", "Земельный фонд"], "Земельный фонд") == 1,
    "saved group is restored by exact path",
)
check(
    choose_group_index(["Гос участки", "Земельный фонд"], "Старая группа") == -1,
    "stale saved group is not silently replaced",
)
