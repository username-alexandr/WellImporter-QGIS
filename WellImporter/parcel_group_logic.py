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


def choose_group_index(group_paths, previous=""):
    """Выбирает индекс группы без скрытого выбора первой из нескольких.

    Сохранённая группа восстанавливается только при точном совпадении пути.
    Если сохранённого выбора нет, единственная доступная группа может быть
    выбрана автоматически. При двух и более группах пользователь обязан
    сделать выбор сам, поэтому возвращается -1.
    """
    values = [str(value or "").strip() for value in (group_paths or [])]
    previous = str(previous or "").strip()
    if previous:
        try:
            return values.index(previous)
        except ValueError:
            return -1
    return 0 if len(values) == 1 else -1
