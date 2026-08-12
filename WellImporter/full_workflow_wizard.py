# -*- coding: utf-8 -*-

from pathlib import Path

from qgis.PyQt import QtWidgets

from .severity import Severity


class FullWorkflowWizard(QtWidgets.QWizard):
    """Единый вход в полный цикл: источник → предпросмотр/дубли → запуск."""

    def __init__(self, main_dialog, parent=None):
        super().__init__(parent or main_dialog)
        self.main = main_dialog
        self.records = []
        self.checks = []
        self.duplicate_checks = []
        self.source_title = ""
        self.setWindowTitle("Полный рабочий цикл — Well Importer")
        self.resize(900, 650)
        self.setOption(QtWidgets.QWizard.NoBackButtonOnStartPage, True)

        self._build_source_page()
        self._build_preview_page()
        self._build_plan_page()

    def _build_source_page(self):
        page = QtWidgets.QWizardPage()
        page.setTitle("1. Источник данных")
        layout = QtWidgets.QVBoxLayout(page)

        intro = QtWidgets.QLabel(
            "Выберите источник. Дальше мастер сам проведёт предпросмотр координат, поиск дублей, "
            "импорт, создание точек/кругов, аудит, участки/кадастр, исправление, сохранение, отчёт и резервную копию."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.radioClipboard = QtWidgets.QRadioButton("Буфер обмена: X | Y | Номер скважины")
        self.radioFile = QtWidgets.QRadioButton("Файл XLSX / CSV / TXT")
        self.radioClipboard.setChecked(True)
        layout.addWidget(self.radioClipboard)
        layout.addWidget(self.radioFile)

        file_row = QtWidgets.QHBoxLayout()
        self.txtFile = QtWidgets.QLineEdit(self.main.ui.txtExcelPath.text().strip())
        self.txtFile.setPlaceholderText("Выберите файл данных")
        btnBrowse = QtWidgets.QPushButton("Обзор…")
        btnBrowse.clicked.connect(self._browse)
        file_row.addWidget(self.txtFile, 1)
        file_row.addWidget(btnBrowse)
        layout.addLayout(file_row)

        settings = QtWidgets.QGroupBox("Параметры текущего проекта")
        form = QtWidgets.QFormLayout(settings)
        form.addRow("Точечный слой:", QtWidgets.QLabel(self.main.ui.cmbPoints.currentText()))
        form.addRow("Слой кругов:", QtWidgets.QLabel(self.main.ui.cmbCircles.currentText()))
        form.addRow("Год:", QtWidgets.QLabel(str(self.main.ui.spinYear.value())))
        form.addRow("Площадь круга, га:", QtWidgets.QLabel(str(self.main.ui.spinArea.value())))
        form.addRow(
            "Точные дубли:",
            QtWidgets.QLabel("пропускать" if self.main.ui.chkSkipDuplicates.isChecked() else "не пропускать"),
        )
        layout.addWidget(settings)
        layout.addStretch(1)
        self.source_page_id = self.addPage(page)

    def _build_preview_page(self):
        page = QtWidgets.QWizardPage()
        page.setTitle("2. Предпросмотр и поиск дублей")
        layout = QtWidgets.QVBoxLayout(page)
        self.lblPreview = QtWidgets.QLabel("Данные ещё не проанализированы.")
        self.lblPreview.setWordWrap(True)
        layout.addWidget(self.lblPreview)

        self.table = QtWidgets.QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels([
            "Строка", "X", "Y", "Номер", "Серьёзность", "Проверка / дубли",
        ])
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        for column in range(5):
            header.setSectionResizeMode(column, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QtWidgets.QHeaderView.Stretch)
        layout.addWidget(self.table, 1)

        note = QtWidgets.QLabel(
            "Номера скважин в этом цикле должны состоять только из цифр 0-9. "
            "Ведущие нули допустимы. При ошибке исправьте исходную таблицу и вернитесь на предыдущий шаг."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        self.preview_page_id = self.addPage(page)

    def _build_plan_page(self):
        page = QtWidgets.QWizardPage()
        page.setTitle("3. Запуск полного рабочего цикла")
        layout = QtWidgets.QVBoxLayout(page)
        text = QtWidgets.QLabel(
            "После нажатия «Готово» Well Importer последовательно выполнит:<br><br>"
            "<b>импорт → предпросмотр → дубли → создание точек/кругов → контроль качества → "
            "земельные участки и кадастровые номера → автоматическое исправление → сохранение проекта → "
            "итоговый отчёт → резервная копия.</b><br><br>"
            "Операции исправления выполняются только поддерживаемыми безопасными алгоритмами. "
            "Если слой уже находится в режиме редактирования, чужие несохранённые изменения не должны фиксироваться автоматически."
        )
        text.setWordWrap(True)
        layout.addWidget(text)
        self.lblFinal = QtWidgets.QLabel()
        self.lblFinal.setWordWrap(True)
        layout.addWidget(self.lblFinal)
        layout.addStretch(1)
        self.plan_page_id = self.addPage(page)

    def _browse(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Выберите файл с координатами",
            self.main._preferred_input_folder(),
            "Файлы данных (*.xlsx *.csv *.txt);;Excel XLSX (*.xlsx);;CSV (*.csv);;Text (*.txt)",
        )
        if path:
            self.txtFile.setText(path)
            self.radioFile.setChecked(True)

    def validateCurrentPage(self):
        if self.currentId() == self.source_page_id:
            try:
                self._load_and_analyze()
            except Exception as exc:
                QtWidgets.QMessageBox.warning(self, "Полный рабочий цикл", str(exc))
                return False
        elif self.currentId() == self.preview_page_id:
            invalid = [record.number for record in self.records if not self._valid_number(record.number)]
            if invalid:
                QtWidgets.QMessageBox.critical(
                    self,
                    "Неверные номера скважин",
                    "Продолжение невозможно: найдены номера с недопустимыми символами. "
                    "Разрешены только цифры 0-9. Первые значения: " + ", ".join(invalid[:10]),
                )
                return False
        return super().validateCurrentPage()

    def initializePage(self, page_id):
        super().initializePage(page_id)
        if page_id == self.plan_page_id:
            self.lblFinal.setText(
                f"Источник: <b>{self.source_title}</b><br>"
                f"Строк к обработке: <b>{len(self.records)}</b><br>"
                f"Точечный слой: <b>{self.main.ui.cmbPoints.currentText()}</b><br>"
                f"Слой кругов: <b>{self.main.ui.cmbCircles.currentText()}</b>"
            )

    def _load_and_analyze(self):
        mode, source_crs = self.main._coordinate_options()
        if self.radioFile.isChecked():
            path = self.txtFile.text().strip()
            if not path:
                raise Exception("Не выбран файл XLSX/CSV/TXT.")
            self.records = self.main.file_importer.parse_file(path, mode, source_crs)
            self.source_title = Path(path).name
            self.main.settings.set_last_folder(str(Path(path).parent))
            self.main.ui.txtExcelPath.setText(path)
        else:
            self.records = self.main.clipboard_importer.parse(mode, source_crs)
            self.source_title = "Буфер обмена"

        self.checks = self.main.coordinate_checker.analyze(self.records)
        self.duplicate_checks = self.main.duplicate_checker.analyze(
            self.records, self.main._current_point_layer()
        )
        self._populate_preview()

    def _valid_number(self, value):
        text = str(value or "")
        return bool(text) and all("0" <= char <= "9" for char in text)

    def _populate_preview(self):
        coord_by_row = {item.row: item for item in self.checks}
        duplicate_by_row = {item.row: item for item in self.duplicate_checks}
        limit = min(200, len(self.records))
        self.table.setRowCount(limit)
        severities = []

        for index, record in enumerate(self.records[:limit], start=1):
            coord = coord_by_row.get(index)
            duplicate = duplicate_by_row.get(index)
            severity = Severity.max(
                coord.severity if coord else Severity.INFO,
                duplicate.severity if duplicate and duplicate.messages else Severity.INFO,
                Severity.CRITICAL if not self._valid_number(record.number) else Severity.INFO,
            )
            severities.append(severity)
            messages = []
            if coord and getattr(coord, "message", ""):
                messages.append(str(coord.message))
            if duplicate and getattr(duplicate, "messages", None):
                messages.extend(str(message) for message in duplicate.messages)
            if not self._valid_number(record.number):
                messages.append("Номер содержит недопустимые символы — разрешены только цифры.")
            values = [
                index,
                record.original_x or record.x,
                record.original_y or record.y,
                record.number,
                Severity.label(severity),
                " | ".join(messages),
            ]
            for column, value in enumerate(values):
                self.table.setItem(index - 1, column, QtWidgets.QTableWidgetItem(str(value)))

        all_severities = []
        for row in range(1, len(self.records) + 1):
            coord = coord_by_row.get(row)
            duplicate = duplicate_by_row.get(row)
            number_severity = Severity.CRITICAL if not str(self.records[row - 1].number).isdigit() else Severity.INFO
            all_severities.append(Severity.max(
                coord.severity if coord else Severity.INFO,
                duplicate.severity if duplicate and duplicate.messages else Severity.INFO,
                number_severity,
            ))
        counts = Severity.counts(all_severities)
        duplicate_count = self.main.duplicate_checker.count_flagged(self.duplicate_checks)
        coordinate_warnings = self.main.coordinate_checker.count_warnings(self.checks)
        self.lblPreview.setText(
            f"Источник: <b>{self.source_title}</b>; строк: <b>{len(self.records)}</b>. "
            f"Возможных дублей: <b>{duplicate_count}</b>; замечаний координат: <b>{coordinate_warnings}</b>. "
            f"Критических: <b>{counts.get(Severity.CRITICAL, 0)}</b>; "
            f"ошибок: <b>{counts.get(Severity.ERROR, 0)}</b>; "
            f"предупреждений: <b>{counts.get(Severity.WARNING, 0)}</b>. "
            + (f"Показаны первые {limit} строк." if len(self.records) > limit else "")
        )
