# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file '_product_cost_clean.ui'
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
    QGridLayout, QHBoxLayout, QLabel, QSizePolicy,
    QWidget)
class Ui_ProductCostPanel(object):
    def setupUi(self, productCostPanel):
        if not productCostPanel.objectName():
            productCostPanel.setObjectName(u"productCostPanel")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        sizePolicy.setHorizontalStretch(1)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(productCostPanel.sizePolicy().hasHeightForWidth())
        productCostPanel.setSizePolicy(sizePolicy)
        productCostPanel.setMinimumSize(QSize(205, 0))
        self.bareProductLayout = QGridLayout(productCostPanel)
        self.bareProductLayout.setSpacing(5)
        self.bareProductLayout.setObjectName(u"bareProductLayout")
        self.bareProductLayout.setContentsMargins(8, 8, 8, 8)
        self.lblBareProductTitle = QLabel(productCostPanel)
        self.lblBareProductTitle.setObjectName(u"lblBareProductTitle")

        self.bareProductLayout.addWidget(self.lblBareProductTitle, 0, 0, 1, 3)

        self.lblProductCost = QLabel(productCostPanel)
        self.lblProductCost.setObjectName(u"lblProductCost")

        self.bareProductLayout.addWidget(self.lblProductCost, 1, 0, 1, 1)

        self.layout_spinProductCostRmb = QHBoxLayout()
        self.layout_spinProductCostRmb.setSpacing(6)
        self.layout_spinProductCostRmb.setObjectName(u"layout_spinProductCostRmb")
        self.layout_spinProductCostRmb.setContentsMargins(0, 0, 0, 0)
        self.spinProductCostRmb = QDoubleSpinBox(productCostPanel)
        self.spinProductCostRmb.setObjectName(u"spinProductCostRmb")
        self.spinProductCostRmb.setMinimumSize(QSize(110, 28))
        self.spinProductCostRmb.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.spinProductCostRmb.setDecimals(2)
        self.spinProductCostRmb.setMinimum(0.000000000000000)
        self.spinProductCostRmb.setMaximum(999999.000000000000000)
        self.spinProductCostRmb.setSingleStep(1.000000000000000)
        self.spinProductCostRmb.setValue(18.800000000000001)

        self.layout_spinProductCostRmb.addWidget(self.spinProductCostRmb)

        self.unit_spinProductCostRmb = QLabel(productCostPanel)
        self.unit_spinProductCostRmb.setObjectName(u"unit_spinProductCostRmb")
        self.unit_spinProductCostRmb.setMinimumSize(QSize(36, 0))
        self.unit_spinProductCostRmb.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.layout_spinProductCostRmb.addWidget(self.unit_spinProductCostRmb)


        self.bareProductLayout.addLayout(self.layout_spinProductCostRmb, 1, 1, 1, 2)

        self.lblDomesticFreight = QLabel(productCostPanel)
        self.lblDomesticFreight.setObjectName(u"lblDomesticFreight")

        self.bareProductLayout.addWidget(self.lblDomesticFreight, 2, 0, 1, 1)

        self.layout_spinDomesticFreightRmb = QHBoxLayout()
        self.layout_spinDomesticFreightRmb.setSpacing(6)
        self.layout_spinDomesticFreightRmb.setObjectName(u"layout_spinDomesticFreightRmb")
        self.layout_spinDomesticFreightRmb.setContentsMargins(0, 0, 0, 0)
        self.spinDomesticFreightRmb = QDoubleSpinBox(productCostPanel)
        self.spinDomesticFreightRmb.setObjectName(u"spinDomesticFreightRmb")
        self.spinDomesticFreightRmb.setMinimumSize(QSize(110, 28))
        self.spinDomesticFreightRmb.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.spinDomesticFreightRmb.setDecimals(2)
        self.spinDomesticFreightRmb.setMinimum(0.000000000000000)
        self.spinDomesticFreightRmb.setMaximum(999999.000000000000000)
        self.spinDomesticFreightRmb.setSingleStep(1.000000000000000)
        self.spinDomesticFreightRmb.setValue(5.000000000000000)

        self.layout_spinDomesticFreightRmb.addWidget(self.spinDomesticFreightRmb)

        self.unit_spinDomesticFreightRmb = QLabel(productCostPanel)
        self.unit_spinDomesticFreightRmb.setObjectName(u"unit_spinDomesticFreightRmb")
        self.unit_spinDomesticFreightRmb.setMinimumSize(QSize(36, 0))
        self.unit_spinDomesticFreightRmb.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.layout_spinDomesticFreightRmb.addWidget(self.unit_spinDomesticFreightRmb)


        self.bareProductLayout.addLayout(self.layout_spinDomesticFreightRmb, 2, 1, 1, 2)

        self.lblBareDimensionsTitle = QLabel(productCostPanel)
        self.lblBareDimensionsTitle.setObjectName(u"lblBareDimensionsTitle")

        self.bareProductLayout.addWidget(self.lblBareDimensionsTitle, 3, 0, 1, 3)

        self.layout_spinBareLengthCm = QHBoxLayout()
        self.layout_spinBareLengthCm.setSpacing(0)
        self.layout_spinBareLengthCm.setObjectName(u"layout_spinBareLengthCm")
        self.layout_spinBareLengthCm.setContentsMargins(0, 0, 0, 0)
        self.lblBareLengthCm = QLabel(productCostPanel)
        self.lblBareLengthCm.setObjectName(u"lblBareLengthCm")
        sizePolicy1 = QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.lblBareLengthCm.sizePolicy().hasHeightForWidth())
        self.lblBareLengthCm.setSizePolicy(sizePolicy1)
        self.lblBareLengthCm.setMinimumSize(QSize(20, 0))
        self.lblBareLengthCm.setMaximumSize(QSize(24, 16777215))
        self.lblBareLengthCm.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.layout_spinBareLengthCm.addWidget(self.lblBareLengthCm)

        self.spinBareLengthCm = QDoubleSpinBox(productCostPanel)
        self.spinBareLengthCm.setObjectName(u"spinBareLengthCm")
        sizePolicy2 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        sizePolicy2.setHorizontalStretch(0)
        sizePolicy2.setVerticalStretch(0)
        sizePolicy2.setHeightForWidth(self.spinBareLengthCm.sizePolicy().hasHeightForWidth())
        self.spinBareLengthCm.setSizePolicy(sizePolicy2)
        self.spinBareLengthCm.setMinimumSize(QSize(45, 28))
        self.spinBareLengthCm.setMaximumSize(QSize(72, 30))
        self.spinBareLengthCm.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.spinBareLengthCm.setDecimals(1)
        self.spinBareLengthCm.setMinimum(0.000000000000000)
        self.spinBareLengthCm.setMaximum(999.000000000000000)
        self.spinBareLengthCm.setSingleStep(1.000000000000000)
        self.spinBareLengthCm.setValue(45.000000000000000)

        self.layout_spinBareLengthCm.addWidget(self.spinBareLengthCm)

        self.unit_spinBareLengthCm = QLabel(productCostPanel)
        self.unit_spinBareLengthCm.setObjectName(u"unit_spinBareLengthCm")
        self.unit_spinBareLengthCm.setMinimumSize(QSize(22, 0))
        self.unit_spinBareLengthCm.setMaximumSize(QSize(28, 16777215))
        self.unit_spinBareLengthCm.setVisible(False)
        self.unit_spinBareLengthCm.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.layout_spinBareLengthCm.addWidget(self.unit_spinBareLengthCm)


        self.bareProductLayout.addLayout(self.layout_spinBareLengthCm, 4, 0, 1, 1)

        self.layout_spinBareWidthCm = QHBoxLayout()
        self.layout_spinBareWidthCm.setSpacing(0)
        self.layout_spinBareWidthCm.setObjectName(u"layout_spinBareWidthCm")
        self.layout_spinBareWidthCm.setContentsMargins(0, 0, 0, 0)
        self.lblBareWidthCm = QLabel(productCostPanel)
        self.lblBareWidthCm.setObjectName(u"lblBareWidthCm")
        sizePolicy1.setHeightForWidth(self.lblBareWidthCm.sizePolicy().hasHeightForWidth())
        self.lblBareWidthCm.setSizePolicy(sizePolicy1)
        self.lblBareWidthCm.setMinimumSize(QSize(20, 0))
        self.lblBareWidthCm.setMaximumSize(QSize(24, 16777215))
        self.lblBareWidthCm.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.layout_spinBareWidthCm.addWidget(self.lblBareWidthCm)

        self.spinBareWidthCm = QDoubleSpinBox(productCostPanel)
        self.spinBareWidthCm.setObjectName(u"spinBareWidthCm")
        sizePolicy2.setHeightForWidth(self.spinBareWidthCm.sizePolicy().hasHeightForWidth())
        self.spinBareWidthCm.setSizePolicy(sizePolicy2)
        self.spinBareWidthCm.setMinimumSize(QSize(45, 28))
        self.spinBareWidthCm.setMaximumSize(QSize(72, 30))
        self.spinBareWidthCm.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.spinBareWidthCm.setDecimals(1)
        self.spinBareWidthCm.setMinimum(0.000000000000000)
        self.spinBareWidthCm.setMaximum(999.000000000000000)
        self.spinBareWidthCm.setSingleStep(1.000000000000000)
        self.spinBareWidthCm.setValue(30.000000000000000)

        self.layout_spinBareWidthCm.addWidget(self.spinBareWidthCm)

        self.unit_spinBareWidthCm = QLabel(productCostPanel)
        self.unit_spinBareWidthCm.setObjectName(u"unit_spinBareWidthCm")
        self.unit_spinBareWidthCm.setMinimumSize(QSize(22, 0))
        self.unit_spinBareWidthCm.setMaximumSize(QSize(28, 16777215))
        self.unit_spinBareWidthCm.setVisible(False)
        self.unit_spinBareWidthCm.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.layout_spinBareWidthCm.addWidget(self.unit_spinBareWidthCm)


        self.bareProductLayout.addLayout(self.layout_spinBareWidthCm, 4, 1, 1, 1)

        self.layout_spinBareHeightCm = QHBoxLayout()
        self.layout_spinBareHeightCm.setSpacing(0)
        self.layout_spinBareHeightCm.setObjectName(u"layout_spinBareHeightCm")
        self.layout_spinBareHeightCm.setContentsMargins(0, 0, 0, 0)
        self.lblBareHeightCm = QLabel(productCostPanel)
        self.lblBareHeightCm.setObjectName(u"lblBareHeightCm")
        sizePolicy1.setHeightForWidth(self.lblBareHeightCm.sizePolicy().hasHeightForWidth())
        self.lblBareHeightCm.setSizePolicy(sizePolicy1)
        self.lblBareHeightCm.setMinimumSize(QSize(20, 0))
        self.lblBareHeightCm.setMaximumSize(QSize(24, 16777215))
        self.lblBareHeightCm.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.layout_spinBareHeightCm.addWidget(self.lblBareHeightCm)

        self.spinBareHeightCm = QDoubleSpinBox(productCostPanel)
        self.spinBareHeightCm.setObjectName(u"spinBareHeightCm")
        sizePolicy2.setHeightForWidth(self.spinBareHeightCm.sizePolicy().hasHeightForWidth())
        self.spinBareHeightCm.setSizePolicy(sizePolicy2)
        self.spinBareHeightCm.setMinimumSize(QSize(45, 28))
        self.spinBareHeightCm.setMaximumSize(QSize(72, 30))
        self.spinBareHeightCm.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.spinBareHeightCm.setDecimals(1)
        self.spinBareHeightCm.setMinimum(0.000000000000000)
        self.spinBareHeightCm.setMaximum(999.000000000000000)
        self.spinBareHeightCm.setSingleStep(1.000000000000000)
        self.spinBareHeightCm.setValue(15.000000000000000)

        self.layout_spinBareHeightCm.addWidget(self.spinBareHeightCm)

        self.unit_spinBareHeightCm = QLabel(productCostPanel)
        self.unit_spinBareHeightCm.setObjectName(u"unit_spinBareHeightCm")
        self.unit_spinBareHeightCm.setMinimumSize(QSize(22, 0))
        self.unit_spinBareHeightCm.setMaximumSize(QSize(28, 16777215))
        self.unit_spinBareHeightCm.setVisible(False)
        self.unit_spinBareHeightCm.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.layout_spinBareHeightCm.addWidget(self.unit_spinBareHeightCm)


        self.bareProductLayout.addLayout(self.layout_spinBareHeightCm, 4, 2, 1, 1)

        self.lblBareWeight = QLabel(productCostPanel)
        self.lblBareWeight.setObjectName(u"lblBareWeight")

        self.bareProductLayout.addWidget(self.lblBareWeight, 5, 0, 1, 1)

        self.layout_spinBareWeightG = QHBoxLayout()
        self.layout_spinBareWeightG.setSpacing(6)
        self.layout_spinBareWeightG.setObjectName(u"layout_spinBareWeightG")
        self.layout_spinBareWeightG.setContentsMargins(0, 0, 0, 0)
        self.spinBareWeightG = QDoubleSpinBox(productCostPanel)
        self.spinBareWeightG.setObjectName(u"spinBareWeightG")
        self.spinBareWeightG.setMinimumSize(QSize(110, 28))
        self.spinBareWeightG.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.spinBareWeightG.setDecimals(0)
        self.spinBareWeightG.setMinimum(0.000000000000000)
        self.spinBareWeightG.setMaximum(999999.000000000000000)
        self.spinBareWeightG.setSingleStep(1.000000000000000)
        self.spinBareWeightG.setValue(580.000000000000000)

        self.layout_spinBareWeightG.addWidget(self.spinBareWeightG)

        self.unit_spinBareWeightG = QLabel(productCostPanel)
        self.unit_spinBareWeightG.setObjectName(u"unit_spinBareWeightG")
        self.unit_spinBareWeightG.setMinimumSize(QSize(28, 0))
        self.unit_spinBareWeightG.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.layout_spinBareWeightG.addWidget(self.unit_spinBareWeightG)


        self.bareProductLayout.addLayout(self.layout_spinBareWeightG, 5, 1, 1, 2)

        self.bareProductLayout.setColumnStretch(0, 1)
        self.bareProductLayout.setColumnStretch(1, 1)
        self.bareProductLayout.setColumnStretch(2, 1)

        self.retranslateUi(productCostPanel)

        QMetaObject.connectSlotsByName(productCostPanel)
    # setupUi

        # --- restored dynamic properties ---
        self.unit_spinProductCostRmb.setProperty("unitLabel", True)
        self.unit_spinDomesticFreightRmb.setProperty("unitLabel", True)
        self.unit_spinBareLengthCm.setProperty("unitLabel", True)
        self.unit_spinBareWidthCm.setProperty("unitLabel", True)
        self.unit_spinBareHeightCm.setProperty("unitLabel", True)
        self.unit_spinBareWeightG.setProperty("unitLabel", True)

    def retranslateUi(self, productCostPanel):
        self.lblBareProductTitle.setText(QCoreApplication.translate("ProductCostPanel", u"\u5546\u54c1\u6210\u672c\u4e0e\u88f8\u4ef6", None))
        self.lblProductCost.setText(QCoreApplication.translate("ProductCostPanel", u"\u5546\u54c1\u6210\u672c", None))
        self.unit_spinProductCostRmb.setText(QCoreApplication.translate("ProductCostPanel", u"RMB", None))
        self.lblDomesticFreight.setText(QCoreApplication.translate("ProductCostPanel", u"\u56fd\u5185\u8fd0\u8d39", None))
        self.unit_spinDomesticFreightRmb.setText(QCoreApplication.translate("ProductCostPanel", u"RMB", None))
        self.lblBareDimensionsTitle.setText(QCoreApplication.translate("ProductCostPanel", u"\u88f8\u5c3a\u5bf8\uff08\u9ed8\u8ba4 cm\uff09", None))
        self.lblBareLengthCm.setText(QCoreApplication.translate("ProductCostPanel", u"\u957f", None))
        self.unit_spinBareLengthCm.setText("")
        self.lblBareWidthCm.setText(QCoreApplication.translate("ProductCostPanel", u"\u5bbd", None))
        self.unit_spinBareWidthCm.setText("")
        self.lblBareHeightCm.setText(QCoreApplication.translate("ProductCostPanel", u"\u9ad8", None))
        self.unit_spinBareHeightCm.setText("")
        self.lblBareWeight.setText(QCoreApplication.translate("ProductCostPanel", u"\u88f8\u91cd", None))
        self.unit_spinBareWeightG.setText(QCoreApplication.translate("ProductCostPanel", u"g", None))
        pass
    # retranslateUi

