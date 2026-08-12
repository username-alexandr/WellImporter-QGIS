# -*- coding: utf-8 -*-

from qgis.PyQt import QtCore, QtGui, QtWidgets


class HelpToolButton(QtWidgets.QToolButton):
    """
    Кнопка подсказки «?». 

    Стандартные toolTip в QGIS иногда не отображаются на маленьких QToolButton.
    Поэтому класс принудительно показывает QToolTip при наведении курсора и
    дополнительно при нажатии на кнопку.
    """

    def __init__(self, tooltip_text, parent=None):
        """Создаёт кнопку с текстом подсказки."""
        super().__init__(parent)
        self.tooltip_text = tooltip_text

        self.setText("?")
        self.setToolTip(tooltip_text)
        self.setStatusTip(tooltip_text)
        self.setWhatsThis(tooltip_text)

        self.setAutoRaise(False)
        self.setMouseTracking(True)
        self.setCursor(QtCore.Qt.WhatsThisCursor)
        self.setFocusPolicy(QtCore.Qt.NoFocus)
        self.setFixedSize(24, 24)

        self.setStyleSheet(
            "QToolButton {"
            "border: 1px solid #8a8a8a;"
            "border-radius: 12px;"
            "background: #f5f5f5;"
            "font-weight: bold;"
            "color: #1f4e79;"
            "}"
            "QToolButton:hover {"
            "background: #e6f2ff;"
            "border: 1px solid #2f80ed;"
            "}"
        )

        self.clicked.connect(self.show_help_tooltip)

    def enterEvent(self, event):
        """Показывает подсказку при наведении курсора."""
        self.show_help_tooltip()
        super().enterEvent(event)

    def leaveEvent(self, event):
        """Скрывает подсказку после ухода курсора."""
        QtWidgets.QToolTip.hideText()
        super().leaveEvent(event)

    def show_help_tooltip(self):
        """Принудительно показывает всплывающую подсказку около кнопки."""
        position = self.mapToGlobal(QtCore.QPoint(self.width() + 8, self.height() // 2))
        QtWidgets.QToolTip.showText(position, self.tooltip_text, self, self.rect(), 12000)


class Ui_WellImporterDialog(object):
    """
    Класс интерфейса окна.

    Ручной аналог файла, который обычно генерируется из .ui через pyuic5.
    Отвечает только за создание виджетов и их расположение.
    """

    def setupUi(self, WellImporterDialog):
        """Создаёт элементы интерфейса."""
        WellImporterDialog.setObjectName("WellImporterDialog")
        WellImporterDialog.setWindowTitle("Well Importer 2.0.6 — управление скважинами")
        WellImporterDialog.setMinimumSize(520, 420)

        # Внешний layout остаётся в пределах экрана, а длинное содержимое
        # прокручивается внутри QScrollArea.
        self.windowLayout = QtWidgets.QVBoxLayout(WellImporterDialog)
        self.windowLayout.setContentsMargins(8, 8, 8, 8)
        self.scrollArea = QtWidgets.QScrollArea(WellImporterDialog)
        self.scrollArea.setWidgetResizable(True)
        self.scrollArea.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.scrollArea.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self.scrollArea.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self.scrollContent = QtWidgets.QWidget()
        self.scrollContent.setMinimumWidth(0)
        self.verticalLayout = QtWidgets.QVBoxLayout(self.scrollContent)
        self.verticalLayout.setContentsMargins(4, 4, 4, 4)

        self.titleLabel = QtWidgets.QLabel(WellImporterDialog)
        self.titleLabel.setText("<b style='font-size:18px'>Well Importer</b><br>Импорт скважин, интеллектуальная проверка и подготовка проекта для выезда")
        self.titleLabel.setWordWrap(True)
        self.verticalLayout.addWidget(self.titleLabel)

        self.grpDashboard = QtWidgets.QGroupBox(WellImporterDialog)
        self.grpDashboard.setTitle("Главная панель состояния")
        self.dashboardLayout = QtWidgets.QGridLayout(self.grpDashboard)
        self.lblDashWells = QtWidgets.QLabel("Скважины\n—")
        self.lblDashCircles = QtWidgets.QLabel("Круги\n—")
        self.lblDashErrors = QtWidgets.QLabel("Ошибки\n—")
        self.lblDashWarnings = QtWidgets.QLabel("Предупреждения\n—")
        self.lblDashImports = QtWidgets.QLabel("Импорты\n—")
        for index, widget in enumerate([self.lblDashWells, self.lblDashCircles, self.lblDashErrors, self.lblDashWarnings, self.lblDashImports]):
            widget.setAlignment(QtCore.Qt.AlignCenter)
            widget.setMinimumHeight(58)
            widget.setStyleSheet("QLabel {border:1px solid #c8d4df; border-radius:6px; background:#f7fafc; padding:6px;}")
            self.dashboardLayout.addWidget(widget, 0, index)
        self.btnDashboardRefresh = QtWidgets.QPushButton("Обновить")
        self.dashboardLayout.addWidget(self.btnDashboardRefresh, 1, 4)
        self.verticalLayout.addWidget(self.grpDashboard)

        self.grpInstruction = QtWidgets.QGroupBox(WellImporterDialog)
        self.grpInstruction.setTitle("Краткая инструкция")
        self.instructionLayout = QtWidgets.QVBoxLayout(self.grpInstruction)

        self.lblInstruction = QtWidgets.QLabel(self.grpInstruction)
        self.lblInstruction.setWordWrap(True)
        self.lblInstruction.setText(
            "1. Подготовьте X | Y | Номер скважины. Поддерживаются DD, DMS и UTM/проекционные координаты.\n"
            "2. Выберите формат координат и исходную CRS, затем буфер Excel или файл .xlsx/.csv/.txt.\n"
            "3. Предпросмотр покажет интеллектуальные дубли и оценит замечания по уровням серьёзности.\n"
            "4. После подтверждения точки и круги сохранятся в выбранные слои. Площадь задаётся в гектарах: 33 = 33 га = 330 000 м².\n"
            "5. После импорта автоматически проверяются площадь круга и положение его центра. История и отмена доступны отдельными кнопками ниже.\n"
            "6. Центр управления содержит единый «Полный аудит проекта», исправление объектов, земельные участки, поиск, карточки, архив, выезд и отчётность. Файл можно перетащить мышью в окно."
        )
        self.instructionLayout.addWidget(self.lblInstruction)
        self.verticalLayout.addWidget(self.grpInstruction)

        self.grpProfiles = QtWidgets.QGroupBox(WellImporterDialog)
        self.grpProfiles.setTitle("Профили настроек")
        self.profileLayout = QtWidgets.QHBoxLayout(self.grpProfiles)
        self.cmbProfile = QtWidgets.QComboBox()
        self.cmbProfile.setToolTip(
            "Выберите сохранённый профиль. Для создания нового выберите "
            "пункт «+ Добавить профиль…» внизу списка."
        )
        self.btnApplyProfile = QtWidgets.QPushButton("Применить")
        self.btnSaveProfile = QtWidgets.QPushButton("Сохранить изменения")
        self.btnDeleteProfile = QtWidgets.QPushButton("Удалить")
        self.profileLayout.addWidget(self.cmbProfile, 1)
        self.profileLayout.addWidget(self.btnApplyProfile)
        self.profileLayout.addWidget(self.btnSaveProfile)
        self.profileLayout.addWidget(self.btnDeleteProfile)
        self.verticalLayout.addWidget(self.grpProfiles)

        self.grpSettings = QtWidgets.QGroupBox(WellImporterDialog)
        self.grpSettings.setTitle("Параметры")
        self.formLayout = QtWidgets.QGridLayout(self.grpSettings)

        self.lblYear = QtWidgets.QLabel("Год бурения")
        self.spinYear = QtWidgets.QSpinBox()
        self.spinYear.setMinimum(1900)
        self.spinYear.setMaximum(2200)
        self.spinYear.setValue(2026)
        self.helpYear = self._help_button("Год, который будет записан в поле «Год» для всех импортируемых скважин.")
        self.formLayout.addWidget(self.lblYear, 0, 0)
        self.formLayout.addWidget(self.spinYear, 0, 1)
        self.formLayout.addWidget(self.helpYear, 0, 2)
        self.chkAutoCurrentYear = QtWidgets.QCheckBox("Автоматически текущий год")
        self.chkAutoCurrentYear.setChecked(True)
        self.formLayout.addWidget(self.chkAutoCurrentYear, 0, 3)

        self.lblArea = QtWidgets.QLabel("Площадь круга, га")
        self.spinArea = QtWidgets.QDoubleSpinBox()
        self.spinArea.setDecimals(2)
        self.spinArea.setMinimum(0.01)
        self.spinArea.setMaximum(1000000.0)
        self.spinArea.setValue(33.0)
        self.helpArea = self._help_button("Площадь каждого круга задаётся в гектарах. Значение 33 означает 33 га = 330 000 м². Радиус рассчитывается автоматически, центр круга — точка скважины.")
        self.formLayout.addWidget(self.lblArea, 1, 0)
        self.formLayout.addWidget(self.spinArea, 1, 1)
        self.formLayout.addWidget(self.helpArea, 1, 2)

        self.lblCoordinateFormat = QtWidgets.QLabel("Формат координат")
        self.cmbCoordinateFormat = QtWidgets.QComboBox()
        self.cmbCoordinateFormat.addItem("Автоматически", "AUTO")
        self.cmbCoordinateFormat.addItem("Десятичные градусы (DD)", "DD")
        self.cmbCoordinateFormat.addItem("Градусы / минуты / секунды (DMS)", "DMS")
        self.cmbCoordinateFormat.addItem("UTM / проекционные координаты", "PROJECTED")
        self.helpCoordinateFormat = self._help_button(
            "Поддерживаются DD, DMS и проекционные координаты. В режиме «Автоматически» DMS определяется по знакам °/′/″ и направлениям N/S/E/W. "
            "Для UTM или другой проекции укажите исходную CRS ниже."
        )
        self.formLayout.addWidget(self.lblCoordinateFormat, 2, 0)
        self.formLayout.addWidget(self.cmbCoordinateFormat, 2, 1)
        self.formLayout.addWidget(self.helpCoordinateFormat, 2, 2)

        self.lblSourceCrs = QtWidgets.QLabel("Исходная CRS")
        self.txtSourceCrs = QtWidgets.QLineEdit("EPSG:4326")
        self.txtSourceCrs.setPlaceholderText("Например: EPSG:4326, EPSG:32638 или 38N")
        self.helpSourceCrs = self._help_button(
            "Для DD/DMS обычно используется EPSG:4326. Для UTM укажите EPSG соответствующей зоны, например EPSG:32638 или коротко 38N; для южного полушария — EPSG:32738 или 38S."
        )
        self.formLayout.addWidget(self.lblSourceCrs, 3, 0)
        self.formLayout.addWidget(self.txtSourceCrs, 3, 1)
        self.formLayout.addWidget(self.helpSourceCrs, 3, 2)

        self.lblPoints = QtWidgets.QLabel("Слой точек")
        self.cmbPoints = QtWidgets.QComboBox()
        self.helpPoints = self._help_button("Точечный слой, куда будут добавлены новые скважины.")
        self.formLayout.addWidget(self.lblPoints, 4, 0)
        self.formLayout.addWidget(self.cmbPoints, 4, 1)
        self.formLayout.addWidget(self.helpPoints, 4, 2)

        self.lblCircles = QtWidgets.QLabel("Слой кругов")
        self.cmbCircles = QtWidgets.QComboBox()
        self.helpCircles = self._help_button("Полигональный слой, куда будут добавлены площадные круги вокруг скважин.")
        self.formLayout.addWidget(self.lblCircles, 5, 0)
        self.formLayout.addWidget(self.cmbCircles, 5, 1)
        self.formLayout.addWidget(self.helpCircles, 5, 2)

        self.lblDuplicates = QtWidgets.QLabel("Дубли")
        self.chkSkipDuplicates = QtWidgets.QCheckBox("Пропускать уже существующие номера скважин")
        self.chkSkipDuplicates.setChecked(True)
        self.helpDuplicates = self._help_button(
            "Помимо точного номера, предпросмотр интеллектуально ищет одинаковые/похожие номера и точки на расстоянии до 5 м. "
            "Автоматически пропускаются только уже существующие точные номера при включённом флажке."
        )
        self.formLayout.addWidget(self.lblDuplicates, 6, 0)
        self.formLayout.addWidget(self.chkSkipDuplicates, 6, 1)
        self.formLayout.addWidget(self.helpDuplicates, 6, 2)

        self.verticalLayout.addWidget(self.grpSettings)

        self.grpClipboard = QtWidgets.QGroupBox(WellImporterDialog)
        self.grpClipboard.setTitle("Формат данных из Excel")
        self.clipboardLayout = QtWidgets.QVBoxLayout(self.grpClipboard)
        self.lblExample = QtWidgets.QLabel()
        self.lblExample.setWordWrap(True)
        self.lblExample.setText(
            "<b>Формат данных:</b><br>"
            "X&nbsp;&nbsp;&nbsp;&nbsp;Y&nbsp;&nbsp;&nbsp;&nbsp;Номер скважины<br>"
            "48.123456&nbsp;&nbsp;&nbsp;&nbsp;44.654321&nbsp;&nbsp;&nbsp;&nbsp;1<br>"
            "48.123789&nbsp;&nbsp;&nbsp;&nbsp;44.654555&nbsp;&nbsp;&nbsp;&nbsp;2<br><br>"
            "<b>Для буфера:</b> выделите эти столбцы в Excel и нажмите Ctrl+C.<br>"
            "<b>Для файла:</b> сохраните таблицу в .xlsx, .csv или .txt и выберите файл в блоке ниже.<br>"
            "Можно использовать строку заголовков. Для DD/DMS X — долгота, Y — широта; для UTM/проекционных координат X и Y берутся в указанной исходной CRS."
        )
        self.clipboardLayout.addWidget(self.lblExample)
        self.verticalLayout.addWidget(self.grpClipboard)


        self.grpFileImport = QtWidgets.QGroupBox(WellImporterDialog)
        self.grpFileImport.setTitle("Импорт из файла Excel / CSV")
        self.fileLayout = QtWidgets.QGridLayout(self.grpFileImport)

        self.lblExcelPath = QtWidgets.QLabel("Файл данных")
        self.txtExcelPath = QtWidgets.QLineEdit()
        self.txtExcelPath.setPlaceholderText("Выберите .xlsx, .csv или .txt файл")
        self.helpExcelPath = self._help_button(
            "Файл с данными скважин. Поддерживаются .xlsx, .csv и .txt. "
            "В файле должны быть три столбца: X, Y, Номер скважины. "
            "Для .xlsx читается первый лист. CSV/TXT поддерживаются в UTF-8, UTF-16, Windows-1251 и CP866."
        )
        self.btnBrowseExcel = QtWidgets.QPushButton("Выбрать файл")
        self.btnImportFile = QtWidgets.QPushButton("Загрузить файл в слои")

        self.fileLayout.addWidget(self.lblExcelPath, 0, 0)
        self.fileLayout.addWidget(self.txtExcelPath, 0, 1)
        self.fileLayout.addWidget(self.helpExcelPath, 0, 2)
        self.fileLayout.addWidget(self.btnBrowseExcel, 0, 3)
        self.fileLayout.addWidget(self.btnImportFile, 1, 1, 1, 3)

        self.lblFavoriteFolder = QtWidgets.QLabel("Избранные папки")
        self.cmbFavoriteFolder = QtWidgets.QComboBox()
        self.cmbFavoriteFolder.setPlaceholderText("Быстрый выбор рабочей папки")
        self.btnAddFavoriteFolder = QtWidgets.QPushButton("Добавить папку")
        self.btnRemoveFavoriteFolder = QtWidgets.QPushButton("Удалить")
        self.fileLayout.addWidget(self.lblFavoriteFolder, 2, 0)
        self.fileLayout.addWidget(self.cmbFavoriteFolder, 2, 1)
        self.fileLayout.addWidget(self.btnAddFavoriteFolder, 2, 2)
        self.fileLayout.addWidget(self.btnRemoveFavoriteFolder, 2, 3)

        self.lblDropHint = QtWidgets.QLabel("Можно перетащить .xlsx/.csv/.txt мышью прямо в окно плагина.")
        self.lblDropHint.setStyleSheet("color:#4d6475;")
        self.fileLayout.addWidget(self.lblDropHint, 3, 1, 1, 3)

        self.verticalLayout.addWidget(self.grpFileImport)

        self.managementLayout = QtWidgets.QGridLayout()
        self.btnHistory = QtWidgets.QPushButton("История импортов")
        self.btnUndo = QtWidgets.QPushButton("Отменить последний импорт")
        self.btnArchive = QtWidgets.QPushButton("Архивировать старые импорты")
        self.btnExportField = QtWidgets.QPushButton("Мастер экспорта для выезда")
        self.btnSearchWell = QtWidgets.QPushButton("Найти скважину")
        self.btnControlCenter = QtWidgets.QPushButton("Центр управления")
        self.managementLayout.addWidget(self.btnHistory, 0, 0, 1, 2)
        self.managementLayout.addWidget(self.btnUndo, 0, 2)
        self.managementLayout.addWidget(self.btnArchive, 1, 0, 1, 2)
        self.managementLayout.addWidget(self.btnExportField, 1, 2)
        self.managementLayout.addWidget(self.btnSearchWell, 2, 0, 1, 1)
        self.managementLayout.addWidget(self.btnControlCenter, 2, 1, 1, 2)
        self.verticalLayout.addLayout(self.managementLayout)

        self.buttonsLayout = QtWidgets.QHBoxLayout()
        self.btnRefreshLayers = QtWidgets.QPushButton("Обновить слои")
        self.buttonsLayout.addWidget(self.btnRefreshLayers)
        self.btnCheckClipboard = QtWidgets.QPushButton("Проверить буфер")
        self.buttonsLayout.addWidget(self.btnCheckClipboard)

        self.buttonsLayout.addItem(QtWidgets.QSpacerItem(40, 20, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum))

        self.btnImport = QtWidgets.QPushButton("Вставить из буфера")
        self.btnImport.setDefault(True)
        self.buttonsLayout.addWidget(self.btnImport)
        self.btnClose = QtWidgets.QPushButton("Закрыть")
        self.buttonsLayout.addWidget(self.btnClose)

        self.verticalLayout.addLayout(self.buttonsLayout)

        self.lblStatus = QtWidgets.QLabel("Ожидание импорта...")
        self.verticalLayout.addWidget(self.lblStatus)

        self.txtLog = QtWidgets.QPlainTextEdit()
        self.txtLog.setReadOnly(True)
        self.txtLog.setPlaceholderText("Журнал импорта")
        self.txtLog.setMinimumHeight(110)
        self.verticalLayout.addWidget(self.txtLog)

        # Помещаем всё содержимое в прокручиваемую область.
        self.scrollArea.setWidget(self.scrollContent)
        self.windowLayout.addWidget(self.scrollArea, 1)

        # Размер окна ограничивается доступной областью текущего экрана.
        # На небольших мониторах окно больше не выходит за нижнюю границу.
        screen = QtWidgets.QApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            target_width = min(980, max(520, int(available.width() * 0.90)))
            target_height = min(900, max(420, int(available.height() * 0.86)))
            target_width = min(target_width, max(480, available.width() - 24))
            target_height = min(target_height, max(360, available.height() - 24))
            WellImporterDialog.resize(target_width, target_height)
        else:
            WellImporterDialog.resize(900, 680)

        QtCore.QMetaObject.connectSlotsByName(WellImporterDialog)

    def _help_button(self, tooltip):
        """
        Создаёт кнопку «?» с гарантированным всплывающим окном подсказки.

        Подсказка появляется при наведении курсора и дополнительно при клике.
        """
        return HelpToolButton(tooltip)

    def instructionText(self):
        """Возвращает полный текст актуальной инструкции для отдельного окна."""
        return (
            "Well Importer 2.0.6 — инструкция по работе\n\n"
            "Формат данных\n"
            "Три столбца: X | Y | Номер скважины.\n\n"
            "Форматы координат\n"
            "Поддерживаются десятичные градусы (DD), градусы/минуты/секунды (DMS) и UTM/другие проекционные координаты. "
            "Для DD и DMS обычно укажите EPSG:4326. Для UTM задайте EPSG зоны, например EPSG:32638 для 38N. "
            "Перед импортом все координаты автоматически приводятся к WGS84.\n\n"
            "Интеллектуальный поиск дублей\n"
            "В предпросмотре проверяются одинаковые номера, номера с ведущими нулями, совпадающие координаты и существующие скважины в радиусе до 5 м. "
            "Каждое замечание получает уровень: Информация, Предупреждение, Ошибка или Критическая.\n\n"
            "Площадные круги\n"
            "Площадь задаётся в гектарах. 33 означает 33 га = 330 000 м². Центром круга является точка скважины. "
            "После импорта проверяются фактическая площадь и смещение центра.\n\n"
            "Импорт\n"
            "Можно вставить данные из буфера Excel или загрузить .xlsx/.csv/.txt. Перед изменением слоёв всегда открывается предпросмотр.\n\n"
            "История и архив\n"
            "История хранит партии импорта. Последний импорт можно пакетно отменить, а старые партии — перенести в архивный GeoPackage.\n\n"
            "Мастер подготовки проекта для выезда\n"
            "Мастер проверяет CRS, геометрию, связь точек и кругов, несохранённые изменения, состав проекта и наличие оформления. "
            "После проверки можно экспортировать все или только выделенные скважины.\n\n"
            "Оформление в GeoPackage\n"
            "При включённой опции стиль точек и кругов сохраняется как стиль по умолчанию непосредственно внутри GeoPackage. "
            "Дополнительно может создаваться отдельный .qgz с относительными путями и README."
        )
