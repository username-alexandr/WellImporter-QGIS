# -*- coding: utf-8 -*-

from qgis.PyQt import QtCore, QtWidgets


class Ui_WellImporterDialog(object):
    def setupUi(self, Dialog):
        Dialog.setObjectName("WellImporterDialog")
        Dialog.resize(620, 520)

        self.verticalLayout = QtWidgets.QVBoxLayout(Dialog)

        self.lblTitle = QtWidgets.QLabel(Dialog)
        self.lblTitle.setText("<b style='font-size:18px'>Well Importer</b><br>Импорт скважин и построение площадных кругов")
        self.lblTitle.setWordWrap(True)
        self.verticalLayout.addWidget(self.lblTitle)

        self.formLayout = QtWidgets.QGridLayout()

        self.lblYear = QtWidgets.QLabel("Год бурения")
        self.txtYear = QtWidgets.QLineEdit()
        self.formLayout.addWidget(self.lblYear, 0, 0)
        self.formLayout.addWidget(self.txtYear, 0, 1)

        self.lblArea = QtWidgets.QLabel("Площадь круга")
        self.spinArea = QtWidgets.QDoubleSpinBox()
        self.spinArea.setDecimals(4)
        self.spinArea.setMinimum(0.0001)
        self.spinArea.setMaximum(1000000000.0)
        self.spinArea.setValue(33.0)
        self.formLayout.addWidget(self.lblArea, 1, 0)
        self.formLayout.addWidget(self.spinArea, 1, 1)

        self.lblPoints = QtWidgets.QLabel("Слой скважин")
        self.cmbPoints = QtWidgets.QComboBox()
        self.formLayout.addWidget(self.lblPoints, 2, 0)
        self.formLayout.addWidget(self.cmbPoints, 2, 1)

        self.lblCircles = QtWidgets.QLabel("Слой площадных кругов")
        self.cmbCircles = QtWidgets.QComboBox()
        self.formLayout.addWidget(self.lblCircles, 3, 0)
        self.formLayout.addWidget(self.cmbCircles, 3, 1)

        self.chkSkipDuplicates = QtWidgets.QCheckBox("Пропускать дубли по номеру скважины")
        self.chkSkipDuplicates.setChecked(True)
        self.formLayout.addWidget(self.chkSkipDuplicates, 4, 0, 1, 2)

        self.verticalLayout.addLayout(self.formLayout)

        self.lblFormat = QtWidgets.QLabel(
            "Формат данных в буфере Excel: <b>X | Y | Номер скважины</b><br>"
            "Можно скопировать 3 столбца без заголовка или с заголовком в первой строке."
        )
        self.lblFormat.setWordWrap(True)
        self.verticalLayout.addWidget(self.lblFormat)

        self.btnRefreshLayers = QtWidgets.QPushButton("Обновить список слоёв")
        self.btnImport = QtWidgets.QPushButton("Импортировать из Excel")
        self.btnClose = QtWidgets.QPushButton("Закрыть")

        self.verticalLayout.addWidget(self.btnRefreshLayers)
        self.verticalLayout.addWidget(self.btnImport)
        self.verticalLayout.addWidget(self.btnClose)

        self.lblStatus = QtWidgets.QLabel("Готово")
        self.lblStatus.setWordWrap(True)
        self.verticalLayout.addWidget(self.lblStatus)

        QtCore.QMetaObject.connectSlotsByName(Dialog)
