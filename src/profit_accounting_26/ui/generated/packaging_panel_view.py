# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file '_packaging_clean.ui'
##
## Created by: Qt User Interface Compiler version 6.11.1
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide6.QtCore import (QCoreApplication, QDate, QDateTime, QLocale,
    QMetaObject, QObject, QPoint, QRect,
    QSize, QTime, QUrl, Qt)
from PySide6.QtGui import (QBrush, QColor, QConicalGradient, QCursor,
    QFont, QFontDatabase, QGradient, QIcon,
    QImage, QKeySequence, QLinearGradient, QPainter,
    QPalette, QPixmap, QRadialGradient, QTransform)
from PySide6.QtWidgets import (QAbstractSpinBox, QApplication, QDoubleSpinBox, QFrame,
    QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QRadioButton, QSizePolicy, QTextEdit, QWidget)
class Ui_PackagingPanel(object):
    def setupUi(self, packagingPanel):
        if not packagingPanel.objectName():
            packagingPanel.setObjectName(u"packagingPanel")
        self.packagingPanelLayout = QHBoxLayout(packagingPanel)
        self.packagingPanelLayout.setSpacing(0)
        self.packagingPanelLayout.setObjectName(u"packagingPanelLayout")
        self.packagingPanelLayout.setContentsMargins(0, 0, 0, 0)
        self.normalPackageCard = QFrame(packagingPanel)
        self.normalPackageCard.setObjectName(u"normalPackageCard")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        sizePolicy.setHorizontalStretch(1)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.normalPackageCard.sizePolicy().hasHeightForWidth())
        self.normalPackageCard.setSizePolicy(sizePolicy)
        self.normalPackageCard.setMinimumSize(QSize(205, 0))
        self.normalPackageLayout = QGridLayout(self.normalPackageCard)
        self.normalPackageLayout.setSpacing(5)
        self.normalPackageLayout.setObjectName(u"normalPackageLayout")
        self.normalPackageLayout.setContentsMargins(8, 8, 8, 8)
        self.radioNormalPackage = QRadioButton(self.normalPackageCard)
        self.radioNormalPackage.setObjectName(u"radioNormalPackage")
        self.radioNormalPackage.setChecked(True)

        self.normalPackageLayout.addWidget(self.radioNormalPackage, 0, 0, 1, 3)

        self.txtNormalReminder = QTextEdit(self.normalPackageCard)
        self.txtNormalReminder.setObjectName(u"txtNormalReminder")
        sizePolicy1 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.txtNormalReminder.sizePolicy().hasHeightForWidth())
        self.txtNormalReminder.setSizePolicy(sizePolicy1)
        self.txtNormalReminder.setMinimumSize(QSize(90, 52))
        self.txtNormalReminder.setMaximumSize(QSize(16777215, 52))
        self.txtNormalReminder.setReadOnly(True)

        self.normalPackageLayout.addWidget(self.txtNormalReminder, 1, 0, 1, 3)

        self.lblNormalDims = QLabel(self.normalPackageCard)
        self.lblNormalDims.setObjectName(u"lblNormalDims")

        self.normalPackageLayout.addWidget(self.lblNormalDims, 2, 0, 1, 3)

        self.layout_spinNormalLengthCm = QHBoxLayout()
        self.layout_spinNormalLengthCm.setSpacing(0)
        self.layout_spinNormalLengthCm.setObjectName(u"layout_spinNormalLengthCm")
        self.layout_spinNormalLengthCm.setContentsMargins(0, 0, 0, 0)
        self.lblNormalLengthCm = QLabel(self.normalPackageCard)
        self.lblNormalLengthCm.setObjectName(u"lblNormalLengthCm")
        sizePolicy2 = QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        sizePolicy2.setHorizontalStretch(0)
        sizePolicy2.setVerticalStretch(0)
        sizePolicy2.setHeightForWidth(self.lblNormalLengthCm.sizePolicy().hasHeightForWidth())
        self.lblNormalLengthCm.setSizePolicy(sizePolicy2)
        self.lblNormalLengthCm.setMinimumSize(QSize(20, 0))
        self.lblNormalLengthCm.setMaximumSize(QSize(24, 16777215))
        self.lblNormalLengthCm.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.layout_spinNormalLengthCm.addWidget(self.lblNormalLengthCm)

        self.spinNormalLengthCm = QDoubleSpinBox(self.normalPackageCard)
        self.spinNormalLengthCm.setObjectName(u"spinNormalLengthCm")
        sizePolicy1.setHeightForWidth(self.spinNormalLengthCm.sizePolicy().hasHeightForWidth())
        self.spinNormalLengthCm.setSizePolicy(sizePolicy1)
        self.spinNormalLengthCm.setMinimumSize(QSize(45, 28))
        self.spinNormalLengthCm.setMaximumSize(QSize(72, 30))
        self.spinNormalLengthCm.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.spinNormalLengthCm.setDecimals(1)
        self.spinNormalLengthCm.setMinimum(0.000000000000000)
        self.spinNormalLengthCm.setMaximum(999.000000000000000)
        self.spinNormalLengthCm.setSingleStep(1.000000000000000)
        self.spinNormalLengthCm.setValue(47.000000000000000)

        self.layout_spinNormalLengthCm.addWidget(self.spinNormalLengthCm)

        self.unit_spinNormalLengthCm = QLabel(self.normalPackageCard)
        self.unit_spinNormalLengthCm.setObjectName(u"unit_spinNormalLengthCm")
        self.unit_spinNormalLengthCm.setMinimumSize(QSize(22, 0))
        self.unit_spinNormalLengthCm.setMaximumSize(QSize(28, 16777215))
        self.unit_spinNormalLengthCm.setVisible(False)
        self.unit_spinNormalLengthCm.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.layout_spinNormalLengthCm.addWidget(self.unit_spinNormalLengthCm)


        self.normalPackageLayout.addLayout(self.layout_spinNormalLengthCm, 3, 0, 1, 1)

        self.layout_spinNormalWidthCm = QHBoxLayout()
        self.layout_spinNormalWidthCm.setSpacing(0)
        self.layout_spinNormalWidthCm.setObjectName(u"layout_spinNormalWidthCm")
        self.layout_spinNormalWidthCm.setContentsMargins(0, 0, 0, 0)
        self.lblNormalWidthCm = QLabel(self.normalPackageCard)
        self.lblNormalWidthCm.setObjectName(u"lblNormalWidthCm")
        sizePolicy2.setHeightForWidth(self.lblNormalWidthCm.sizePolicy().hasHeightForWidth())
        self.lblNormalWidthCm.setSizePolicy(sizePolicy2)
        self.lblNormalWidthCm.setMinimumSize(QSize(20, 0))
        self.lblNormalWidthCm.setMaximumSize(QSize(24, 16777215))
        self.lblNormalWidthCm.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.layout_spinNormalWidthCm.addWidget(self.lblNormalWidthCm)

        self.spinNormalWidthCm = QDoubleSpinBox(self.normalPackageCard)
        self.spinNormalWidthCm.setObjectName(u"spinNormalWidthCm")
        sizePolicy1.setHeightForWidth(self.spinNormalWidthCm.sizePolicy().hasHeightForWidth())
        self.spinNormalWidthCm.setSizePolicy(sizePolicy1)
        self.spinNormalWidthCm.setMinimumSize(QSize(45, 28))
        self.spinNormalWidthCm.setMaximumSize(QSize(72, 30))
        self.spinNormalWidthCm.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.spinNormalWidthCm.setDecimals(1)
        self.spinNormalWidthCm.setMinimum(0.000000000000000)
        self.spinNormalWidthCm.setMaximum(999.000000000000000)
        self.spinNormalWidthCm.setSingleStep(1.000000000000000)
        self.spinNormalWidthCm.setValue(32.000000000000000)

        self.layout_spinNormalWidthCm.addWidget(self.spinNormalWidthCm)

        self.unit_spinNormalWidthCm = QLabel(self.normalPackageCard)
        self.unit_spinNormalWidthCm.setObjectName(u"unit_spinNormalWidthCm")
        self.unit_spinNormalWidthCm.setMinimumSize(QSize(22, 0))
        self.unit_spinNormalWidthCm.setMaximumSize(QSize(28, 16777215))
        self.unit_spinNormalWidthCm.setVisible(False)
        self.unit_spinNormalWidthCm.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.layout_spinNormalWidthCm.addWidget(self.unit_spinNormalWidthCm)


        self.normalPackageLayout.addLayout(self.layout_spinNormalWidthCm, 3, 1, 1, 1)

        self.layout_spinNormalHeightCm = QHBoxLayout()
        self.layout_spinNormalHeightCm.setSpacing(0)
        self.layout_spinNormalHeightCm.setObjectName(u"layout_spinNormalHeightCm")
        self.layout_spinNormalHeightCm.setContentsMargins(0, 0, 0, 0)
        self.lblNormalHeightCm = QLabel(self.normalPackageCard)
        self.lblNormalHeightCm.setObjectName(u"lblNormalHeightCm")
        sizePolicy2.setHeightForWidth(self.lblNormalHeightCm.sizePolicy().hasHeightForWidth())
        self.lblNormalHeightCm.setSizePolicy(sizePolicy2)
        self.lblNormalHeightCm.setMinimumSize(QSize(20, 0))
        self.lblNormalHeightCm.setMaximumSize(QSize(24, 16777215))
        self.lblNormalHeightCm.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.layout_spinNormalHeightCm.addWidget(self.lblNormalHeightCm)

        self.spinNormalHeightCm = QDoubleSpinBox(self.normalPackageCard)
        self.spinNormalHeightCm.setObjectName(u"spinNormalHeightCm")
        sizePolicy1.setHeightForWidth(self.spinNormalHeightCm.sizePolicy().hasHeightForWidth())
        self.spinNormalHeightCm.setSizePolicy(sizePolicy1)
        self.spinNormalHeightCm.setMinimumSize(QSize(45, 28))
        self.spinNormalHeightCm.setMaximumSize(QSize(72, 30))
        self.spinNormalHeightCm.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.spinNormalHeightCm.setDecimals(1)
        self.spinNormalHeightCm.setMinimum(0.000000000000000)
        self.spinNormalHeightCm.setMaximum(999.000000000000000)
        self.spinNormalHeightCm.setSingleStep(1.000000000000000)
        self.spinNormalHeightCm.setValue(17.000000000000000)

        self.layout_spinNormalHeightCm.addWidget(self.spinNormalHeightCm)

        self.unit_spinNormalHeightCm = QLabel(self.normalPackageCard)
        self.unit_spinNormalHeightCm.setObjectName(u"unit_spinNormalHeightCm")
        self.unit_spinNormalHeightCm.setMinimumSize(QSize(22, 0))
        self.unit_spinNormalHeightCm.setMaximumSize(QSize(28, 16777215))
        self.unit_spinNormalHeightCm.setVisible(False)
        self.unit_spinNormalHeightCm.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.layout_spinNormalHeightCm.addWidget(self.unit_spinNormalHeightCm)


        self.normalPackageLayout.addLayout(self.layout_spinNormalHeightCm, 3, 2, 1, 1)

        self.lblNormalWeight = QLabel(self.normalPackageCard)
        self.lblNormalWeight.setObjectName(u"lblNormalWeight")

        self.normalPackageLayout.addWidget(self.lblNormalWeight, 4, 0, 1, 1)

        self.layout_spinNormalWeightG = QHBoxLayout()
        self.layout_spinNormalWeightG.setSpacing(6)
        self.layout_spinNormalWeightG.setObjectName(u"layout_spinNormalWeightG")
        self.layout_spinNormalWeightG.setContentsMargins(0, 0, 0, 0)
        self.spinNormalWeightG = QDoubleSpinBox(self.normalPackageCard)
        self.spinNormalWeightG.setObjectName(u"spinNormalWeightG")
        self.spinNormalWeightG.setMinimumSize(QSize(110, 28))
        self.spinNormalWeightG.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.spinNormalWeightG.setDecimals(0)
        self.spinNormalWeightG.setMinimum(0.000000000000000)
        self.spinNormalWeightG.setMaximum(999999.000000000000000)
        self.spinNormalWeightG.setSingleStep(1.000000000000000)
        self.spinNormalWeightG.setValue(720.000000000000000)

        self.layout_spinNormalWeightG.addWidget(self.spinNormalWeightG)

        self.unit_spinNormalWeightG = QLabel(self.normalPackageCard)
        self.unit_spinNormalWeightG.setObjectName(u"unit_spinNormalWeightG")
        self.unit_spinNormalWeightG.setMinimumSize(QSize(28, 0))
        self.unit_spinNormalWeightG.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.layout_spinNormalWeightG.addWidget(self.unit_spinNormalWeightG)


        self.normalPackageLayout.addLayout(self.layout_spinNormalWeightG, 4, 1, 1, 2)

        self.normalPackageLayout.setColumnStretch(0, 1)
        self.normalPackageLayout.setColumnStretch(1, 1)
        self.normalPackageLayout.setColumnStretch(2, 1)

        self.packagingPanelLayout.addWidget(self.normalPackageCard)

        self.conservativePackageCard = QFrame(packagingPanel)
        self.conservativePackageCard.setObjectName(u"conservativePackageCard")
        sizePolicy.setHeightForWidth(self.conservativePackageCard.sizePolicy().hasHeightForWidth())
        self.conservativePackageCard.setSizePolicy(sizePolicy)
        self.conservativePackageCard.setMinimumSize(QSize(205, 0))
        self.conservativePackageLayout = QGridLayout(self.conservativePackageCard)
        self.conservativePackageLayout.setSpacing(5)
        self.conservativePackageLayout.setObjectName(u"conservativePackageLayout")
        self.conservativePackageLayout.setContentsMargins(8, 8, 8, 8)
        self.radioConservativePackage = QRadioButton(self.conservativePackageCard)
        self.radioConservativePackage.setObjectName(u"radioConservativePackage")

        self.conservativePackageLayout.addWidget(self.radioConservativePackage, 0, 0, 1, 3)

        self.lblConservativeMethod = QLabel(self.conservativePackageCard)
        self.lblConservativeMethod.setObjectName(u"lblConservativeMethod")

        self.conservativePackageLayout.addWidget(self.lblConservativeMethod, 1, 0, 1, 1)

        self.txtConservativeMethod = QLineEdit(self.conservativePackageCard)
        self.txtConservativeMethod.setObjectName(u"txtConservativeMethod")
        sizePolicy1.setHeightForWidth(self.txtConservativeMethod.sizePolicy().hasHeightForWidth())
        self.txtConservativeMethod.setSizePolicy(sizePolicy1)
        self.txtConservativeMethod.setMinimumSize(QSize(90, 28))
        self.txtConservativeMethod.setReadOnly(True)

        self.conservativePackageLayout.addWidget(self.txtConservativeMethod, 1, 1, 1, 2)

        self.lblConservativeDims = QLabel(self.conservativePackageCard)
        self.lblConservativeDims.setObjectName(u"lblConservativeDims")

        self.conservativePackageLayout.addWidget(self.lblConservativeDims, 2, 0, 1, 3)

        self.layout_spinConservativeLengthCm = QHBoxLayout()
        self.layout_spinConservativeLengthCm.setSpacing(0)
        self.layout_spinConservativeLengthCm.setObjectName(u"layout_spinConservativeLengthCm")
        self.layout_spinConservativeLengthCm.setContentsMargins(0, 0, 0, 0)
        self.lblConservativeLengthCm = QLabel(self.conservativePackageCard)
        self.lblConservativeLengthCm.setObjectName(u"lblConservativeLengthCm")
        sizePolicy2.setHeightForWidth(self.lblConservativeLengthCm.sizePolicy().hasHeightForWidth())
        self.lblConservativeLengthCm.setSizePolicy(sizePolicy2)
        self.lblConservativeLengthCm.setMinimumSize(QSize(20, 0))
        self.lblConservativeLengthCm.setMaximumSize(QSize(24, 16777215))
        self.lblConservativeLengthCm.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.layout_spinConservativeLengthCm.addWidget(self.lblConservativeLengthCm)

        self.spinConservativeLengthCm = QDoubleSpinBox(self.conservativePackageCard)
        self.spinConservativeLengthCm.setObjectName(u"spinConservativeLengthCm")
        sizePolicy1.setHeightForWidth(self.spinConservativeLengthCm.sizePolicy().hasHeightForWidth())
        self.spinConservativeLengthCm.setSizePolicy(sizePolicy1)
        self.spinConservativeLengthCm.setMinimumSize(QSize(45, 28))
        self.spinConservativeLengthCm.setMaximumSize(QSize(72, 30))
        self.spinConservativeLengthCm.setReadOnly(True)
        self.spinConservativeLengthCm.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.spinConservativeLengthCm.setDecimals(1)
        self.spinConservativeLengthCm.setMinimum(0.000000000000000)
        self.spinConservativeLengthCm.setMaximum(999.000000000000000)
        self.spinConservativeLengthCm.setSingleStep(1.000000000000000)
        self.spinConservativeLengthCm.setValue(49.000000000000000)

        self.layout_spinConservativeLengthCm.addWidget(self.spinConservativeLengthCm)

        self.unit_spinConservativeLengthCm = QLabel(self.conservativePackageCard)
        self.unit_spinConservativeLengthCm.setObjectName(u"unit_spinConservativeLengthCm")
        self.unit_spinConservativeLengthCm.setMinimumSize(QSize(22, 0))
        self.unit_spinConservativeLengthCm.setMaximumSize(QSize(28, 16777215))
        self.unit_spinConservativeLengthCm.setVisible(False)
        self.unit_spinConservativeLengthCm.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.layout_spinConservativeLengthCm.addWidget(self.unit_spinConservativeLengthCm)


        self.conservativePackageLayout.addLayout(self.layout_spinConservativeLengthCm, 3, 0, 1, 1)

        self.layout_spinConservativeWidthCm = QHBoxLayout()
        self.layout_spinConservativeWidthCm.setSpacing(0)
        self.layout_spinConservativeWidthCm.setObjectName(u"layout_spinConservativeWidthCm")
        self.layout_spinConservativeWidthCm.setContentsMargins(0, 0, 0, 0)
        self.lblConservativeWidthCm = QLabel(self.conservativePackageCard)
        self.lblConservativeWidthCm.setObjectName(u"lblConservativeWidthCm")
        sizePolicy2.setHeightForWidth(self.lblConservativeWidthCm.sizePolicy().hasHeightForWidth())
        self.lblConservativeWidthCm.setSizePolicy(sizePolicy2)
        self.lblConservativeWidthCm.setMinimumSize(QSize(20, 0))
        self.lblConservativeWidthCm.setMaximumSize(QSize(24, 16777215))
        self.lblConservativeWidthCm.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.layout_spinConservativeWidthCm.addWidget(self.lblConservativeWidthCm)

        self.spinConservativeWidthCm = QDoubleSpinBox(self.conservativePackageCard)
        self.spinConservativeWidthCm.setObjectName(u"spinConservativeWidthCm")
        sizePolicy1.setHeightForWidth(self.spinConservativeWidthCm.sizePolicy().hasHeightForWidth())
        self.spinConservativeWidthCm.setSizePolicy(sizePolicy1)
        self.spinConservativeWidthCm.setMinimumSize(QSize(45, 28))
        self.spinConservativeWidthCm.setMaximumSize(QSize(72, 30))
        self.spinConservativeWidthCm.setReadOnly(True)
        self.spinConservativeWidthCm.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.spinConservativeWidthCm.setDecimals(1)
        self.spinConservativeWidthCm.setMinimum(0.000000000000000)
        self.spinConservativeWidthCm.setMaximum(999.000000000000000)
        self.spinConservativeWidthCm.setSingleStep(1.000000000000000)
        self.spinConservativeWidthCm.setValue(34.000000000000000)

        self.layout_spinConservativeWidthCm.addWidget(self.spinConservativeWidthCm)

        self.unit_spinConservativeWidthCm = QLabel(self.conservativePackageCard)
        self.unit_spinConservativeWidthCm.setObjectName(u"unit_spinConservativeWidthCm")
        self.unit_spinConservativeWidthCm.setMinimumSize(QSize(22, 0))
        self.unit_spinConservativeWidthCm.setMaximumSize(QSize(28, 16777215))
        self.unit_spinConservativeWidthCm.setVisible(False)
        self.unit_spinConservativeWidthCm.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.layout_spinConservativeWidthCm.addWidget(self.unit_spinConservativeWidthCm)


        self.conservativePackageLayout.addLayout(self.layout_spinConservativeWidthCm, 3, 1, 1, 1)

        self.layout_spinConservativeHeightCm = QHBoxLayout()
        self.layout_spinConservativeHeightCm.setSpacing(0)
        self.layout_spinConservativeHeightCm.setObjectName(u"layout_spinConservativeHeightCm")
        self.layout_spinConservativeHeightCm.setContentsMargins(0, 0, 0, 0)
        self.lblConservativeHeightCm = QLabel(self.conservativePackageCard)
        self.lblConservativeHeightCm.setObjectName(u"lblConservativeHeightCm")
        sizePolicy2.setHeightForWidth(self.lblConservativeHeightCm.sizePolicy().hasHeightForWidth())
        self.lblConservativeHeightCm.setSizePolicy(sizePolicy2)
        self.lblConservativeHeightCm.setMinimumSize(QSize(20, 0))
        self.lblConservativeHeightCm.setMaximumSize(QSize(24, 16777215))
        self.lblConservativeHeightCm.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.layout_spinConservativeHeightCm.addWidget(self.lblConservativeHeightCm)

        self.spinConservativeHeightCm = QDoubleSpinBox(self.conservativePackageCard)
        self.spinConservativeHeightCm.setObjectName(u"spinConservativeHeightCm")
        sizePolicy1.setHeightForWidth(self.spinConservativeHeightCm.sizePolicy().hasHeightForWidth())
        self.spinConservativeHeightCm.setSizePolicy(sizePolicy1)
        self.spinConservativeHeightCm.setMinimumSize(QSize(45, 28))
        self.spinConservativeHeightCm.setMaximumSize(QSize(72, 30))
        self.spinConservativeHeightCm.setReadOnly(True)
        self.spinConservativeHeightCm.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.spinConservativeHeightCm.setDecimals(1)
        self.spinConservativeHeightCm.setMinimum(0.000000000000000)
        self.spinConservativeHeightCm.setMaximum(999.000000000000000)
        self.spinConservativeHeightCm.setSingleStep(1.000000000000000)
        self.spinConservativeHeightCm.setValue(19.000000000000000)

        self.layout_spinConservativeHeightCm.addWidget(self.spinConservativeHeightCm)

        self.unit_spinConservativeHeightCm = QLabel(self.conservativePackageCard)
        self.unit_spinConservativeHeightCm.setObjectName(u"unit_spinConservativeHeightCm")
        self.unit_spinConservativeHeightCm.setMinimumSize(QSize(22, 0))
        self.unit_spinConservativeHeightCm.setMaximumSize(QSize(28, 16777215))
        self.unit_spinConservativeHeightCm.setVisible(False)
        self.unit_spinConservativeHeightCm.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.layout_spinConservativeHeightCm.addWidget(self.unit_spinConservativeHeightCm)


        self.conservativePackageLayout.addLayout(self.layout_spinConservativeHeightCm, 3, 2, 1, 1)

        self.lblConservativeWeight = QLabel(self.conservativePackageCard)
        self.lblConservativeWeight.setObjectName(u"lblConservativeWeight")

        self.conservativePackageLayout.addWidget(self.lblConservativeWeight, 4, 0, 1, 1)

        self.layout_spinConservativeWeightG = QHBoxLayout()
        self.layout_spinConservativeWeightG.setSpacing(6)
        self.layout_spinConservativeWeightG.setObjectName(u"layout_spinConservativeWeightG")
        self.layout_spinConservativeWeightG.setContentsMargins(0, 0, 0, 0)
        self.spinConservativeWeightG = QDoubleSpinBox(self.conservativePackageCard)
        self.spinConservativeWeightG.setObjectName(u"spinConservativeWeightG")
        self.spinConservativeWeightG.setMinimumSize(QSize(110, 28))
        self.spinConservativeWeightG.setReadOnly(True)
        self.spinConservativeWeightG.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.spinConservativeWeightG.setDecimals(0)
        self.spinConservativeWeightG.setMinimum(0.000000000000000)
        self.spinConservativeWeightG.setMaximum(999999.000000000000000)
        self.spinConservativeWeightG.setSingleStep(1.000000000000000)
        self.spinConservativeWeightG.setValue(820.000000000000000)

        self.layout_spinConservativeWeightG.addWidget(self.spinConservativeWeightG)

        self.unit_spinConservativeWeightG = QLabel(self.conservativePackageCard)
        self.unit_spinConservativeWeightG.setObjectName(u"unit_spinConservativeWeightG")
        self.unit_spinConservativeWeightG.setMinimumSize(QSize(28, 0))
        self.unit_spinConservativeWeightG.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.layout_spinConservativeWeightG.addWidget(self.unit_spinConservativeWeightG)


        self.conservativePackageLayout.addLayout(self.layout_spinConservativeWeightG, 4, 1, 1, 2)

        self.conservativePackageLayout.setColumnStretch(0, 1)
        self.conservativePackageLayout.setColumnStretch(1, 1)
        self.conservativePackageLayout.setColumnStretch(2, 1)

        self.packagingPanelLayout.addWidget(self.conservativePackageCard)


        self.retranslateUi(packagingPanel)

        QMetaObject.connectSlotsByName(packagingPanel)
    # setupUi

        # --- restored dynamic properties ---
        self.normalPackageCard.setProperty("selected", True)
        self.txtNormalReminder.setProperty("verticalScrollBarPolicy", "Qt::ScrollBarPolicy::ScrollBarAlwaysOff")
        self.txtNormalReminder.setProperty("horizontalScrollBarPolicy", "Qt::ScrollBarPolicy::ScrollBarAlwaysOff")
        self.txtNormalReminder.setProperty("lineWrapMode", "QTextEdit::LineWrapMode::WidgetWidth")
        self.txtNormalReminder.setProperty("acceptRichText", False)
        self.txtNormalReminder.setProperty("preview", True)
        self.unit_spinNormalLengthCm.setProperty("unitLabel", True)
        self.unit_spinNormalWidthCm.setProperty("unitLabel", True)
        self.unit_spinNormalHeightCm.setProperty("unitLabel", True)
        self.unit_spinNormalWeightG.setProperty("unitLabel", True)
        self.normalPackageCard.setProperty("methodFrozen", True)
        self.txtConservativeMethod.setProperty("preview", True)
        self.spinConservativeLengthCm.setProperty("preview", True)
        self.unit_spinConservativeLengthCm.setProperty("unitLabel", True)
        self.spinConservativeWidthCm.setProperty("preview", True)
        self.unit_spinConservativeWidthCm.setProperty("unitLabel", True)
        self.spinConservativeHeightCm.setProperty("preview", True)
        self.unit_spinConservativeHeightCm.setProperty("unitLabel", True)
        self.spinConservativeWeightG.setProperty("preview", True)
        self.unit_spinConservativeWeightG.setProperty("unitLabel", True)
        self.conservativePackageCard.setProperty("frozen", True)

    def retranslateUi(self, packagingPanel):
        self.radioNormalPackage.setText(QCoreApplication.translate("PackagingPanel", u"\u6b63\u5e38\u6863\uff08\u5f53\u524d\u91c7\u7528\uff09", None))
        self.txtNormalReminder.setPlaceholderText(QCoreApplication.translate("PackagingPanel", u"\u6b63\u5e38\u6863\u5305\u88c5\u65b9\u5f0f\uff08\u7531 AI / CAL \u751f\u6210\uff09", None))
