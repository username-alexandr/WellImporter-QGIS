# -*- coding: utf-8 -*-

from qgis.PyQt import QtGui, QtWidgets

from .severity import Severity


class FieldExportWizard(QtWidgets.QWizard):
    """Мастер подготовки к выезду в последовательности QField Sync: анализ → рекомендации → упаковка."""

    def __init__(self, preparation_report, selected_count=0, parent=None):
        super().__init__(parent)
        self.report = preparation_report or {}
        self.selected_count = int(selected_count or 0)
        self.setWindowTitle("Мастер подготовки проекта для выезда — Well Importer")
        self.resize(860, 610)
        self.setOption(QtWidgets.QWizard.NoBackButtonOnStartPage, True)

        self._build_analysis_page()
        self._build_recommendations_page()
        self._build_scope_page()
        self._build_package_page()

    def _build_analysis_page(self):
        page = QtWidgets.QWizardPage()
        page.setTitle("1. Анализ проекта")
        layout = QtWidgets.QVBoxLayout(page)

        counts = self.report.get("severity_counts", {})
        summary = QtWidgets.QLabel(
            "Перед упаковкой Well Importer анализирует рабочие слои и проект. "
            f"Критических: <b>{counts.get(Severity.CRITICAL, 0)}</b>; "
            f"ошибок: <b>{counts.get(Severity.ERROR, 0)}</b>; "
            f"предупреждений: <b>{counts.get(Severity.WARNING, 0)}</b>."
        )
        summary.setWordWrap(True)
        layout.addWidget(summary)

        checks = self.report.get("checks", [])
        self.analysis_table = QtWidgets.QTableWidget(len(checks), 3, page)
        self.analysis_table.setHorizontalHeaderLabels(["Серьёзность", "Проверка", "Результат"])
        self.analysis_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.analysis_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.analysis_table.verticalHeader().setVisible(False)

        for row, check in enumerate(checks):
            severity = Severity.normalize(check.get("severity"))
            values = [Severity.label(severity), check.get("title", ""), check.get("message", "")]
            color = QtGui.QColor(*Severity.COLORS[severity])
            for col, value in enumerate(values):
                item = QtWidgets.QTableWidgetItem(str(value))
                item.setBackground(color)
                self.analysis_table.setItem(row, col, item)

        header = self.analysis_table.horizontalHeader()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.Stretch)
        layout.addWidget(self.analysis_table, 1)
        self.addPage(page)

    def _build_recommendations_page(self):
        page = QtWidgets.QWizardPage()
        page.setTitle("2. Рекомендации перед выездом")
        layout = QtWidgets.QVBoxLayout(page)

        recommendations = self._recommendations()
        intro = QtWidgets.QLabel(
            "Рекомендации сформированы автоматически из результатов анализа. "
            "Критические проблемы блокируют упаковку; остальные можно устранить до выезда или принять осознанно."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.recommendations = QtWidgets.QTreeWidget()
        self.recommendations.setHeaderLabels(["Приоритет", "Рекомендация"])
        self.recommendations.setRootIsDecorated(False)
        for item in recommendations:
            severity = Severity.normalize(item.get("severity"))
            row = QtWidgets.QTreeWidgetItem([
                Severity.label(severity),
                str(item.get("message", "")),
            ])
            color = QtGui.QColor(*Severity.COLORS[severity])
            row.setBackground(0, color)
            row.setBackground(1, color)
            self.recommendations.addTopLevelItem(row)
        self.recommendations.header().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        self.recommendations.header().setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        layout.addWidget(self.recommendations, 1)

        if not recommendations:
            ok = QtWidgets.QLabel("Проект готов к переходу к этапу упаковки. Существенных рекомендаций нет.")
            ok.setWordWrap(True)
            layout.addWidget(ok)
        self.addPage(page)

    def _build_scope_page(self):
        page = QtWidgets.QWizardPage()
        page.setTitle("3. Территория и объекты для упаковки")
        layout = QtWidgets.QVBoxLayout(page)

        self.radio_selected = QtWidgets.QRadioButton(
            f"Только выделенные скважины ({self.selected_count}) и связанные с ними круги"
        )
        self.radio_all = QtWidgets.QRadioButton("Все объекты рабочих слоёв")
        self.radio_selected.setEnabled(self.selected_count > 0)
        self.radio_selected.setChecked(self.selected_count > 0)
        self.radio_all.setChecked(self.selected_count <= 0)
        layout.addWidget(self.radio_selected)
        layout.addWidget(self.radio_all)

        note = QtWidgets.QLabel(
            "На следующем этапе выбор территории будет расширен вариантами по земельным участкам "
            "и выделением области на карте. Сейчас мастер сохраняет совместимость с выделением скважин."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch(1)
        self.addPage(page)

    def _build_package_page(self):
        page = QtWidgets.QWizardPage()
        page.setTitle("4. Упаковка выездного комплекта")
        layout = QtWidgets.QVBoxLayout(page)

        self.chk_store_styles = QtWidgets.QCheckBox("Сохранить оформление слоёв внутри GeoPackage")
        self.chk_store_styles.setChecked(True)
        self.chk_create_project = QtWidgets.QCheckBox("Создать отдельный проект QGIS (.qgz)")
        self.chk_create_project.setChecked(True)
        self.chk_relative_paths = QtWidgets.QCheckBox("Использовать относительные пути в выездном проекте")
        self.chk_relative_paths.setChecked(True)
        self.chk_readme = QtWidgets.QCheckBox("Создать памятку README с результатами анализа")
        self.chk_readme.setChecked(True)

        layout.addWidget(self.chk_store_styles)
        layout.addWidget(self.chk_create_project)
        layout.addWidget(self.chk_relative_paths)
        layout.addWidget(self.chk_readme)

        counts = self.report.get("severity_counts", {})
        self.lblPackageState = QtWidgets.QLabel()
        self.lblPackageState.setWordWrap(True)
        if counts.get(Severity.CRITICAL, 0):
            self.lblPackageState.setText(
                "<b>Упаковка заблокирована:</b> в анализе остались критические проблемы. "
                "Вернитесь к рекомендациям, устраните их и запустите мастер повторно."
            )
        else:
            self.lblPackageState.setText(
                "Анализ и рекомендации пройдены. После нажатия «Готово» будет создан выездной комплект."
            )
        layout.addWidget(self.lblPackageState)
        layout.addStretch(1)
        self.addPage(page)

    def _recommendations(self):
        recommendations = []
        for check in self.report.get("checks", []):
            severity = Severity.normalize(check.get("severity"))
            if severity == Severity.INFO:
                continue
            title = str(check.get("title", "Проверка") or "Проверка")
            message = str(check.get("message", "") or "")
            action = self._action_for(title, severity)
            recommendations.append({
                "severity": severity,
                "message": f"{title}: {action} {message}".strip(),
            })
        recommendations.sort(
            key=lambda item: (
                -Severity.RANK.get(Severity.normalize(item["severity"]), 0),
                item["message"].casefold(),
            )
        )
        return recommendations

    def _action_for(self, title, severity):
        title_lower = title.lower()
        if "редакт" in title_lower:
            return "Сохраните изменения перед упаковкой."
        if "связ" in title_lower:
            return "Исправьте пары точка/круг в Центре управления."
        if "геометр" in title_lower:
            return "Запустите полный аудит и мастер исправления геометрии."
        if "файл проекта" in title_lower:
            return "Сохраните рабочий QGIS-проект."
        if "оформ" in title_lower:
            return "Проверьте стили и внешние ресурсы оформления."
        if severity == Severity.CRITICAL:
            return "Устраните проблему до выезда."
        return "Проверьте замечание перед выездом."

    def accept(self):
        counts = self.report.get("severity_counts", {})
        if counts.get(Severity.CRITICAL, 0):
            QtWidgets.QMessageBox.critical(
                self,
                "Подготовка к выезду",
                "Упаковка невозможна, пока в анализе проекта есть критические замечания."
            )
            return
        if self.radio_selected.isChecked() and self.selected_count <= 0:
            QtWidgets.QMessageBox.warning(self, "Подготовка к выезду", "Нет выделенных скважин.")
            return
        super().accept()

    def options(self):
        return {
            "selected_only": bool(self.radio_selected.isChecked()),
            "store_styles": bool(self.chk_store_styles.isChecked()),
            "create_project": bool(self.chk_create_project.isChecked()),
            "relative_paths": bool(self.chk_relative_paths.isChecked()),
            "include_readme": bool(self.chk_readme.isChecked()),
        }
