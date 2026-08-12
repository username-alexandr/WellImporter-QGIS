# -*- coding: utf-8 -*-

from pathlib import Path
import csv

from qgis.PyQt import QtCore, QtGui, QtWidgets
from qgis.core import QgsMapLayerType, QgsProject, QgsWkbTypes

from .history_dialog import HistoryDialog
from .severity import Severity
from .well_number_field import feature_well_number
from .repair_wizard import RepairWizard
from .audit_issue_list import AuditIssueList
from .statistics_panel import InteractiveBarChart


class ControlCenterDialog(QtWidgets.QDialog):
    """Единый центр управления импортом, контролем качества и рабочими операциями."""

    def __init__(self, main_dialog, parent=None):
        super().__init__(parent or main_dialog)
        self.main = main_dialog
        self.controller = main_dialog.controller
        self.settings = main_dialog.settings
        self.current_search_results = []
        self.last_audit_report = None
        self.setWindowTitle("Центр управления Well Importer")
        self.setMinimumSize(560, 420)
        self._resize_to_available_screen()
        self._build_ui()
        self.refresh_layers()
        self.refresh_overview()
        self.refresh_statistics()

    def _resize_to_available_screen(self):
        """Подбирает размер окна под доступную область экрана."""
        screen = QtWidgets.QApplication.primaryScreen()
        if screen is None:
            self.resize(900, 650)
            return

        available = screen.availableGeometry()
        width = min(1040, max(560, int(available.width() * 0.90)))
        height = min(720, max(420, int(available.height() * 0.86)))
        width = min(width, max(520, available.width() - 24))
        height = min(height, max(380, available.height() - 24))
        self.resize(width, height)

    def _add_scroll_tab(self, widget, title):
        """Добавляет вкладку в прокручиваемой области."""
        widget.setMinimumSize(0, 0)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        scroll.setWidget(widget)
        self.tabs.addTab(scroll, title)
        return scroll

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        title = QtWidgets.QLabel("<b style='font-size:18px'>Центр управления Well Importer</b><br>Контроль качества, исправление, участки, поиск, архив, выезд и отчётность")
        title.setWordWrap(True)
        layout.addWidget(title)

        self.tabs = QtWidgets.QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.tabBar().setUsesScrollButtons(True)
        self.tabs.setElideMode(QtCore.Qt.ElideRight)
        layout.addWidget(self.tabs, 1)
        self._build_import_tab()
        self._build_overview_tab()
        self._build_statistics_tab()
        self._build_quality_tab()
        self._build_parcel_tab()
        self._build_search_tab()
        self._build_operations_tab()
        self._build_reports_tab()

        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _metric_label(self, title):
        label = QtWidgets.QLabel(f"<b>{title}</b><br><span style='font-size:22px'>—</span>")
        label.setAlignment(QtCore.Qt.AlignCenter)
        label.setMinimumHeight(75)
        label.setStyleSheet("QLabel { border: 1px solid #c8d4df; border-radius: 8px; background: #f7fafc; padding: 8px; }")
        return label

    def _build_import_tab(self):
        tab = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(tab)
        self.lblImportState = QtWidgets.QLabel()
        self.lblImportState.setWordWrap(True)
        v.addWidget(self.lblImportState)
        self._refresh_import_state()

        row1 = QtWidgets.QHBoxLayout()
        btnBrowse = QtWidgets.QPushButton("Выбрать файл")
        btnImportFile = QtWidgets.QPushButton("Импортировать выбранный файл")
        btnBrowse.clicked.connect(self._browse_from_center)
        btnImportFile.clicked.connect(self._import_file_from_center)
        row1.addWidget(btnBrowse)
        row1.addWidget(btnImportFile)
        v.addLayout(row1)

        row2 = QtWidgets.QHBoxLayout()
        btnCheck = QtWidgets.QPushButton("Проверить буфер")
        btnClipboard = QtWidgets.QPushButton("Вставить из буфера")
        btnCheck.clicked.connect(self.main.check_clipboard_clicked)
        btnClipboard.clicked.connect(self._import_clipboard_from_center)
        row2.addWidget(btnCheck)
        row2.addWidget(btnClipboard)
        v.addLayout(row2)

        note = QtWidgets.QLabel(
            "Параметры импорта (профиль, год, площадь, формат координат и целевые слои) "
            "берутся из главного окна Well Importer. После операции панель состояния обновляется автоматически."
        )
        note.setWordWrap(True)
        v.addWidget(note)
        v.addStretch(1)
        self._add_scroll_tab(tab, "Импорт")

    def _refresh_import_state(self):
        if not hasattr(self, "lblImportState"):
            return
        self.lblImportState.setText(
            f"Файл: {self.main.ui.txtExcelPath.text().strip() or 'не выбран'}\n"
            f"Год: {self.main.ui.spinYear.value()}    Площадь: {self.main.ui.spinArea.value():.2f} га\n"
            f"Слой точек: {self.main.ui.cmbPoints.currentText() or '—'}\n"
            f"Слой кругов: {self.main.ui.cmbCircles.currentText() or '—'}"
        )

    def _browse_from_center(self):
        self.main.browse_excel_clicked()
        self._refresh_import_state()

    def _import_file_from_center(self):
        self.main.import_file_clicked()
        self._refresh_import_state()
        self.refresh_overview()

    def _import_clipboard_from_center(self):
        self.main.import_clicked()
        self.refresh_overview()

    def _build_overview_tab(self):
        tab = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(tab)
        grid = QtWidgets.QGridLayout()
        self.lblWells = self._metric_label("Скважины")
        self.lblCircles = self._metric_label("Круги")
        self.lblErrors = self._metric_label("Ошибки")
        self.lblWarnings = self._metric_label("Предупреждения")
        self.lblImports = self._metric_label("Импорты")
        for col, widget in enumerate([self.lblWells, self.lblCircles, self.lblErrors, self.lblWarnings, self.lblImports]):
            grid.addWidget(widget, 0, col)
        v.addLayout(grid)
        self.lblLatest = QtWidgets.QLabel("Последний импорт: —")
        v.addWidget(self.lblLatest)
        self.txtOverview = QtWidgets.QPlainTextEdit()
        self.txtOverview.setReadOnly(True)
        v.addWidget(self.txtOverview, 1)
        row = QtWidgets.QHBoxLayout()
        btnRefresh = QtWidgets.QPushButton("Обновить состояние")
        btnHistory = QtWidgets.QPushButton("История импортов")
        btnRefresh.clicked.connect(self.refresh_overview)
        btnHistory.clicked.connect(lambda: HistoryDialog(self.controller.history.items(), self).exec_())
        row.addWidget(btnRefresh)
        row.addWidget(btnHistory)
        row.addStretch(1)
        v.addLayout(row)
        self._add_scroll_tab(tab, "Обзор")

    def _build_statistics_tab(self):
        tab = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(tab)

        note = QtWidgets.QLabel(
            "Интерактивная статистика по рабочему слою скважин. Нажмите на столбец диаграммы, "
            "чтобы выделить соответствующие скважины и приблизить их на карте."
        )
        note.setWordWrap(True)
        v.addWidget(note)

        top = QtWidgets.QHBoxLayout()
        self.lblStatisticsTotal = QtWidgets.QLabel("Скважин: —")
        top.addWidget(self.lblStatisticsTotal)
        top.addStretch(1)
        btnRefresh = QtWidgets.QPushButton("Обновить статистику")
        btnRefresh.clicked.connect(self.refresh_statistics)
        top.addWidget(btnRefresh)
        v.addLayout(top)

        grid = QtWidgets.QGridLayout()
        self.chartYear = InteractiveBarChart("Скважины по годам")
        self.chartParcel = InteractiveBarChart("Скважины по участкам")
        self.chartStatus = InteractiveBarChart("Скважины по состояниям")
        self.chartBatch = InteractiveBarChart("Скважины по партиям")
        self.chartYear.barClicked.connect(lambda value: self.show_statistics_category("year", value))
        self.chartParcel.barClicked.connect(lambda value: self.show_statistics_category("parcel", value))
        self.chartStatus.barClicked.connect(lambda value: self.show_statistics_category("status", value))
        self.chartBatch.barClicked.connect(lambda value: self.show_statistics_category("batch", value))
        grid.addWidget(self.chartYear, 0, 0)
        grid.addWidget(self.chartParcel, 0, 1)
        grid.addWidget(self.chartStatus, 1, 0)
        grid.addWidget(self.chartBatch, 1, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        v.addLayout(grid, 1)

        state_note = QtWidgets.QLabel(
            "Поле «Состояние» создаётся автоматически. Допустимые значения: «Пробурена» и «Не заполнено». "
            "Новые импортированные скважины получают состояние «Пробурена»."
        )
        state_note.setWordWrap(True)
        v.addWidget(state_note)
        self._add_scroll_tab(tab, "Статистика")

    def _build_quality_tab(self):
        tab = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(tab)

        audit_box = QtWidgets.QGroupBox("Полный аудит проекта")
        audit_layout = QtWidgets.QVBoxLayout(audit_box)
        audit_note = QtWidgets.QLabel(
            "Одна проверка анализирует обязательные атрибуты, наличие пар точка/круг, "
            "площадь и центрирование площадных кругов. Аудит ничего не изменяет в слоях."
        )
        audit_note.setWordWrap(True)
        audit_layout.addWidget(audit_note)
        self.btnFullAudit = QtWidgets.QPushButton("Полный аудит проекта")
        self.btnFullAudit.setMinimumHeight(42)
        font = self.btnFullAudit.font()
        font.setBold(True)
        self.btnFullAudit.setFont(font)
        self.btnFullAudit.clicked.connect(self.full_project_audit)
        audit_layout.addWidget(self.btnFullAudit)
        v.addWidget(audit_box)

        required = QtWidgets.QGroupBox("Параметры обязательных атрибутов")
        form = QtWidgets.QFormLayout(required)
        self.txtRequiredPoints = QtWidgets.QLineEdit(", ".join(self.settings.required_point_fields()))
        self.txtRequiredPolygons = QtWidgets.QLineEdit(", ".join(self.settings.required_polygon_fields()))
        form.addRow("Поля скважин:", self.txtRequiredPoints)
        form.addRow("Поля кругов:", self.txtRequiredPolygons)
        v.addWidget(required)

        repair_box = QtWidgets.QGroupBox("Исправление ошибок")
        repair_layout = QtWidgets.QVBoxLayout(repair_box)
        repair_note = QtWidgets.QLabel(
            "Мастер использует результат полного аудита, предлагает безопасные операции, "
            "запрашивает подтверждение и после исправления повторяет аудит проекта."
        )
        repair_note.setWordWrap(True)
        repair_layout.addWidget(repair_note)
        self.btnRepairWizard = QtWidgets.QPushButton("Мастер исправления ошибок")
        self.btnRepairWizard.setMinimumHeight(40)
        self.btnRepairWizard.clicked.connect(self.open_repair_wizard)
        repair_layout.addWidget(self.btnRepairWizard)
        v.addWidget(repair_box)

        self.txtQuality = QtWidgets.QPlainTextEdit()
        self.txtQuality.setReadOnly(True)
        self.txtQuality.setMaximumHeight(190)
        self.txtQuality.setPlaceholderText("Результат полного аудита проекта")
        v.addWidget(self.txtQuality)

        issues_box = QtWidgets.QGroupBox("Интерактивный список ошибок")
        issues_layout = QtWidgets.QVBoxLayout(issues_box)
        issues_note = QtWidgets.QLabel(
            "Фильтруйте найденные проблемы, выбирайте строку и нажимайте «Показать на карте» "
            "или дважды щёлкните по ошибке для перехода к связанному объекту."
        )
        issues_note.setWordWrap(True)
        issues_layout.addWidget(issues_note)
        self.auditIssueList = AuditIssueList()
        self.auditIssueList.issueActivated.connect(self.show_audit_issue_on_map)
        issues_layout.addWidget(self.auditIssueList, 1)
        v.addWidget(issues_box, 1)
        self._add_scroll_tab(tab, "Контроль и исправление")

    def _build_parcel_tab(self):
        tab = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(tab)

        title = QtWidgets.QLabel(
            "<b>Автоматическое определение земельных участков</b><br>"
            "Well Importer самостоятельно анализирует полигональные слои проекта, "
            "определяет слой земельных участков и поле его наименования. Ручной выбор не требуется."
        )
        title.setWordWrap(True)
        v.addWidget(title)

        source_box = QtWidgets.QGroupBox("Автоматически найденный источник")
        source_layout = QtWidgets.QFormLayout(source_box)
        self.lblParcelLayerAuto = QtWidgets.QLabel("—")
        self.lblParcelFieldAuto = QtWidgets.QLabel("—")
        self.lblCadastralFieldAuto = QtWidgets.QLabel("—")
        self.lblParcelLayerAuto.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        self.lblParcelFieldAuto.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        self.lblCadastralFieldAuto.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        source_layout.addRow("Слой участков:", self.lblParcelLayerAuto)
        source_layout.addRow("Поле участка:", self.lblParcelFieldAuto)
        source_layout.addRow("Кадастровое поле (обнаружено):", self.lblCadastralFieldAuto)
        v.addWidget(source_box)

        self.chkSelectedOnly = QtWidgets.QCheckBox("Обрабатывать только выделенные скважины")
        v.addWidget(self.chkSelectedOnly)

        btn = QtWidgets.QPushButton("Автоматически определить участки и кадастровые номера")
        btn.setMinimumHeight(40)
        btn.clicked.connect(self.assign_parcels)
        v.addWidget(btn)

        note = QtWidgets.QLabel(
            "Результат записывается в поля WI_PARCEL и WI_CAD с псевдонимами «Земельный участок» "
            "и «Кадастровый номер». Если точка попадает в несколько полигонов, выбирается участок "
            "с ближайшим центроидом."
        )
        note.setWordWrap(True)
        v.addWidget(note)
        self.txtParcels = QtWidgets.QPlainTextEdit()
        self.txtParcels.setReadOnly(True)
        v.addWidget(self.txtParcels, 1)
        self._add_scroll_tab(tab, "Земельные участки")

    def _build_search_tab(self):
        tab = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(tab)
        row = QtWidgets.QHBoxLayout()
        row.addWidget(QtWidgets.QLabel("Номер скважины:"))
        self.txtWellNumber = QtWidgets.QLineEdit()
        self.txtWellNumber.setPlaceholderText("Например: 15 или 015")
        row.addWidget(self.txtWellNumber, 1)
        self.chkAutoZoom = QtWidgets.QCheckBox("Автоматически приблизить")
        self.chkAutoZoom.setChecked(True)
        row.addWidget(self.chkAutoZoom)
        btnFind = QtWidgets.QPushButton("Найти")
        btnFind.clicked.connect(self.find_well)
        row.addWidget(btnFind)
        v.addLayout(row)

        self.searchTable = QtWidgets.QTableWidget(0, 5)
        self.searchTable.setHorizontalHeaderLabels(["FID", "Номер", "Год", "Земельный участок", "Кадастровый номер"])
        self.searchTable.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.searchTable.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.searchTable.doubleClicked.connect(lambda _index: self.zoom_selected_search())
        self.searchTable.horizontalHeader().setStretchLastSection(True)
        v.addWidget(self.searchTable, 1)

        buttons = QtWidgets.QHBoxLayout()
        btnZoom = QtWidgets.QPushButton("Приблизить к выбранной")
        btnPdf = QtWidgets.QPushButton("Печать карточки PDF")
        btnPng = QtWidgets.QPushButton("Карта-схема PNG")
        btnZoom.clicked.connect(self.zoom_selected_search)
        btnPdf.clicked.connect(lambda: self.export_well_card(False))
        btnPng.clicked.connect(lambda: self.export_well_card(True))
        buttons.addWidget(btnZoom)
        buttons.addWidget(btnPdf)
        buttons.addWidget(btnPng)
        buttons.addStretch(1)
        v.addLayout(buttons)
        self._add_scroll_tab(tab, "Поиск и карточка")

    def _build_operations_tab(self):
        tab = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(tab)
        label = QtWidgets.QLabel(
            "Из единого центра можно перейти к операциям, которые уже доступны в основном окне: "
            "архивирование старых партий, мастер выездного экспорта и история."
        )
        label.setWordWrap(True)
        v.addWidget(label)
        btnArchive = QtWidgets.QPushButton("Архивировать старые импорты")
        btnField = QtWidgets.QPushButton("Мастер подготовки проекта для выезда")
        btnHistory = QtWidgets.QPushButton("История импортов")
        btnArchive.clicked.connect(self.main.archive_old_imports)
        btnField.clicked.connect(self.main.export_for_field)
        btnHistory.clicked.connect(lambda: HistoryDialog(self.controller.history.items(), self).exec_())
        v.addWidget(btnArchive)
        v.addWidget(btnField)
        v.addWidget(btnHistory)
        v.addStretch(1)
        self._add_scroll_tab(tab, "Архив и выезд")

    def _build_reports_tab(self):
        tab = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(tab)
        self.lblReportInfo = QtWidgets.QLabel(
            "Можно выгрузить контрольный CSV с проблемами обязательных атрибутов. "
            "Карточка выбранной скважины и карта-схема доступны во вкладке «Поиск и карточка»."
        )
        self.lblReportInfo.setWordWrap(True)
        v.addWidget(self.lblReportInfo)
        btnCsv = QtWidgets.QPushButton("Экспорт полного отчёта контроля в CSV")
        btnPairCsv = QtWidgets.QPushButton("Экспорт отчёта «1 точка = 1 круг» в CSV")
        btnCsv.clicked.connect(self.export_attribute_report)
        btnPairCsv.clicked.connect(self.export_pair_integrity_report)
        v.addWidget(btnCsv)
        v.addWidget(btnPairCsv)
        v.addStretch(1)
        self._add_scroll_tab(tab, "Отчётность")

    def refresh_layers(self):
        """Обновляет сведения об автоматически выбранном слое участков."""
        try:
            _, polygon_id = self._target_ids()
            source = self.controller.detect_parcel_source(polygon_id)
            self.lblParcelLayerAuto.setText(source.get("layer_name", "—") or "—")
            self.lblParcelFieldAuto.setText(source.get("label_field", "—") or "—")
            self.lblCadastralFieldAuto.setText(source.get("cadastral_field", "—") or "—")
        except Exception as exc:
            self.lblParcelLayerAuto.setText("Не найден")
            self.lblParcelFieldAuto.setText("—")
            self.lblCadastralFieldAuto.setText("—")
            self.txtParcels.setPlainText(str(exc))

    def _target_ids(self):
        return self.main._target_ids()

    def _required_fields(self):
        point = [item.strip() for item in self.txtRequiredPoints.text().split(",") if item.strip()]
        polygons = [item.strip() for item in self.txtRequiredPolygons.text().split(",") if item.strip()]
        self.settings.set_required_fields(point, polygons)
        return point, polygons

    def refresh_overview(self):
        try:
            point_id, polygon_id = self._target_ids()
            point_fields, polygon_fields = self._required_fields()
            status = self.controller.project_status(
                point_id, polygon_id, self.main.ui.spinArea.value(), point_fields, polygon_fields
            )
            self._set_metric(self.lblWells, "Скважины", status["wells"])
            self._set_metric(self.lblCircles, "Круги", status["circles"])
            self._set_metric(self.lblErrors, "Ошибки", status["errors"])
            self._set_metric(self.lblWarnings, "Предупреждения", status["warnings"])
            self._set_metric(self.lblImports, "Импорты", status["imports"])
            self.lblLatest.setText(f"Последний импорт: {status.get('latest_import', '—')}")
            self.txtOverview.setPlainText(
                f"Проблем по полному аудиту: {status.get('audit', {}).get('total', 0)}\n"
                f"Критических проблем: {status.get('critical', 0)}\n"
                f"Проблем обязательных атрибутов: {status['attributes'].get('total', 0)}\n"
                f"Проверено пар точка/круг: {status['quality'].get('total', 0)}\n"
                f"Нарушений правила 1 точка = 1 круг: {status.get('audit', {}).get('pair_integrity', {}).get('violations', 0)}\n"
                f"Критических несовпадений номера точка/круг: {status.get('audit', {}).get('number_consistency', {}).get('mismatches', 0)}\n"
                f"Неверных форматов номера: {status.get('audit', {}).get('number_format', {}).get('invalid', 0)}\n"
                f"Кругов без замечаний: {status['quality'].get('ok', 0)}"
            )
        except Exception as exc:
            self.txtOverview.setPlainText(f"Не удалось обновить состояние: {exc}")

    def _set_metric(self, label, title, value):
        label.setText(f"<b>{title}</b><br><span style='font-size:22px'>{value}</span>")

    def refresh_statistics(self):
        """Обновляет четыре интерактивные диаграммы статистики."""
        try:
            point_id, _ = self._target_ids()
            stats = self.controller.project_statistics(point_id)
            self.lblStatisticsTotal.setText(f"Скважин: {stats.get('total', 0)}")
            self.chartYear.set_data(stats.get("year", []))
            self.chartParcel.set_data(stats.get("parcel", []))
            self.chartStatus.set_data(stats.get("status", []))
            self.chartBatch.set_data(stats.get("batch", []))
        except Exception as exc:
            self.lblStatisticsTotal.setText(f"Статистика недоступна: {exc}")
            for chart in (self.chartYear, self.chartParcel, self.chartStatus, self.chartBatch):
                chart.set_data([])

    def show_statistics_category(self, dimension, value):
        """Выделяет на карте объекты, соответствующие выбранному столбцу диаграммы."""
        try:
            point_id, _ = self._target_ids()
            layer = self.controller.layer_by_id(point_id)
            ids = self.controller.statistics_feature_ids(point_id, dimension, value)
            layer.removeSelection()
            if not ids:
                return
            layer.selectByIds(ids)
            self.main.iface.setActiveLayer(layer)
            canvas = self.main.iface.mapCanvas()
            if hasattr(canvas, "zoomToSelected"):
                canvas.zoomToSelected(layer)
            else:
                self.main.iface.actionZoomToSelected().trigger()
            canvas.refresh()
        except Exception as exc:
            self._error(exc)

    def full_project_audit(self):
        """Запускает единственную пользовательскую команду аудита всего проекта."""
        try:
            point_id, polygon_id = self._target_ids()
            point_fields, polygon_fields = self._required_fields()
            report = self.controller.full_project_audit(
                point_id,
                polygon_id,
                self.main.ui.spinArea.value(),
                point_fields,
                polygon_fields,
            )
            self.last_audit_report = report
            counts = report.get("severity_counts", {})
            checked = report.get("checked", {})
            pair_report = report.get("pair_integrity", {})
            number_report = report.get("number_consistency", {})
            number_format = report.get("number_format", {})

            lines = [
                "ПОЛНЫЙ АУДИТ ПРОЕКТА",
                "=" * 24,
                f"Проверено скважин: {checked.get('points', 0)}",
                f"Проверено площадных кругов: {checked.get('circles', 0)}",
                f"Проверено пар точка/круг: {checked.get('pairs', 0)}",
                f"Кругов без замечаний: {checked.get('circles_ok', 0)}",
                "",
                "ОТЧЁТ «1 ТОЧКА = 1 КРУГ»",
                f"Проверено номеров: {pair_report.get('numbers_checked', 0)}",
                f"Корректных пар: {pair_report.get('ok', 0)}",
                f"Нарушений 1:1: {pair_report.get('violations', 0)}",
                f"Точек без круга: {pair_report.get('missing_circles', 0)}",
                f"Кругов без точки: {pair_report.get('missing_points', 0)}",
                f"Дублирующихся точек: {pair_report.get('duplicate_points', 0)}",
                f"Дублирующихся кругов: {pair_report.get('duplicate_circles', 0)}",
                "",
                "КОНТРОЛЬ НОМЕРОВ ТОЧКА ↔ КРУГ",
                f"Геометрически проверено пар: {number_report.get('checked', 0)}",
                f"Критических несовпадений номеров: {number_report.get('mismatches', 0)}",
                f"Не удалось однозначно сопоставить: {number_report.get('unresolved', 0)}",
                "",
                "ФОРМАТ НОМЕРА СКВАЖИНЫ",
                f"Проверено заполненных номеров: {number_format.get('checked', 0)}",
                f"Номеров с неверными символами: {number_format.get('invalid', 0)}",
                "Разрешённый формат: только цифры 0-9.",
                "",
                f"Всего проблем: {report.get('total', 0)}",
                f"Критических: {counts.get(Severity.CRITICAL, 0)}",
                f"Ошибок: {counts.get(Severity.ERROR, 0)}",
                f"Предупреждений: {counts.get(Severity.WARNING, 0)}",
            ]

            issues = report.get("issues", [])
            if issues:
                lines.append("\nПервые найденные проблемы:")
                for issue in issues[:50]:
                    number = issue.get("number", "") or "—"
                    lines.append(
                        f"[{Severity.label(issue.get('severity'))}] "
                        f"{issue.get('category', '')} / №{number}: "
                        f"{issue.get('message', '')}"
                    )
            else:
                lines.append("\nПроблем не обнаружено.")

            self.txtQuality.setPlainText("\n".join(lines))
            self.auditIssueList.set_report(report)
            self.refresh_overview()
        except Exception as exc:
            self._error(exc)

    def show_audit_issue_on_map(self, issue):
        """Выбирает связанный с ошибкой объект и переводит карту к нему."""
        try:
            issue = dict(issue or {})
            point_id, polygon_id = self._target_ids()
            layer_id = str(issue.get("layer_id", "") or "")
            feature_id = int(issue.get("feature_id", -1) or -1)
            number = str(issue.get("number", "") or "").strip()

            candidate_ids = []
            if layer_id:
                candidate_ids.append(layer_id)
            for candidate in (point_id, polygon_id):
                if candidate and candidate not in candidate_ids:
                    candidate_ids.append(candidate)

            target_layer = None
            target_fid = -1

            # Ошибки атрибутов уже содержат FID. Для геометрических проблем
            # аудит иногда знает только номер скважины, поэтому объект ищется
            # по единому логическому полю «Номер скважины».
            if feature_id >= 0 and layer_id:
                layer = QgsProject.instance().mapLayer(layer_id)
                if layer is not None and layer.getFeature(feature_id).isValid():
                    target_layer = layer
                    target_fid = feature_id

            if target_layer is None and number:
                for candidate_id in candidate_ids:
                    layer = QgsProject.instance().mapLayer(candidate_id)
                    if layer is None:
                        continue
                    for feature in layer.getFeatures():
                        if feature_well_number(feature, layer, "").strip() == number:
                            target_layer = layer
                            target_fid = feature.id()
                            break
                    if target_layer is not None:
                        break

            if target_layer is None or target_fid < 0:
                QtWidgets.QMessageBox.information(
                    self,
                    "Интерактивный список ошибок",
                    "Для этой проблемы не удалось однозначно определить объект на карте."
                )
                return

            target_layer.removeSelection()
            target_layer.selectByIds([target_fid])
            self.main.iface.setActiveLayer(target_layer)
            canvas = self.main.iface.mapCanvas()
            if hasattr(canvas, "zoomToSelected"):
                canvas.zoomToSelected(target_layer)
            else:
                self.main.iface.actionZoomToSelected().trigger()
            canvas.refresh()
        except Exception as exc:
            self._error(exc)

    def open_repair_wizard(self):
        """Запускает аудит, мастер исправления и повторный контроль после изменений."""
        try:
            point_id, polygon_id = self._target_ids()
            point_fields, polygon_fields = self._required_fields()
            audit = self.controller.full_project_audit(
                point_id, polygon_id, self.main.ui.spinArea.value(),
                point_fields, polygon_fields,
            )
            if not audit.get("total", 0):
                QtWidgets.QMessageBox.information(
                    self, "Мастер исправления ошибок",
                    "Полный аудит не обнаружил проблем, требующих исправления."
                )
                self.txtQuality.setPlainText("Полный аудит: проблем не обнаружено.")
                self.auditIssueList.set_report(audit)
                return

            wizard = RepairWizard(audit, self)
            if wizard.exec_() != QtWidgets.QDialog.Accepted:
                return

            result = self.controller.repair_project(
                point_id, polygon_id,
                self.main.ui.spinYear.value(),
                self.main.ui.spinArea.value(),
                point_fields, polygon_fields,
                wizard.plan(),
            )
            before = result.get("before", {})
            after = result.get("after", {})
            before_counts = before.get("severity_counts", {})
            after_counts = after.get("severity_counts", {})
            lines = [
                "Мастер исправления завершён.",
                "",
                f"Проблем до: {before.get('total', 0)}",
                f"Проблем после: {after.get('total', 0)}",
                f"Устранено по повторному аудиту: {result.get('fixed', 0)}",
                "",
                "До исправления: "
                f"критических {before_counts.get(Severity.CRITICAL, 0)}, "
                f"ошибок {before_counts.get(Severity.ERROR, 0)}, "
                f"предупреждений {before_counts.get(Severity.WARNING, 0)}",
                "После исправления: "
                f"критических {after_counts.get(Severity.CRITICAL, 0)}, "
                f"ошибок {after_counts.get(Severity.ERROR, 0)}, "
                f"предупреждений {after_counts.get(Severity.WARNING, 0)}",
            ]
            if after.get("total", 0):
                lines.append("Оставшиеся проблемы будут доступны для дальнейшего анализа.")
            self.txtQuality.setPlainText("\n".join(lines))
            self.last_audit_report = after
            self.auditIssueList.set_report(after)
            self.main.refresh_dashboard()
            self.refresh_overview()
            QtWidgets.QMessageBox.information(
                self, "Мастер исправления ошибок", "\n".join(lines)
            )
        except Exception as exc:
            self._error(exc)

    def repair_points(self):
        """
        Исправляет точки отдельно от площадных кругов.

        Автоматически выполняются только безопасные операции:
        восстановление номера по содержащему точку кругу, восстановление
        пустой геометрии по центру круга, заполнение пустого года и создание
        отсутствующей точки для пронумерованного круга.
        """
        answer = QtWidgets.QMessageBox.question(
            self,
            "Исправление точек бурения",
            "Будут исправлены только однозначно восстанавливаемые данные точек:\n"
            "• пустой номер — по площадному кругу;\n"
            "• пустая геометрия — по центру круга с тем же номером;\n"
            "• пустой год — по году из главного окна;\n"
            "• отсутствующая точка — по центру пронумерованного круга.\n\n"
            "Продолжить?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )
        if answer != QtWidgets.QMessageBox.Yes:
            return

        try:
            point_id, polygon_id = self._target_ids()
            result = self.controller.repair_points(
                point_id,
                polygon_id,
                self.main.ui.spinYear.value(),
            )
            self.txtQuality.setPlainText(
                "Исправление точек завершено.\n"
                f"Создано отсутствующих точек: {result.get('created_points', 0)}\n"
                f"Восстановлено номеров: {result.get('restored_numbers', 0)}\n"
                f"Восстановлено геометрий: {result.get('restored_geometry', 0)}\n"
                f"Заполнено пустых значений года: {result.get('filled_years', 0)}\n"
                f"Всего изменений: {result.get('total_changes', 0)}"
            )
            self.main.refresh_dashboard()
            self.refresh_overview()
        except Exception as exc:
            self._error(exc)

    def repair_circles(self):
        if not self.chkRepairArea.isChecked() and not self.chkRepairCenter.isChecked():
            QtWidgets.QMessageBox.warning(self, "Исправление кругов", "Выберите хотя бы один тип исправления.")
            return
        answer = QtWidgets.QMessageBox.question(
            self, "Автоматическое исправление",
            "Будут созданы отсутствующие площадные круги, а существующие проблемные круги "
            "будут исправлены по точкам скважин. Продолжить?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )
        if answer != QtWidgets.QMessageBox.Yes:
            return
        try:
            point_id, polygon_id = self._target_ids()
            result = self.controller.repair_circles(
                point_id, polygon_id, self.main.ui.spinArea.value(),
                repair_area=self.chkRepairArea.isChecked(),
                repair_center=self.chkRepairCenter.isChecked(),
            )
            self.txtQuality.setPlainText(
                f"Исправление кругов завершено.\nСоздано отсутствующих кругов: {result.get('created', 0)}\n"
                f"Перестроено кругов: {result.get('repaired', 0)}\n"
                f"Обновлено значений в атрибутивной таблице: {result.get('attributes_updated', 0)}\n"
                f"После исправления без замечаний: {result.get('validation_after', {}).get('ok', 0)} / "
                f"{result.get('validation_after', {}).get('total', 0)}"
            )
            self.main.refresh_dashboard()
            self.refresh_overview()
        except Exception as exc:
            self._error(exc)

    def sync_circle_attributes(self):
        """Обновляет площадь, радиус и смещение центра в строках слоя кругов."""
        answer = QtWidgets.QMessageBox.question(
            self,
            "Синхронизация атрибутов",
            "Будут пересчитаны и записаны атрибуты площади, радиуса и смещения центра "
            "для всех связанных площадных кругов. Продолжить?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.Yes,
        )
        if answer != QtWidgets.QMessageBox.Yes:
            return

        try:
            point_id, polygon_id = self._target_ids()
            result = self.controller.sync_circle_attributes(
                point_id,
                polygon_id,
                self.main.ui.spinArea.value(),
            )
            self.txtQuality.setPlainText(
                "Синхронизация атрибутов завершена.\n"
                f"Обновлено объектов: {result.get('features_updated', 0)}\n"
                f"Обновлено значений: {result.get('values_updated', 0)}\n\n"
                "В слое кругов используются поля WI_AREA_HA, WI_AREA_M2, "
                "WI_RADIUS_M и WI_CENTER_M. Совместимые существующие поля "
                "«Площадь», «Радиус» и аналогичные также обновлены."
            )
            self.main.refresh_dashboard()
            self.refresh_overview()
        except Exception as exc:
            self._error(exc)

    def assign_parcels(self):
        """Определяет участок каждой скважины полностью автоматически."""
        try:
            point_id, polygon_id = self._target_ids()
            result = self.controller.assign_parcels_auto(
                point_id, polygon_id, selected_only=self.chkSelectedOnly.isChecked()
            )
            self.lblParcelLayerAuto.setText(result.get("source_layer", "—") or "—")
            self.lblParcelFieldAuto.setText(result.get("label_field", "—") or "—")
            self.lblCadastralFieldAuto.setText(result.get("cadastral_field", "—") or "—")
            self.txtParcels.setPlainText(
                f"Источник определён автоматически: {result.get('source_layer', '—')}\n"
                f"Поле участка: {result.get('label_field', '—') or '—'}\n"
                f"Поле кадастрового номера: {result.get('cadastral_field', '—') or '—'}\n\n"
                f"Обработано скважин: {result.get('processed', 0)}\n"
                f"Участок найден: {result.get('found', 0)}\n"
                f"Не найден: {result.get('not_found', 0)}\n"
                f"Несколько пересечений: {result.get('multiple', 0)}\n"
                f"Кадастровых номеров получено: {result.get('cadastral_found', 0)}\n"
                f"Пустых кадастровых номеров: {result.get('cadastral_empty', 0)}"
            )
            self.main.refresh_dashboard()
            self.refresh_statistics()
        except Exception as exc:
            self._error(exc)

    def find_well(self):
        try:
            point_id, _ = self._target_ids()
            results = self.controller.find_wells(point_id, self.txtWellNumber.text(), auto_zoom=self.chkAutoZoom.isChecked())
            self.current_search_results = results
            self._populate_search(results)
            if not results:
                QtWidgets.QMessageBox.information(self, "Поиск скважины", "Скважина не найдена.")
        except Exception as exc:
            self._error(exc)

    def _populate_search(self, features):
        point_id, _ = self._target_ids()
        layer = QgsProject.instance().mapLayer(point_id)
        names = layer.fields().names() if layer else []
        self.searchTable.setRowCount(len(features))
        for row, feature in enumerate(features):
            values = [
                str(feature.id()),
                feature_well_number(feature, layer, ""),
                self._field_value(feature, names, ["Год"]),
                self._field_value(feature, names, ["WI_PARCEL"]),
                self._field_value(feature, names, ["WI_CAD"]),
            ]
            for col, value in enumerate(values):
                item = QtWidgets.QTableWidgetItem(value)
                item.setData(QtCore.Qt.UserRole, int(feature.id()))
                self.searchTable.setItem(row, col, item)
        self.searchTable.resizeColumnsToContents()

    def _field_value(self, feature, names, candidates):
        for field in candidates:
            if field in names:
                return str(feature[field]).strip()
        return ""

    def _selected_search_feature_id(self):
        row = self.searchTable.currentRow()
        if row < 0:
            if len(self.current_search_results) == 1:
                return self.current_search_results[0].id()
            raise Exception("Выберите скважину в таблице результатов.")
        item = self.searchTable.item(row, 0)
        return int(item.data(QtCore.Qt.UserRole))

    def zoom_selected_search(self):
        try:
            point_id, _ = self._target_ids()
            fid = self._selected_search_feature_id()
            self.controller.well_search.zoom(self.main.iface, self.controller.layer_by_id(point_id), [fid])
        except Exception as exc:
            self._error(exc)

    def export_well_card(self, image=False):
        try:
            point_id, polygon_id = self._target_ids()
            fid = self._selected_search_feature_id()
            suffix = ".png" if image else ".pdf"
            filter_text = "PNG (*.png)" if image else "PDF (*.pdf)"
            path, _ = QtWidgets.QFileDialog.getSaveFileName(
                self, "Сохранить карту-схему" if image else "Сохранить карточку скважины",
                str(Path(self.main._default_output_dir()) / f"Скважина_{fid}{suffix}"), filter_text
            )
            if not path:
                return
            result = self.controller.export_well_card(
                point_id, polygon_id, fid, path,
                area_ha=self.main.ui.spinArea.value(), image=image,
            )
            QtWidgets.QMessageBox.information(self, "Well Importer", f"Файл создан:\n{result}")
        except Exception as exc:
            self._error(exc)

    def export_pair_integrity_report(self):
        """Экспортирует отдельный отчёт нарушений правила «1 точка = 1 круг»."""
        try:
            point_id, polygon_id = self._target_ids()
            point_fields, polygon_fields = self._required_fields()
            audit_report = self.controller.full_project_audit(
                point_id, polygon_id, self.main.ui.spinArea.value(),
                point_fields, polygon_fields,
            )
            pair_report = audit_report.get("pair_integrity", {})
            path, _ = QtWidgets.QFileDialog.getSaveFileName(
                self, "Сохранить отчёт 1 точка = 1 круг",
                str(Path(self.main._default_output_dir()) / "WellImporter_OnePoint_OneCircle.csv"),
                "CSV (*.csv)",
            )
            if not path:
                return
            with open(path, "w", encoding="utf-8-sig", newline="") as stream:
                writer = csv.writer(stream, delimiter=";")
                writer.writerow([
                    "Номер скважины", "Количество точек", "Количество кругов",
                    "Серьёзность", "Нарушение",
                ])
                for item in pair_report.get("items", []):
                    writer.writerow([
                        item.get("number", ""),
                        item.get("point_count", 0),
                        item.get("circle_count", 0),
                        Severity.label(item.get("severity")),
                        item.get("message", ""),
                    ])
            QtWidgets.QMessageBox.information(
                self, "Отчёт 1 точка = 1 круг",
                f"Отчёт сохранён:\n{path}\n\nНарушений: {pair_report.get('violations', 0)}"
            )
        except Exception as exc:
            self._error(exc)

    def export_attribute_report(self):
        try:
            point_id, polygon_id = self._target_ids()
            point_fields, polygon_fields = self._required_fields()
            audit_report = self.controller.full_project_audit(
                point_id, polygon_id, self.main.ui.spinArea.value(), point_fields, polygon_fields
            )
            path, _ = QtWidgets.QFileDialog.getSaveFileName(
                self, "Сохранить отчёт контроля",
                str(Path(self.main._default_output_dir()) / "WellImporter_Project_Audit.csv"),
                "CSV (*.csv)",
            )
            if not path:
                return
            with open(path, "w", encoding="utf-8-sig", newline="") as stream:
                writer = csv.writer(stream, delimiter=";")
                writer.writerow(["Тип проверки", "Слой/объект", "Номер скважины", "Серьёзность", "Проблема"])
                for issue in audit_report.get("issues", []):
                    writer.writerow([
                        issue.get("category", ""), issue.get("layer_name", ""), issue.get("number", ""),
                        Severity.label(issue.get("severity")), issue.get("message", ""),
                    ])
            QtWidgets.QMessageBox.information(self, "Отчёт", f"Полный отчёт контроля сохранён:\n{path}")
        except Exception as exc:
            self._error(exc)

    def _error(self, exc):
        QtWidgets.QMessageBox.critical(self, "Well Importer", str(exc))
