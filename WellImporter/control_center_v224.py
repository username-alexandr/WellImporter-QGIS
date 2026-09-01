# -*- coding: utf-8 -*-

from qgis.PyQt import QtWidgets

from .control_center import ControlCenterDialog


class ControlCenterDialogV224(ControlCenterDialog):
    """Центр управления 2.2.4 с выбором группы земельных участков."""

    def _build_parcel_tab(self):
        tab = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(tab)

        title = QtWidgets.QLabel(
            "<b>Группа земельных участков</b><br>"
            "Выберите одну группу QGIS. Well Importer будет рекурсивно проверять все "
            "полигональные слои внутри неё и определять участок отдельно для каждой скважины."
        )
        title.setWordWrap(True)
        v.addWidget(title)

        group_box = QtWidgets.QGroupBox("Источник земельных участков")
        form = QtWidgets.QFormLayout(group_box)
        group_row = QtWidgets.QHBoxLayout()
        self.cmbParcelGroup = QtWidgets.QComboBox()
        self.btnRefreshParcelGroups = QtWidgets.QPushButton("Обновить")
        self.btnRefreshParcelGroups.clicked.connect(self.refresh_layers)
        self.cmbParcelGroup.currentIndexChanged.connect(self._parcel_group_changed)
        group_row.addWidget(self.cmbParcelGroup, 1)
        group_row.addWidget(self.btnRefreshParcelGroups)
        form.addRow("Группа слоёв:", group_row)
        self.lblParcelGroupLayers = QtWidgets.QLabel("—")
        self.lblParcelGroupLayers.setWordWrap(True)
        form.addRow("Найденные слои:", self.lblParcelGroupLayers)
        self.lblParcelGroupFields = QtWidgets.QLabel("—")
        self.lblParcelGroupFields.setWordWrap(True)
        form.addRow("Поля:", self.lblParcelGroupFields)
        v.addWidget(group_box)

        self.chkSelectedOnly = QtWidgets.QCheckBox("Обрабатывать только выделенные скважины")
        v.addWidget(self.chkSelectedOnly)

        btn = QtWidgets.QPushButton("Определить участки, кадастр и назначение по группе")
        btn.setMinimumHeight(42)
        btn.clicked.connect(self.assign_parcels)
        v.addWidget(btn)

        note = QtWidgets.QLabel(
            "Результат записывается в поля: «Земельный участок», «Кадастровый номер», "
            "«Назначение участка» и служебный источник. Если в слое нет отдельного поля "
            "назначения/категории/владельца, назначением используется название слоя. "
            "Если скважина попадает сразу в несколько участков, автоматический выбор не выполняется — "
            "такой объект показывается как конфликт."
        )
        note.setWordWrap(True)
        v.addWidget(note)

        self.txtParcels = QtWidgets.QPlainTextEdit()
        self.txtParcels.setReadOnly(True)
        v.addWidget(self.txtParcels, 1)
        self._add_scroll_tab(tab, "Земельные участки")

    def _selected_group_path(self):
        return str(self.cmbParcelGroup.currentData() or self.cmbParcelGroup.currentText() or "").strip()

    def _parcel_group_changed(self, _index=-1):
        group_path = self._selected_group_path()
        if group_path:
            self.settings.set_parcel_group_path(group_path)
        self._refresh_group_summary()

    def refresh_layers(self):
        """Обновляет перечень групп, не выбирая один слой участков автоматически."""
        if not hasattr(self, "cmbParcelGroup"):
            return
        try:
            _, polygon_id = self._target_ids()
        except Exception:
            polygon_id = None

        previous = self._selected_group_path() or self.settings.parcel_group_path()
        self.cmbParcelGroup.blockSignals(True)
        self.cmbParcelGroup.clear()
        try:
            groups = self.controller.parcels.group_paths(
                excluded_layer_ids=[polygon_id] if polygon_id else []
            )
        except Exception:
            groups = []
        for path in groups:
            self.cmbParcelGroup.addItem(path, path)

        target_index = self.cmbParcelGroup.findData(previous) if previous else -1
        if target_index < 0 and self.cmbParcelGroup.count() == 1:
            target_index = 0
        if target_index >= 0:
            self.cmbParcelGroup.setCurrentIndex(target_index)
            self.settings.set_parcel_group_path(self._selected_group_path())
        self.cmbParcelGroup.blockSignals(False)
        self._refresh_group_summary()

    def _refresh_group_summary(self):
        group_path = self._selected_group_path()
        if not group_path:
            self.lblParcelGroupLayers.setText("Группа не выбрана")
            self.lblParcelGroupFields.setText("—")
            return
        try:
            _, polygon_id = self._target_ids()
            report = self.controller.parcels.describe_group(
                group_path,
                excluded_layer_ids=[polygon_id] if polygon_id else [],
            )
            layer_names = [item.get("layer_name", "") for item in report.get("layers", [])]
            self.lblParcelGroupLayers.setText(
                f"{report.get('layer_count', 0)}: " + (", ".join(layer_names) if layer_names else "—")
            )
            self.lblParcelGroupFields.setText(
                f"слоёв с кадастровым полем: {report.get('cadastral_layers', 0)}; "
                f"слоёв с отдельным полем назначения: {report.get('purpose_layers', 0)}"
            )
        except Exception as exc:
            self.lblParcelGroupLayers.setText(str(exc))
            self.lblParcelGroupFields.setText("—")

    def assign_parcels(self):
        try:
            group_path = self._selected_group_path()
            if not group_path:
                raise Exception("Выберите группу земельных участков.")
            self.settings.set_parcel_group_path(group_path)
            self.controller.set_parcel_group_path(group_path)

            point_id, polygon_id = self._target_ids()
            result = self.controller.assign_parcels_auto(
                point_id,
                polygon_id,
                selected_only=self.chkSelectedOnly.isChecked(),
            )

            lines = [
                f"Группа: {result.get('group_path', group_path)}",
                f"Полигональных слоёв: {result.get('source_layer_count', 0)}",
                "Слои: " + (", ".join(result.get("source_layers", [])) or "—"),
                "",
                f"Обработано скважин: {result.get('processed', 0)}",
                f"Участок найден однозначно: {result.get('found', 0)}",
                f"Не найден: {result.get('not_found', 0)}",
                f"Конфликтов перекрытия: {result.get('conflict_count', 0)}",
                f"Кадастровых номеров получено: {result.get('cadastral_found', 0)}",
                f"Пустых кадастровых номеров: {result.get('cadastral_empty', 0)}",
                f"Назначение определено: {result.get('purpose_found', 0)}",
            ]
            if result.get("left_uncommitted"):
                lines.append(
                    "\nСлой скважин уже находился в режиме редактирования; изменения оставлены "
                    "в текущей edit-сессии и не зафиксированы автоматически."
                )

            conflicts = result.get("conflicts", [])
            if conflicts:
                lines.append("\nКОНФЛИКТЫ (первые 20):")
                for conflict in conflicts[:20]:
                    variants = []
                    for item in conflict.get("matches", []):
                        text = item.get("layer", "—")
                        if item.get("cadastral"):
                            text += f" → {item.get('cadastral')}"
                        variants.append(text)
                    lines.append(
                        f"FID скважины {conflict.get('point_feature_id')}: " + " | ".join(variants)
                    )

            self.txtParcels.setPlainText("\n".join(lines))
            self._refresh_group_summary()
            self.main.refresh_dashboard()
            self.refresh_statistics()
        except Exception as exc:
            self._error(exc)
