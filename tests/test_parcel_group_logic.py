from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from WellImporter.parcel_group_logic import resolve_unique_match, purpose_or_layer


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
