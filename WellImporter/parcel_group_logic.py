# -*- coding: utf-8 -*-


def resolve_unique_match(matches):
    """Возвращает состояние сопоставления и единственный допустимый вариант.

    Ноль совпадений — участок не найден. Ровно одно — однозначное совпадение.
    Два и более — конфликт; автоматический выбор запрещён.
    """
    values = list(matches or [])
    if not values:
        return "not_found", None
    if len(values) == 1:
        return "matched", values[0]
    return "conflict", None


def purpose_or_layer(value, layer_name):
    """Использует поле назначения, а при его отсутствии — название слоя."""
    text = str(value or "").strip()
    return text or str(layer_name or "").strip()
