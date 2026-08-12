# -*- coding: utf-8 -*-

from qgis.PyQt import QtCore, QtWidgets

from .severity import Severity


class AuditIssueList(QtWidgets.QWidget):
    """Интерактивный список проблем, сформированных полным аудитом проекта.

    Виджет намеренно не знает ничего о карте QGIS. Он отвечает только за
    фильтрацию, сортировку и выбор ошибки, а переход к объекту выполняет
    ``ControlCenterDialog``. Такое разделение позволяет позже использовать
    тот же список для режима «Следующая / Предыдущая ошибка» и мастера
    исправления без дублирования логики таблицы.
    """

    issueActivated = QtCore.pyqtSignal(dict)
    currentIssueChanged = QtCore.pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._issues = []
        self._visible_issues = []
        self._build_ui()

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        filters = QtWidgets.QHBoxLayout()
        filters.addWidget(QtWidgets.QLabel("Серьёзность:"))
        self.cmbSeverity = QtWidgets.QComboBox()
        self.cmbSeverity.addItem("Все", "")
        for severity in (
            Severity.CRITICAL,
            Severity.ERROR,
            Severity.WARNING,
            Severity.INFO,
        ):
            self.cmbSeverity.addItem(Severity.label(severity), severity)
        filters.addWidget(self.cmbSeverity)

        filters.addWidget(QtWidgets.QLabel("Категория:"))
        self.cmbCategory = QtWidgets.QComboBox()
        self.cmbCategory.addItem("Все", "")
        filters.addWidget(self.cmbCategory)

        self.txtFilter = QtWidgets.QLineEdit()
        self.txtFilter.setClearButtonEnabled(True)
        self.txtFilter.setPlaceholderText("Поиск по номеру, слою или тексту ошибки")
        filters.addWidget(self.txtFilter, 1)
        layout.addLayout(filters)

        self.table = QtWidgets.QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels([
            "Серьёзность",
            "Категория",
            "Номер",
            "Слой",
            "FID",
            "Описание",
        ])
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.setSortingEnabled(True)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QtWidgets.QHeaderView.ResizeToContents)
        layout.addWidget(self.table, 1)

        footer = QtWidgets.QHBoxLayout()
        self.lblCount = QtWidgets.QLabel("Ошибок: 0")
        footer.addWidget(self.lblCount)
        footer.addStretch(1)
        self.btnShow = QtWidgets.QPushButton("Показать на карте")
        self.btnShow.setEnabled(False)
        footer.addWidget(self.btnShow)
        layout.addLayout(footer)

        self.cmbSeverity.currentIndexChanged.connect(self._apply_filters)
        self.cmbCategory.currentIndexChanged.connect(self._apply_filters)
        self.txtFilter.textChanged.connect(self._apply_filters)
        self.table.itemSelectionChanged.connect(self._selection_changed)
        self.table.itemDoubleClicked.connect(lambda _item: self.activate_current())
        self.btnShow.clicked.connect(self.activate_current)

    def set_report(self, report):
        """Загружает новый результат полного аудита и обновляет фильтры."""
        self.set_issues((report or {}).get("issues", []))

    def set_issues(self, issues):
        self._issues = [dict(issue) for issue in (issues or [])]
        current_category = self.cmbCategory.currentData()
        categories = sorted({
            str(issue.get("category", "") or "")
            for issue in self._issues
            if str(issue.get("category", "") or "")
        })

        self.cmbCategory.blockSignals(True)
        self.cmbCategory.clear()
        self.cmbCategory.addItem("Все", "")
        for category in categories:
            self.cmbCategory.addItem(category, category)
        if current_category:
            index = self.cmbCategory.findData(current_category)
            if index >= 0:
                self.cmbCategory.setCurrentIndex(index)
        self.cmbCategory.blockSignals(False)
        self._apply_filters()

    def issues(self):
        return list(self._issues)

    def visible_issues(self):
        return list(self._visible_issues)

    def current_issue(self):
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        if item is None:
            return None
        value = item.data(QtCore.Qt.UserRole)
        return dict(value) if isinstance(value, dict) else None

    def current_visible_index(self):
        issue = self.current_issue()
        if issue is None:
            return -1
        for index, candidate in enumerate(self._visible_issues):
            if candidate == issue:
                return index
        return -1

    def select_visible_index(self, index):
        """Выбирает видимую ошибку по индексу; API используется навигацией п.5."""
        if not self._visible_issues:
            return None
        index = max(0, min(int(index), len(self._visible_issues) - 1))
        target = self._visible_issues[index]
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item is not None and item.data(QtCore.Qt.UserRole) == target:
                self.table.selectRow(row)
                self.table.scrollToItem(item, QtWidgets.QAbstractItemView.PositionAtCenter)
                return dict(target)
        return None

    def activate_current(self):
        issue = self.current_issue()
        if issue is not None:
            self.issueActivated.emit(issue)

    def _selection_changed(self):
        issue = self.current_issue()
        self.btnShow.setEnabled(issue is not None)
        self.currentIssueChanged.emit(issue)

    def _apply_filters(self):
        severity = self.cmbSeverity.currentData() or ""
        category = self.cmbCategory.currentData() or ""
        query = self.txtFilter.text().strip().lower()

        visible = []
        for issue in self._issues:
            if severity and Severity.normalize(issue.get("severity")) != severity:
                continue
            if category and str(issue.get("category", "") or "") != category:
                continue
            haystack = " ".join((
                str(issue.get("number", "") or ""),
                str(issue.get("layer_name", "") or ""),
                str(issue.get("category", "") or ""),
                str(issue.get("message", "") or ""),
            )).lower()
            if query and query not in haystack:
                continue
            visible.append(issue)

        self._visible_issues = visible
        self._populate_table()

    def _populate_table(self):
        sorting = self.table.isSortingEnabled()
        self.table.setSortingEnabled(False)
        self.table.clearContents()
        self.table.setRowCount(len(self._visible_issues))

        for row, issue in enumerate(self._visible_issues):
            severity = Severity.normalize(issue.get("severity"))
            values = [
                Severity.label(severity),
                str(issue.get("category", "") or ""),
                str(issue.get("number", "") or ""),
                str(issue.get("layer_name", "") or ""),
                "" if int(issue.get("feature_id", -1) or -1) < 0 else str(issue.get("feature_id")),
                str(issue.get("message", "") or ""),
            ]
            for column, value in enumerate(values):
                item = QtWidgets.QTableWidgetItem(value)
                item.setData(QtCore.Qt.UserRole, dict(issue))
                item.setToolTip(str(issue.get("message", "") or ""))
                self.table.setItem(row, column, item)

        self.table.setSortingEnabled(sorting)
        self.lblCount.setText(
            f"Показано: {len(self._visible_issues)} из {len(self._issues)}"
        )
        self.btnShow.setEnabled(False)
        self.currentIssueChanged.emit(None)
