# -*- coding: utf-8 -*-

from qgis.PyQt import QtGui, QtWidgets

from .severity import Severity


class FieldExportWizard(QtWidgets.QWizard):
    """Пошаговый мастер подготовки выездного комплекта."""

    def __init__(self, preparation_report, selected_count=0, parent=None):
        super().__init__(parent)
        self.report = preparation_report or {}
        self.selected_count = int(selected_count or 0)
        self.setWindowTitle("Мастер подготовки проекта для выезда — Well Importer")
        self.resize(820, 560)
        self.setOption(QtWidgets.QWizard.NoBackButtonOnStartPage, True)

        self._build_scope_page()
        self._build_readiness_page()
        self._build_options_page()

    def _build_scope_page(self):
        page = QtWidgets.QWizardPage()
        page.setTitle("1. Что подготовить для выезда")
        layout = QtWidgets.QVBoxLayout(page)

        intro = QtWidgets.QLabel(
            "Мастер проверит выбранные слои, связи скважин с площадными кругами и параметры проекта, "
            "после чего создаст переносимый GeoPackage и, при необходимости, отдельный QGIS-проект."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.radio_selected = QtWidgets.QRadioButton(
            f"Только выделенные скважины ({self.selected_count}) и связанные с ними круги"
        )
        self.radio_all = QtWidgets.QRadioButton("Все объекты выбранных слоёв")
        self.radio_selected.setEnabled(self.selected_count > 0)
        self.radio_selected.setChecked(self.selected_count > 0)
        self.radio_all.setChecked(self.selected_count <= 0)
        layout.addWidget(self.radio_selected)
        layout.addWidget(self.radio_all)
        layout.addStretch(1)
        self.addPage(page)

    def _build_readiness_page(self):
        page = QtWidgets.QWizardPage()
        page.setTitle("2. Проверка готовности")
        layout = QtWidgets.QVBoxLayout(page)

        checks = self.report.get("checks", [])
        counts = self.report.get("severity_counts", {})
        summary = QtWidgets.QLabel(
            "Результат анализа: "
            f"критических: <b>{counts.get(Severity.CRITICAL, 0)}</b>; "
            f"ошибок: <b>{counts.get(Severity.ERROR, 0)}</b>; "
            f"предупреждений: <b>{counts.get(Severity.WARNING, 0)}</b>."
        )
        summary.setWordWrap(True)
        layout.addWidget(summary)

        self.readiness_table = QtWidgets.QTableWidget(len(checks), 3, page)
        self.readiness_table.setHorizontalHeaderLabels(["Серьёзность", "Проверка", "Результат"])
        self.readiness_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.readiness_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.readiness_table.verticalHeader().setVisible(False)

        for row, check in enumerate(checks):
            severity = Severity.normalize(check.get("severity"))
            values = [Severity.label(severity), check.get("title", ""), check.get("message", "")]
            color = QtGui.QColor(*Severity.COLORS[severity])
            for col, value in enumerate(values):
                item = QtWidgets.QTableWidgetItem(str(value))
                item.setBackground(color)
                if severity == Severity.CRITICAL:
                    item.setForeground(QtGui.QColor(150, 0, 0))
                self.readiness_table.setItem(row, col, item)

        header = self.readiness_table.horizontalHeader()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.Stretch)
        layout.addWidget(self.readiness_table)

        if counts.get(Severity.CRITICAL, 0):
            warning = QtWidgets.QLabel(
                "<b>Экспорт заблокирован:</b> сначала устраните критические замечания, затем запустите мастер повторно."
            )
            warning.setWordWrap(True)
            layout.addWidget(warning)
        self.addPage(page)

    def _build_options_page(self):
        page = QtWidgets.QWizardPage()
        page.setTitle("3. Состав выездного комплекта")
        layout = QtWidgets.QVBoxLayout(page)

        self.chk_store_styles = QtWidgets.QCheckBox("Сохранить оформление слоёв внутри GeoPackage")
        self.chk_store_styles.setChecked(True)
        self.chk_create_project = QtWidgets.QCheckBox("Создать отдельный проект QGIS (.qgz)")
        self.chk_create_project.setChecked(True)
        self.chk_relative_paths = QtWidgets.QCheckBox("Использовать относительные пути в выездном проекте")
        self.chk_relative_paths.setChecked(True)
        self.chk_readme = QtWidgets.QCheckBox("Создать памятку README с результатами проверки")
        self.chk_readme.setChecked(True)

        layout.addWidget(self.chk_store_styles)
        layout.addWidget(self.chk_create_project)
        layout.addWidget(self.chk_relative_paths)
        layout.addWidget(self.chk_readme)

        note = QtWidgets.QLabel(
            "Оформление включает рендерер, подписи, прозрачность и другие настройки слоя. "
            "Если стиль использует внешние SVG-файлы или шрифты, на другом компьютере они также должны быть доступны."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch(1)
        self.addPage(page)

    def accept(self):
        """Не позволяет завершить мастер при критических проблемах."""
        counts = self.report.get("severity_counts", {})
        if counts.get(Severity.CRITICAL, 0):
            QtWidgets.QMessageBox.critical(
                self,
                "Подготовка к выезду",
                "Экспорт нельзя продолжить, пока в проверке есть критические замечания."
            )
            return
        if self.radio_selected.isChecked() and self.selected_count <= 0:
            QtWidgets.QMessageBox.warning(self, "Подготовка к выезду", "Нет выделенных скважин.")
            return
        super().accept()

    def options(self):
        """Возвращает выбранные пользователем параметры экспорта."""
        return {
            "selected_only": bool(self.radio_selected.isChecked()),
            "store_styles": bool(self.chk_store_styles.isChecked()),
            "create_project": bool(self.chk_create_project.isChecked()),
            "relative_paths": bool(self.chk_relative_paths.isChecked()),
            "include_readme": bool(self.chk_readme.isChecked()),
        }