#if QT_CONFIG(tooltip)
        self.txtNormalReminder.setToolTip(QCoreApplication.translate("PackagingPanel", u"\u6b63\u5e38\u6863\u5305\u88c5\u65b9\u5f0f\u4e3a\u7cfb\u7edf\u751f\u6210\u7ed3\u679c\uff0c\u4e0d\u5728\u6b64\u5904\u76f4\u63a5\u7f16\u8f91\uff1b\u9884\u7559\u4e24\u884c\u663e\u793a\u7a7a\u95f4", None))
#endif // QT_CONFIG(tooltip)
        self.lblNormalDims.setText(QCoreApplication.translate("PackagingPanel", u"\u5305\u88c5\u5c3a\u5bf8\uff08\u9ed8\u8ba4 cm\uff09", None))
        self.lblNormalLengthCm.setText(QCoreApplication.translate("PackagingPanel", u"\u957f", None))
        self.unit_spinNormalLengthCm.setText("")
        self.lblNormalWidthCm.setText(QCoreApplication.translate("PackagingPanel", u"\u5bbd", None))
        self.unit_spinNormalWidthCm.setText("")
        self.lblNormalHeightCm.setText(QCoreApplication.translate("PackagingPanel", u"\u9ad8", None))
        self.unit_spinNormalHeightCm.setText("")
        self.lblNormalWeight.setText(QCoreApplication.translate("PackagingPanel", u"\u5305\u88c5\u540e\u91cd\u91cf", None))
        self.unit_spinNormalWeightG.setText(QCoreApplication.translate("PackagingPanel", u"g", None))
        self.radioConservativePackage.setText(QCoreApplication.translate("PackagingPanel", u"\u4fdd\u5b88\u6863", None))
        self.lblConservativeMethod.setText(QCoreApplication.translate("PackagingPanel", u"\u5305\u88c5\u65b9\u5f0f\uff08\u51bb\u7ed3\uff09", None))
        self.txtConservativeMethod.setText("")
        self.txtConservativeMethod.setPlaceholderText(QCoreApplication.translate("PackagingPanel", u"\u4fdd\u5b88\u6863\u5305\u88c5\u65b9\u5f0f\uff08\u7531 AI / CAL \u751f\u6210\uff09", None))
