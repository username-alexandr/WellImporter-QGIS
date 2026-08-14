# -*- coding: utf-8 -*-

"""Безопасное декодирование текстовых таблиц CSV/TXT.

Отдельный модуль не зависит от QGIS, поэтому код определения кодировки можно
проверять обычными unit-тестами. Особое внимание уделено UTF-16 без BOM:
такие файлы нередко создаются Excel и при ошибочном чтении как UTF-8 содержат
технические NUL-символы, из-за которых ``csv.reader`` выдаёт ``line contains NUL``.
"""


def decode_table_bytes(raw):
    """Возвращает текст CSV/TXT без технических NUL-символов.

    Порядок определения:
    1. UTF-8 BOM;
    2. UTF-16 BOM;
    3. UTF-16 LE/BE без BOM;
    4. UTF-8;
    5. Windows-1251;
    6. CP866.
    """
    if not isinstance(raw, (bytes, bytearray)):
        raise TypeError("Ожидалась последовательность байтов.")

    raw = bytes(raw)
    if not raw:
        return ""

    if raw.startswith(b"\xef\xbb\xbf"):
        return _clean_text(raw.decode("utf-8-sig"))

    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        return _clean_text(raw.decode("utf-16"))

    utf16_text = _decode_utf16_without_bom(raw)
    if utf16_text is not None:
        return _clean_text(utf16_text)

    errors = []
    for encoding in ("utf-8", "cp1251", "cp866"):
        try:
            return _clean_text(raw.decode(encoding))
        except UnicodeDecodeError as exc:
            errors.append(f"{encoding}: {exc}")

    raise ValueError(
        "Не удалось прочитать CSV/TXT-файл. Поддерживаются UTF-8, UTF-16, "
        "Windows-1251 и CP866.\n"
        "Попробуйте пересохранить файл из Excel в формате CSV UTF-8.\n\n"
        + "\n".join(errors)
    )


def _decode_utf16_without_bom(raw):
    """Определяет UTF-16 LE/BE без BOM по структуре табличного текста."""
    if len(raw) < 4 or len(raw) % 2 != 0 or b"\x00" not in raw:
        return None

    candidates = []
    for encoding in ("utf-16-le", "utf-16-be"):
        try:
            text = raw.decode(encoding)
        except UnicodeDecodeError:
            continue

        score = _table_text_score(text)
        if score is not None:
            candidates.append((score, text))

    if not candidates:
        return None

    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def _table_text_score(text):
    """Оценивает, похож ли декодированный текст на CSV/TXT-таблицу."""
    if not text:
        return None

    # Правильная endian-последовательность восстанавливает реальные разделители
    # и переводы строк. При неверной endian-последовательности байты обычно
    # превращаются в печатные, но бессмысленные символы Unicode без структуры CSV.
    delimiters = sum(text.count(delimiter) for delimiter in (";", ",", "\t"))
    line_breaks = text.count("\n") + text.count("\r")
    if delimiters == 0 and line_breaks == 0:
        return None

    allowed_controls = {"\r", "\n", "\t"}
    printable = sum(1 for ch in text if ch.isprintable() or ch in allowed_controls)
    controls = sum(1 for ch in text if not ch.isprintable() and ch not in allowed_controls)
    printable_ratio = printable / max(1, len(text))
    if printable_ratio < 0.85:
        return None

    return (
        printable_ratio * 100.0
        + min(delimiters, 20) * 2.0
        + min(line_breaks, 20)
        - controls * 10.0
        - text.count("\x00") * 20.0
    )


def _clean_text(text):
    """Удаляет BOM и остаточные технические NUL после определения кодировки."""
    if text.startswith("\ufeff"):
        text = text.lstrip("\ufeff")
    if "\x00" in text:
        text = text.replace("\x00", "")
    return text
