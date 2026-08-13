# -*- coding: utf-8 -*-

from qgis.PyQt import QtGui, QtWidgets

from .severity import Severity


class PreviewDialog(QtWidgets.QDialog):
    """Предпросмотр импорта с оценкой серьёзности, дублями и карантином."""

    def __init__(self, records, checks, duplicate_checks, source_title, allow_import=True, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Предпросмотр импорта — Well Importer")
        self.resize(1120, 680)

        layout = QtWidgets.QVBoxLayout(self)
        coord_by_row = {item.row: item for item in checks}
        duplicate_by_row = {item.row: item for item in duplicate_checks}
        quarantine = list(getattr(records, "quarantine", []) or [])

        severities = []
        for row_index in range(1, len(records) + 1):
            coord = coord_by_row.get(row_index)
            duplicate = duplicate_by_row.get(row_index)
            severities.append(Severity.max(
                coord.severity if coord else Severity.INFO,
                duplicate.severity if duplicate and duplicate.messages else Severity.INFO,
            ))
        counts = Severity.counts(severities)
        flagged_duplicates = sum(1 for item in duplicate_checks if item.messages)

        summary = QtWidgets.QLabel(
            f"Источник: <b>{source_title}</b><br>Корректных строк: <b>{len(records)}</b>; "
            f"в карантине: <b>{len(quarantine)}</b>; "
            f"возможных дублей: <b>{flagged_duplicates}</b>; "
            f"критических: <b>{counts.get(Severity.CRITICAL, 0)}</b>; "
            f"ошибок: <b>{counts.get(Severity.ERROR, 0)}</b>; "
            f"предупреждений: <b>{counts.get(Severity.WARNING, 0)}</b>. "
            "Ошибочные строки не блокируют импорт корректных записей."
        )
        summary.setWordWrap(True)
        layout.addWidget(summary)

        self.table = QtWidgets.QTableWidget(len(records), 8, self)
        self.table.setHorizontalHeaderLabels([
            "Строка", "Номер", "X / долгота WGS84", "Y / широта WGS84",
            "Формат", "Серьёзность", "Проверка координат", "Интеллектуальные дубли"
        ])
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)

        for row_index, record in enumerate(records):
            row_number = row_index + 1
            coord = coord_by_row.get(row_number)
            duplicate = duplicate_by_row.get(row_number)
            severity = Severity.max(
                coord.severity if coord else Severity.INFO,
                duplicate.severity if duplicate and duplicate.messages else Severity.INFO,
            )
            values = [
                str(row_number),
                str(record.number),
                f"{record.x:.6f}",
                f"{record.y:.6f}",
                str(getattr(record, "coordinate_format", "DD")),
                Severity.label(severity),
                coord.message if coord else "OK",
                duplicate.message if duplicate else "Дубли не обнаружены",
            ]
            color = QtGui.QColor(*Severity.COLORS[severity])
            for col, value in enumerate(values):
                item = QtWidgets.QTableWidgetItem(value)
                item.setBackground(color)
                if severity == Severity.CRITICAL:
                    item.setForeground(QtGui.QColor(150, 0, 0))
                elif severity == Severity.ERROR:
                    item.setForeground(QtGui.QColor(160, 70, 0))
                self.table.setItem(row_index, col, item)

        header = self.table.horizontalHeader()
        for col in range(6):
            header.setSectionResizeMode(col, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(6, QtWidgets.QHeaderView.Stretch)
        header.setSectionResizeMode(7, QtWidgets.QHeaderView.Stretch)
        layout.addWidget(self.table)

        if quarantine:
            quarantine_label = QtWidgets.QLabel(
                "<b>Карантин текущей сессии</b> — эти строки исключены из импорта. "
                "Очередь хранится только до закрытия текущей сессии QGIS."
            )
            quarantine_label.setWordWrap(True)
            layout.addWidget(quarantine_label)

            self.quarantine_table = QtWidgets.QTableWidget(len(quarantine), 4, self)
            self.quarantine_table.setHorizontalHeaderLabels([
                "Источник", "Строка", "Исходные значения", "Причина"
            ])
            self.quarantine_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
            self.quarantine_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
            self.quarantine_table.verticalHeader().setVisible(False)
            self.quarantine_table.setMaximumHeight(190)

            for row_index, entry in enumerate(quarantine):
                values = [
                    str(entry.source),
                    str(entry.row),
                    str(entry.raw_values),
                    str(entry.error),
                ]
                for col, value in enumerate(values):
                    item = QtWidgets.QTableWidgetItem(value)
                    item.setBackground(QtGui.QColor(255, 230, 230))
                    self.quarantine_table.setItem(row_index, col, item)

            qheader = self.quarantine_table.horizontalHeader()
            qheader.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
            qheader.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
            qheader.setSectionResizeMode(2, QtWidgets.QHeaderView.Stretch)
            qheader.setSectionResizeMode(3, QtWidgets.QHeaderView.Stretch)
            layout.addWidget(self.quarantine_table)

        info = QtWidgets.QLabel(
            "Шкала: Информация — справочный сигнал; Предупреждение — требуется внимание; "
            "Ошибка — вероятная проблема; Критическая — высокая вероятность дубля или неверных данных."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        buttons = QtWidgets.QDialogButtonBox(self)
        if allow_import:
            import_button = buttons.addButton("Импортировать корректные строки", QtWidgets.QDialogButtonBox.AcceptRole)
            import_button.setDefault(True)
        buttons.addButton("Закрыть" if not allow_import else "Отмена", QtWidgets.QDialogButtonBox.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
