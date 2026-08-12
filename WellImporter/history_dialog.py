# -*- coding: utf-8 -*-

from qgis.PyQt import QtCore, QtGui, QtWidgets

from .severity import Severity


class HistoryDialog(QtWidgets.QDialog):
    """История импортов с поиском по тексту и фильтром по году."""

    def __init__(self, history_items, parent=None):
        super().__init__(parent)
        self.history_items = list(history_items)
        self.setWindowTitle("История импортов — Well Importer")
        self.resize(1180, 560)
        layout = QtWidgets.QVBoxLayout(self)

        filters = QtWidgets.QHBoxLayout()
        filters.addWidget(QtWidgets.QLabel("Поиск:"))
        self.txtSearch = QtWidgets.QLineEdit()
        self.txtSearch.setPlaceholderText("Источник, номер партии, слой, дата...")
        filters.addWidget(self.txtSearch, 1)
        filters.addWidget(QtWidgets.QLabel("Год:"))
        self.cmbYear = QtWidgets.QComboBox()
        self.cmbYear.addItem("Все", None)
        years = sorted({str(item.get("year")) for item in self.history_items if item.get("year")}, reverse=True)
        for year in years:
            self.cmbYear.addItem(year, year)
        filters.addWidget(self.cmbYear)
        self.lblCount = QtWidgets.QLabel()
        filters.addWidget(self.lblCount)
        layout.addLayout(filters)

        self.table = QtWidgets.QTableWidget(0, 12, self)
        self.table.setHorizontalHeaderLabels([
            "Дата", "Источник", "Год", "Площадь, га", "Точек", "Кругов",
            "Точные дубли", "Умные дубли", "Предупр.", "Проверка", "Серьёзность", "Статус"
        ])
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.setSortingEnabled(True)
        layout.addWidget(self.table)

        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close, parent=self)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.txtSearch.textChanged.connect(self.apply_filters)
        self.cmbYear.currentIndexChanged.connect(self.apply_filters)
        self.apply_filters()

    def apply_filters(self):
        query = self.txtSearch.text().strip().lower()
        year = self.cmbYear.currentData()
        filtered = []
        for item in self.history_items:
            if year and str(item.get("year", "")) != str(year):
                continue
            haystack = " ".join([
                str(item.get("timestamp", "")), str(item.get("source", "")),
                str(item.get("batch_id", "")), str(item.get("year", "")),
                str(item.get("point_layer_name", "")), str(item.get("polygon_layer_name", "")),
                " ".join(str(value) for value in item.get("well_numbers", [])),
            ]).lower()
            if query and query not in haystack:
                continue
            filtered.append(item)
        self._populate(filtered)
        self.lblCount.setText(f"Показано: {len(filtered)} / {len(self.history_items)}")

    def _populate(self, items):
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(items))
        for row, item in enumerate(items):
            validation = item.get("validation") or {}
            validation_text = "—" if not validation else f"OK {validation.get('ok', 0)}/{validation.get('total', 0)}"

            preview_counts = item.get("preview_severity_counts") or {}
            validation_counts = validation.get("severity_counts") or {}
            severities = [severity for severity in Severity.ORDER if preview_counts.get(severity, 0) or validation_counts.get(severity, 0)]
            highest = Severity.max(*severities) if severities else Severity.INFO

            if item.get("undone"):
                status = "Отменён"
            elif item.get("archived"):
                status = "Архивирован"
            else:
                status = "Активен"

            values = [
                item.get("timestamp", ""), item.get("source", ""), str(item.get("year", "")),
                str(item.get("area_ha", "")), str(item.get("added_points", 0)),
                str(item.get("added_circles", 0)), str(item.get("skipped_duplicates", 0)),
                str(item.get("intelligent_duplicate_count", 0)), str(item.get("suspicious_count", 0)),
                validation_text, Severity.label(highest), status,
            ]
            for col, value in enumerate(values):
                cell = QtWidgets.QTableWidgetItem(value)
                cell.setData(QtCore.Qt.UserRole, item.get("batch_id", ""))
                if col == 10:
                    cell.setBackground(QtGui.QColor(*Severity.COLORS[highest]))
                if col == 11 and item.get("archived") and item.get("archive_path"):
                    cell.setToolTip(f"Архив: {item.get('archive_path')}")
                self.table.setItem(row, col, cell)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSortingEnabled(True)