#if QT_CONFIG(tooltip)
        self.txtConservativeMethod.setToolTip(QCoreApplication.translate("PackagingPanel", u"\u4fdd\u5b88\u6863\u6574\u4f53\u4e3a\u51bb\u7ed3\u7ed3\u679c\uff1b\u53ef\u9009\u62e9\u91c7\u7528\uff0c\u4f46\u4e0d\u53ef\u76f4\u63a5\u7f16\u8f91\u5b57\u6bb5", None))
#endif // QT_CONFIG(tooltip)
        self.lblConservativeDims.setText(QCoreApplication.translate("PackagingPanel", u"\u5305\u88c5\u5c3a\u5bf8\uff08\u9ed8\u8ba4 cm\uff09", None))
        self.lblConservativeLengthCm.setText(QCoreApplication.translate("PackagingPanel", u"\u957f", None))
#if QT_CONFIG(tooltip)
        self.spinConservativeLengthCm.setToolTip(QCoreApplication.translate("PackagingPanel", u"\u4fdd\u5b88\u6863\u4e3a\u51bb\u7ed3\u4f30\u7b97\u7ed3\u679c\uff0c\u4e0d\u53ef\u76f4\u63a5\u7f16\u8f91", None))
#endif // QT_CONFIG(tooltip)
        self.unit_spinConservativeLengthCm.setText("")
        self.lblConservativeWidthCm.setText(QCoreApplication.translate("PackagingPanel", u"\u5bbd", None))
