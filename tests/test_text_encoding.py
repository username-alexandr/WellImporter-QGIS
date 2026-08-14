from pathlib import Path
import csv
import importlib.util
import io


MODULE = Path(__file__).resolve().parents[1] / "WellImporter" / "text_encoding.py"
spec = importlib.util.spec_from_file_location("well_importer_text_encoding", MODULE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
decode_table_bytes = module.decode_table_bytes


SAMPLE = "X;Y;Номер скважины\r\n48.123456;44.123456;35\r\n"


def check(raw, label):
    text = decode_table_bytes(raw)
    assert "\x00" not in text, f"{label}: NUL remained"
    rows = list(csv.reader(io.StringIO(text), delimiter=";"))
    assert rows[0][:3] == ["X", "Y", "Номер скважины"], f"{label}: bad header {rows[0]}"
    assert rows[1][:3] == ["48.123456", "44.123456", "35"], f"{label}: bad data {rows[1]}"
    print(f"OK: {label}")


check(SAMPLE.encode("utf-8"), "UTF-8")
check(("\ufeff" + SAMPLE).encode("utf-8"), "UTF-8 BOM")
check(SAMPLE.encode("utf-16"), "UTF-16 BOM")
check(SAMPLE.encode("utf-16-le"), "UTF-16 LE without BOM")
check(SAMPLE.encode("utf-16-be"), "UTF-16 BE without BOM")
check(SAMPLE.encode("cp1251"), "Windows-1251")
check(SAMPLE.encode("cp866"), "CP866")

# Воспроизводит исходный симптом: байты UTF-16 LE без BOM содержат NUL,
# но после декодирования стандартный csv.reader должен работать без ошибки.
raw_with_nuls = SAMPLE.encode("utf-16-le")
assert b"\x00" in raw_with_nuls
text = decode_table_bytes(raw_with_nuls)
list(csv.reader(io.StringIO(text), delimiter=";"))
print("OK: csv.reader no longer raises line contains NUL")
