# -*- coding: utf-8 -*-

from collections import Counter

from qgis.PyQt import QtCore, QtGui, QtWidgets
from qgis.PyQt.QtCore import QVariant
from qgis.core import QgsEditorWidgetSetup, QgsField


class StatisticsManager:
    """Готовит статистику по скважинам и поддерживает поле «Состояние»."""

    STATUS_FIELD = "Состояние"
    STATUS_DRILLED = "Пробурена"
    STATUS_EMPTY = "Не заполнено"
    YEAR_FIELD = "Год"
    PARCEL_FIELD = "WI_PARCEL"
    BATCH_FIELD = "WI_BATCH"

    DIMENSIONS = {
        "year": YEAR_FIELD,
        "parcel": PARCEL_FIELD,
        "status": STATUS_FIELD,
        "batch": BATCH_FIELD,
    }

    def ensure_status_field(self, layer):
        """Создаёт поле состояния и ValueMap, не фиксируя чужую edit-сессию."""
        was_editable = bool(layer.isEditable())
        started_here = False
        if not was_editable:
            if not layer.startEditing():
                raise Exception(f"Не удалось включить редактирование слоя «{layer.name()}».")
            started_here = True

        created = False
        index = layer.fields().indexFromName(self.STATUS_FIELD)
        if index < 0:
            if not layer.addAttribute(QgsField(self.STATUS_FIELD, QVariant.String, len=32)):
                if started_here:
                    layer.rollBack()
                raise Exception(f"Не удалось создать поле «{self.STATUS_FIELD}».")
            layer.updateFields()
            index = layer.fields().indexFromName(self.STATUS_FIELD)
            created = True

        try:
            layer.setFieldAlias(index, self.STATUS_FIELD)
            layer.setEditorWidgetSetup(
                index,
                QgsEditorWidgetSetup(
                    "ValueMap",
                    {
                        "map": [
                            {self.STATUS_DRILLED: self.STATUS_DRILLED},
                            {self.STATUS_EMPTY: self.STATUS_EMPTY},
                        ]
                    },
                ),
            )
        except Exception:
            # Некоторые провайдеры/старые QGIS могут не сохранить настройку
            # редактора; сами допустимые значения и поле при этом остаются.
            pass

        filled = 0
        for feature in layer.getFeatures():
            value = str(feature[index] or "").strip()
            if not value:
                if layer.changeAttributeValue(feature.id(), index, self.STATUS_EMPTY):
                    filled += 1

        if started_here:
            if not layer.commitChanges():
                errors = "\n".join(layer.commitErrors())
                layer.rollBack()
                raise Exception(f"Не удалось сохранить поле состояния.\n{errors}")

        layer.triggerRepaint()
        return {"created": created, "filled": filled, "field": self.STATUS_FIELD}

    def summarize(self, layer):
        self.ensure_status_field(layer)
        features = list(layer.getFeatures())
        result = {
            "total": len(features),
            "year": self._count(features, layer, "year"),
            "parcel": self._count(features, layer, "parcel"),
            "status": self._count(features, layer, "status"),
            "batch": self._count(features, layer, "batch"),
        }
        return result

    def feature_ids(self, layer, dimension, value):
        field_name = self.DIMENSIONS.get(str(dimension))
        if not field_name or layer.fields().indexFromName(field_name) < 0:
            return []
        target = str(value)
        return [
            feature.id()
            for feature in layer.getFeatures()
            if self._display_value(dimension, feature[field_name]) == target
        ]

    def _count(self, features, layer, dimension):
        field_name = self.DIMENSIONS[dimension]
        if layer.fields().indexFromName(field_name) < 0:
            return []
        counter = Counter(
            self._display_value(dimension, feature[field_name])
            for feature in features
        )
        items = list(counter.items())
        if dimension == "year":
            items.sort(key=lambda item: self._year_sort_key(item[0]))
        else:
            items.sort(key=lambda item: (-item[1], item[0].casefold()))
        return [{"label": label, "count": count} for label, count in items]

    def _display_value(self, dimension, value):
        text = str(value or "").strip()
        if text:
            return text
        if dimension == "status":
            return self.STATUS_EMPTY
        if dimension == "parcel":
            return "Без участка"
        if dimension == "batch":
            return "Без партии"
        if dimension == "year":
            return "Без года"
        return "Не заполнено"

    def _year_sort_key(self, value):
        text = str(value)
        try:
            return (0, int(float(text)), text)
        except Exception:
            return (1, 0, text.casefold())


class InteractiveBarChart(QtWidgets.QWidget):
    """Лёгкий интерактивный bar-chart без внешней зависимости DataPlotly."""

    barClicked = QtCore.pyqtSignal(str)

    def __init__(self, title="", parent=None):
        super().__init__(parent)
        self.title = title
        self._items = []
        self._bar_rects = []
        self._hover_index = -1
        self.setMouseTracking(True)
        self.setMinimumHeight(210)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)

    def set_data(self, items):
        self._items = [
            (str(item.get("label", "")), int(item.get("count", 0)))
            for item in (items or [])
        ]
        self._hover_index = -1
        self.update()

    def paintEvent(self, _event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        palette = self.palette()
        text_color = palette.color(QtGui.QPalette.Text)
        base_color = palette.color(QtGui.QPalette.Highlight)
        background = palette.color(QtGui.QPalette.Base)
        painter.fillRect(self.rect(), background)
        painter.setPen(text_color)

        title_font = painter.font()
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.drawText(12, 24, self.title)
        painter.setFont(self.font())

        self._bar_rects = []
        if not self._items:
            painter.drawText(12, 54, "Нет данных")
            return

        max_count = max(count for _label, count in self._items) or 1
        visible = self._items[:12]
        top = 42
        row_height = max(22, min(34, int((self.height() - top - 12) / max(1, len(visible)))))
        label_width = max(100, min(190, int(self.width() * 0.34)))
        chart_left = label_width + 18
        chart_width = max(60, self.width() - chart_left - 54)

        metrics = painter.fontMetrics()
        for index, (label, count) in enumerate(visible):
            y = top + index * row_height
            elided = metrics.elidedText(label, QtCore.Qt.ElideRight, label_width - 16)
            painter.setPen(text_color)
            painter.drawText(10, y + row_height - 8, elided)

            width = max(3, int(chart_width * (count / max_count))) if count else 1
            rect = QtCore.QRect(chart_left, y + 5, width, max(8, row_height - 10))
            color = QtGui.QColor(base_color)
            if index != self._hover_index:
                color.setAlpha(180)
            painter.fillRect(rect, color)
            painter.setPen(text_color)
            painter.drawText(chart_left + width + 6, y + row_height - 8, str(count))
            self._bar_rects.append((rect, index))

        if len(self._items) > len(visible):
            painter.drawText(10, self.height() - 5, f"Показаны первые {len(visible)} из {len(self._items)} категорий")

    def mouseMoveEvent(self, event):
        index = self._index_at(event.pos())
        if index != self._hover_index:
            self._hover_index = index
            self.update()
        if 0 <= index < len(self._items):
            label, count = self._items[index]
            QtWidgets.QToolTip.showText(event.globalPos(), f"{label}: {count}", self)
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self._hover_index = -1
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            index = self._index_at(event.pos())
            if 0 <= index < len(self._items):
                self.barClicked.emit(self._items[index][0])
        super().mousePressEvent(event)

    def _index_at(self, pos):
        for rect, index in self._bar_rects:
            expanded = rect.adjusted(-3, -3, 36, 3)
            if expanded.contains(pos):
                return index
        return -1