#if QT_CONFIG(tooltip)
        self.spinConservativeWidthCm.setToolTip(QCoreApplication.translate("PackagingPanel", u"\u4fdd\u5b88\u6863\u4e3a\u51bb\u7ed3\u4f30\u7b97\u7ed3\u679c\uff0c\u4e0d\u53ef\u76f4\u63a5\u7f16\u8f91", None))
#endif // QT_CONFIG(tooltip)
        self.unit_spinConservativeWidthCm.setText("")
        self.lblConservativeHeightCm.setText(QCoreApplication.translate("PackagingPanel", u"\u9ad8", None))
#if QT_CONFIG(tooltip)
        self.spinConservativeHeightCm.setToolTip(QCoreApplication.translate("PackagingPanel", u"\u4fdd\u5b88\u6863\u4e3a\u51bb\u7ed3\u4f30\u7b97\u7ed3\u679c\uff0c\u4e0d\u53ef\u76f4\u63a5\u7f16\u8f91", None))
#endif // QT_CONFIG(tooltip)
        self.unit_spinConservativeHeightCm.setText("")
        self.lblConservativeWeight.setText(QCoreApplication.translate("PackagingPanel", u"\u5305\u88c5\u540e\u91cd\u91cf", None))
#if QT_CONFIG(tooltip)
        self.spinConservativeWeightG.setToolTip(QCoreApplication.translate("PackagingPanel", u"\u4fdd\u5b88\u6863\u4e3a\u51bb\u7ed3\u4f30\u7b97\u7ed3\u679c\uff0c\u4e0d\u53ef\u76f4\u63a5\u7f16\u8f91", None))
#endif // QT_CONFIG(tooltip)
        self.unit_spinConservativeWeightG.setText(QCoreApplication.translate("PackagingPanel", u"g", None))
        pass
    # retranslateUi

