# -*- coding: utf-8 -*-

from qgis.PyQt import QtCore, QtWidgets

from .severity import Severity


class RepairWizard(QtWidgets.QWizard):
    """Пошаговый мастер безопасного исправления проблем, найденных полным аудитом."""

    def __init__(self, audit_report, parent=None):
        super().__init__(parent)
        self.audit = audit_report or {}
        self.setWindowTitle("Мастер исправления ошибок — Well Importer")
        self.resize(780, 590)
        self.setOption(QtWidgets.QWizard.NoBackButtonOnStartPage, True)

        self._build_summary_page()
        self._build_options_page()
        self._build_confirmation_page()

    def _build_summary_page(self):
        """Показывает результат полного аудита до любых изменений данных."""
        page = QtWidgets.QWizardPage()
        page.setTitle("1. Результаты полного аудита")
        layout = QtWidgets.QVBoxLayout(page)

        counts = self.audit.get("severity_counts", {})
        checked = self.audit.get("checked", {})
        summary = QtWidgets.QLabel(
            f"Найдено проблем: <b>{self.audit.get('total', 0)}</b><br>"
            f"Критических: <b>{counts.get(Severity.CRITICAL, 0)}</b>; "
            f"ошибок: <b>{counts.get(Severity.ERROR, 0)}</b>; "
            f"предупреждений: <b>{counts.get(Severity.WARNING, 0)}</b>.<br><br>"
            f"Проверено скважин: {checked.get('points', 0)}; "
            f"кругов: {checked.get('circles', 0)}; "
            f"пар точка/круг: {checked.get('pairs', 0)}."
        )
        summary.setWordWrap(True)
        layout.addWidget(summary)

        categories = {}
        for issue in self.audit.get("issues", []):
            category = str(issue.get("category", "Прочее") or "Прочее")
            categories[category] = categories.get(category, 0) + 1

        text = QtWidgets.QPlainTextEdit()
        text.setReadOnly(True)
        if categories:
            text.setPlainText("\n".join(
                f"{name}: {count}" for name, count in sorted(categories.items())
            ))
        else:
            text.setPlainText("Полный аудит не обнаружил проблем, требующих исправления.")
        layout.addWidget(text, 1)

        note = QtWidgets.QLabel(
            "Мастер не исправляет данные на этом шаге. На следующей странице можно "
            "выбрать только те операции, которые необходимо выполнить."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        self.addPage(page)

    def _build_options_page(self):
        """Формирует список доступных безопасных операций исправления."""
        page = QtWidgets.QWizardPage()
        page.setTitle("2. Выбор исправлений")
        layout = QtWidgets.QVBoxLayout(page)

        intro = QtWidgets.QLabel(
            "Автоматически выполняются только поддерживаемые Well Importer операции. "
            "Заполненные значения не перезаписываются без необходимости."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        quality_failed = int(self.audit.get("quality", {}).get("failed", 0) or 0)
        has_issues = int(self.audit.get("total", 0) or 0) > 0
        has_pair_issues = any(
            str(issue.get("category", "") or "") == "Соответствие точка ↔ круг"
            for issue in self.audit.get("issues", [])
        )

        points_box = QtWidgets.QGroupBox("Точки бурения")
        points_layout = QtWidgets.QVBoxLayout(points_box)
        self.chk_points = QtWidgets.QCheckBox(
            "Исправить однозначно восстанавливаемые данные точек"
        )
        self.chk_points.setToolTip(
            "Восстановление пустого номера/геометрии, заполнение пустого года и "
            "создание отсутствующей точки по существующему пронумерованному кругу."
        )
        self.chk_points.setChecked(has_issues)
        points_layout.addWidget(self.chk_points)
        layout.addWidget(points_box)

        circles_box = QtWidgets.QGroupBox("Площадные круги")
        circles_layout = QtWidgets.QVBoxLayout(circles_box)

        self.chk_missing_circles = QtWidgets.QCheckBox(
            "Создать отсутствующие круги для существующих точек бурения"
        )
        self.chk_missing_circles.setToolTip(
            "Для каждой пронумерованной точки без соответствующего круга будет создан "
            "круг заданной площади с центром точно в точке бурения."
        )
        self.chk_missing_circles.setChecked(has_pair_issues)
        circles_layout.addWidget(self.chk_missing_circles)

        self.chk_circles = QtWidgets.QCheckBox("Исправить существующие площадные круги")
        self.chk_circles.setChecked(quality_failed > 0)
        circles_layout.addWidget(self.chk_circles)

        self.chk_area = QtWidgets.QCheckBox("Исправлять неправильную площадь")
        self.chk_area.setChecked(True)
        self.chk_center = QtWidgets.QCheckBox("Центрировать круг по точке скважины")
        self.chk_center.setChecked(True)
        self.chk_sync = QtWidgets.QCheckBox("Синхронизировать служебные атрибуты кругов")
        self.chk_sync.setChecked(quality_failed > 0)
        circles_layout.addWidget(self.chk_area)
        circles_layout.addWidget(self.chk_center)
        circles_layout.addWidget(self.chk_sync)
        layout.addWidget(circles_box)

        self.chk_circles.toggled.connect(self._update_circle_controls)
        self._update_circle_controls(self.chk_circles.isChecked())

        warning = QtWidgets.QLabel(
            "После подтверждения выбранные операции изменят рабочие слои и сохранят изменения. "
            "После выполнения Well Importer автоматически повторит полный аудит и покажет результат до/после."
        )
        warning.setWordWrap(True)
        layout.addWidget(warning)
        layout.addStretch(1)
        self.options_page_id = self.addPage(page)

    def _build_confirmation_page(self):
        """Показывает финальный перечень операций перед применением изменений."""
        page = QtWidgets.QWizardPage()
        page.setTitle("3. Подтверждение")
        layout = QtWidgets.QVBoxLayout(page)
        self.confirmation_text = QtWidgets.QLabel()
        self.confirmation_text.setWordWrap(True)
        self.confirmation_text.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        layout.addWidget(self.confirmation_text)
        layout.addStretch(1)
        self.confirmation_page_id = self.addPage(page)

    def _update_circle_controls(self, enabled):
        self.chk_area.setEnabled(bool(enabled))
        self.chk_center.setEnabled(bool(enabled))
        # Синхронизация атрибутов может выполняться отдельно от перестроения геометрии.
        self.chk_sync.setEnabled(True)

    def initializePage(self, page_id):
        super().initializePage(page_id)
        if page_id == self.confirmation_page_id:
            plan = self.plan()
            operations = []
            if plan["repair_points"]:
                operations.append("• исправление точек бурения")
            if plan["create_missing_circles"]:
                operations.append("• создание отсутствующих площадных кругов")
            if plan["repair_circles"]:
                details = []
                if plan["repair_area"]:
                    details.append("площадь")
                if plan["repair_center"]:
                    details.append("центрирование")
                suffix = f" ({', '.join(details)})" if details else ""
                operations.append("• исправление существующих площадных кругов" + suffix)
            if plan["sync_circle_attributes"]:
                operations.append("• синхронизация служебных атрибутов кругов")

            self.confirmation_text.setText(
                "Будут выполнены следующие операции:<br><br>" +
                "<br>".join(operations) +
                "<br><br><b>Нажмите «Готово», чтобы применить изменения.</b>"
            )

    def validateCurrentPage(self):
        if self.currentId() == self.options_page_id:
            plan = self.plan()
            if not any((
                plan["repair_points"],
                plan["create_missing_circles"],
                plan["repair_circles"],
                plan["sync_circle_attributes"],
            )):
                QtWidgets.QMessageBox.warning(
                    self,
                    "Мастер исправления ошибок",
                    "Выберите хотя бы одну операцию исправления."
                )
                return False
            if plan["repair_circles"] and not (
                plan["repair_area"] or plan["repair_center"]
            ):
                QtWidgets.QMessageBox.warning(
                    self,
                    "Мастер исправления ошибок",
                    "Для исправления существующих кругов выберите площадь и/или центрирование."
                )
                return False
        return super().validateCurrentPage()

    def plan(self):
        """Возвращает выбранный пользователем план исправления."""
        return {
            "repair_points": bool(self.chk_points.isChecked()),
            "create_missing_circles": bool(self.chk_missing_circles.isChecked()),
            "repair_circles": bool(self.chk_circles.isChecked()),
            "repair_area": bool(self.chk_area.isChecked()),
            "repair_center": bool(self.chk_center.isChecked()),
            "sync_circle_attributes": bool(self.chk_sync.isChecked()),
        }
