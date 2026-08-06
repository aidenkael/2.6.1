# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file '_logistics_clean.ui'
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
    QGridLayout, QHBoxLayout, QLabel, QPushButton,
    QRadioButton, QSizePolicy, QSpacerItem, QVBoxLayout,
    QWidget)
class Ui_LogisticsPanel(object):
    def setupUi(self, logisticsPanel):
        if not logisticsPanel.objectName():
            logisticsPanel.setObjectName(u"logisticsPanel")
        self.logisticsPanelLayout = QVBoxLayout(logisticsPanel)
        self.logisticsPanelLayout.setSpacing(0)
        self.logisticsPanelLayout.setObjectName(u"logisticsPanelLayout")
        self.logisticsPanelLayout.setContentsMargins(0, 0, 0, 0)
        self.freightSection = QFrame(logisticsPanel)
        self.freightSection.setObjectName(u"freightSection")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        sizePolicy.setHorizontalStretch(27)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.freightSection.sizePolicy().hasHeightForWidth())
        self.freightSection.setSizePolicy(sizePolicy)
        self.freightSection.setMinimumSize(QSize(350, 0))
        self.freightLayout = QVBoxLayout(self.freightSection)
        self.freightLayout.setSpacing(6)
        self.freightLayout.setObjectName(u"freightLayout")
        self.freightLayout.setContentsMargins(10, 8, 10, 10)
        self.lblFreightTitle = QLabel(self.freightSection)
        self.lblFreightTitle.setObjectName(u"lblFreightTitle")
        sizePolicy1 = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.lblFreightTitle.sizePolicy().hasHeightForWidth())
        self.lblFreightTitle.setSizePolicy(sizePolicy1)
        self.lblFreightTitle.setMaximumSize(QSize(16777215, 28))

        self.freightLayout.addWidget(self.lblFreightTitle)

        self.tailFreightLayout = QGridLayout()
        self.tailFreightLayout.setSpacing(4)
        self.tailFreightLayout.setObjectName(u"tailFreightLayout")
        self.tailFreightLayout.setContentsMargins(0, 0, 0, 0)
        self.lblTailFreight = QLabel(self.freightSection)
        self.lblTailFreight.setObjectName(u"lblTailFreight")

        self.tailFreightLayout.addWidget(self.lblTailFreight, 0, 0, 1, 1)

        self.layout_spinTailFreightUsd = QHBoxLayout()
        self.layout_spinTailFreightUsd.setSpacing(6)
        self.layout_spinTailFreightUsd.setObjectName(u"layout_spinTailFreightUsd")
        self.layout_spinTailFreightUsd.setContentsMargins(0, 0, 0, 0)
        self.spinTailFreightUsd = QDoubleSpinBox(self.freightSection)
        self.spinTailFreightUsd.setObjectName(u"spinTailFreightUsd")
        self.spinTailFreightUsd.setReadOnly(False)
        self.spinTailFreightUsd.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.spinTailFreightUsd.setDecimals(2)
        self.spinTailFreightUsd.setMinimum(0.000000000000000)
        self.spinTailFreightUsd.setMaximum(9999.000000000000000)
        self.spinTailFreightUsd.setSingleStep(1.000000000000000)
        self.spinTailFreightUsd.setValue(5.560000000000000)

        self.layout_spinTailFreightUsd.addWidget(self.spinTailFreightUsd)

        self.unit_spinTailFreightUsd = QLabel(self.freightSection)
        self.unit_spinTailFreightUsd.setObjectName(u"unit_spinTailFreightUsd")
        self.unit_spinTailFreightUsd.setMinimumSize(QSize(36, 0))
        self.unit_spinTailFreightUsd.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.layout_spinTailFreightUsd.addWidget(self.unit_spinTailFreightUsd)


        self.tailFreightLayout.addLayout(self.layout_spinTailFreightUsd, 0, 1, 1, 1)

        self.layout_spinTailFreightRmb = QHBoxLayout()
        self.layout_spinTailFreightRmb.setSpacing(6)
        self.layout_spinTailFreightRmb.setObjectName(u"layout_spinTailFreightRmb")
        self.layout_spinTailFreightRmb.setContentsMargins(0, 0, 0, 0)
        self.spinTailFreightRmb = QDoubleSpinBox(self.freightSection)
        self.spinTailFreightRmb.setObjectName(u"spinTailFreightRmb")
        self.spinTailFreightRmb.setReadOnly(True)
        self.spinTailFreightRmb.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.spinTailFreightRmb.setDecimals(2)
        self.spinTailFreightRmb.setMinimum(0.000000000000000)
        self.spinTailFreightRmb.setMaximum(99999.000000000000000)
        self.spinTailFreightRmb.setSingleStep(1.000000000000000)
        self.spinTailFreightRmb.setValue(40.000000000000000)

        self.layout_spinTailFreightRmb.addWidget(self.spinTailFreightRmb)

        self.unit_spinTailFreightRmb = QLabel(self.freightSection)
        self.unit_spinTailFreightRmb.setObjectName(u"unit_spinTailFreightRmb")
        self.unit_spinTailFreightRmb.setMinimumSize(QSize(36, 0))
        self.unit_spinTailFreightRmb.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.layout_spinTailFreightRmb.addWidget(self.unit_spinTailFreightRmb)


        self.tailFreightLayout.addLayout(self.layout_spinTailFreightRmb, 0, 2, 1, 1)

        self.tailFreightLayout.setColumnStretch(1, 1)
        self.tailFreightLayout.setColumnStretch(2, 1)

        self.freightLayout.addLayout(self.tailFreightLayout)

        self.forwarderCardsLayout = QHBoxLayout()
        self.forwarderCardsLayout.setSpacing(6)
        self.forwarderCardsLayout.setObjectName(u"forwarderCardsLayout")
        self.forwarderCardsLayout.setContentsMargins(0, 0, 0, 0)
        self.forwarderCardShenzhen = QFrame(self.freightSection)
        self.forwarderCardShenzhen.setObjectName(u"forwarderCardShenzhen")
        sizePolicy2 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy2.setHorizontalStretch(1)
        sizePolicy2.setVerticalStretch(1)
        sizePolicy2.setHeightForWidth(self.forwarderCardShenzhen.sizePolicy().hasHeightForWidth())
        self.forwarderCardShenzhen.setSizePolicy(sizePolicy2)
        self.forwarderCardShenzhen.setMinimumSize(QSize(145, 0))
        self.forwarderShenzhenLayout = QGridLayout(self.forwarderCardShenzhen)
        self.forwarderShenzhenLayout.setSpacing(2)
        self.forwarderShenzhenLayout.setObjectName(u"forwarderShenzhenLayout")
        self.forwarderShenzhenLayout.setContentsMargins(8, 7, 8, 7)
        self.radioForwarderShenzhen = QRadioButton(self.forwarderCardShenzhen)
        self.radioForwarderShenzhen.setObjectName(u"radioForwarderShenzhen")
        self.radioForwarderShenzhen.setChecked(True)

        self.forwarderShenzhenLayout.addWidget(self.radioForwarderShenzhen, 0, 0, 1, 2)

        self.lblShenzhen1Name = QLabel(self.forwarderCardShenzhen)
        self.lblShenzhen1Name.setObjectName(u"lblShenzhen1Name")

        self.forwarderShenzhenLayout.addWidget(self.lblShenzhen1Name, 1, 0, 1, 1)

        self.lblShenzhen1Value = QLabel(self.forwarderCardShenzhen)
        self.lblShenzhen1Value.setObjectName(u"lblShenzhen1Value")
        self.lblShenzhen1Value.setAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignTrailing|Qt.AlignmentFlag.AlignVCenter)

        self.forwarderShenzhenLayout.addWidget(self.lblShenzhen1Value, 1, 1, 1, 1)

        self.lblShenzhen2Name = QLabel(self.forwarderCardShenzhen)
        self.lblShenzhen2Name.setObjectName(u"lblShenzhen2Name")

        self.forwarderShenzhenLayout.addWidget(self.lblShenzhen2Name, 2, 0, 1, 1)

        self.lblShenzhen2Value = QLabel(self.forwarderCardShenzhen)
        self.lblShenzhen2Value.setObjectName(u"lblShenzhen2Value")
        self.lblShenzhen2Value.setAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignTrailing|Qt.AlignmentFlag.AlignVCenter)

        self.forwarderShenzhenLayout.addWidget(self.lblShenzhen2Value, 2, 1, 1, 1)

        self.lblShenzhen3Name = QLabel(self.forwarderCardShenzhen)
        self.lblShenzhen3Name.setObjectName(u"lblShenzhen3Name")

        self.forwarderShenzhenLayout.addWidget(self.lblShenzhen3Name, 3, 0, 1, 1)

        self.lblShenzhen3Value = QLabel(self.forwarderCardShenzhen)
        self.lblShenzhen3Value.setObjectName(u"lblShenzhen3Value")
        self.lblShenzhen3Value.setAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignTrailing|Qt.AlignmentFlag.AlignVCenter)

        self.forwarderShenzhenLayout.addWidget(self.lblShenzhen3Value, 3, 1, 1, 1)

        self.lblShenzhen4Name = QLabel(self.forwarderCardShenzhen)
        self.lblShenzhen4Name.setObjectName(u"lblShenzhen4Name")

        self.forwarderShenzhenLayout.addWidget(self.lblShenzhen4Name, 4, 0, 1, 1)

        self.lblShenzhen4Value = QLabel(self.forwarderCardShenzhen)
        self.lblShenzhen4Value.setObjectName(u"lblShenzhen4Value")
        self.lblShenzhen4Value.setAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignTrailing|Qt.AlignmentFlag.AlignVCenter)

        self.forwarderShenzhenLayout.addWidget(self.lblShenzhen4Value, 4, 1, 1, 1)

        self.lblShenzhenTotal = QLabel(self.forwarderCardShenzhen)
        self.lblShenzhenTotal.setObjectName(u"lblShenzhenTotal")
        self.lblShenzhenTotal.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.forwarderShenzhenLayout.addWidget(self.lblShenzhenTotal, 5, 0, 1, 2)

        self.forwarderShenzhenLayout.setColumnStretch(0, 1)
        self.forwarderShenzhenLayout.setColumnStretch(1, 1)

        self.forwarderCardsLayout.addWidget(self.forwarderCardShenzhen)

        self.forwarderCardYiwu = QFrame(self.freightSection)
        self.forwarderCardYiwu.setObjectName(u"forwarderCardYiwu")
        sizePolicy2.setHeightForWidth(self.forwarderCardYiwu.sizePolicy().hasHeightForWidth())
        self.forwarderCardYiwu.setSizePolicy(sizePolicy2)
        self.forwarderCardYiwu.setMinimumSize(QSize(145, 0))
        self.forwarderYiwuLayout = QGridLayout(self.forwarderCardYiwu)
        self.forwarderYiwuLayout.setSpacing(2)
        self.forwarderYiwuLayout.setObjectName(u"forwarderYiwuLayout")
        self.forwarderYiwuLayout.setContentsMargins(8, 7, 8, 7)
        self.radioForwarderYiwu = QRadioButton(self.forwarderCardYiwu)
        self.radioForwarderYiwu.setObjectName(u"radioForwarderYiwu")

        self.forwarderYiwuLayout.addWidget(self.radioForwarderYiwu, 0, 0, 1, 2)

        self.lblYiwu1Name = QLabel(self.forwarderCardYiwu)
        self.lblYiwu1Name.setObjectName(u"lblYiwu1Name")

        self.forwarderYiwuLayout.addWidget(self.lblYiwu1Name, 1, 0, 1, 1)

        self.lblYiwu1Value = QLabel(self.forwarderCardYiwu)
        self.lblYiwu1Value.setObjectName(u"lblYiwu1Value")
        self.lblYiwu1Value.setAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignTrailing|Qt.AlignmentFlag.AlignVCenter)

        self.forwarderYiwuLayout.addWidget(self.lblYiwu1Value, 1, 1, 1, 1)

        self.lblYiwu2Name = QLabel(self.forwarderCardYiwu)
        self.lblYiwu2Name.setObjectName(u"lblYiwu2Name")

        self.forwarderYiwuLayout.addWidget(self.lblYiwu2Name, 2, 0, 1, 1)

        self.lblYiwu2Value = QLabel(self.forwarderCardYiwu)
        self.lblYiwu2Value.setObjectName(u"lblYiwu2Value")
        self.lblYiwu2Value.setAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignTrailing|Qt.AlignmentFlag.AlignVCenter)

        self.forwarderYiwuLayout.addWidget(self.lblYiwu2Value, 2, 1, 1, 1)

        self.lblYiwu3Name = QLabel(self.forwarderCardYiwu)
        self.lblYiwu3Name.setObjectName(u"lblYiwu3Name")

        self.forwarderYiwuLayout.addWidget(self.lblYiwu3Name, 3, 0, 1, 1)

        self.lblYiwu3Value = QLabel(self.forwarderCardYiwu)
        self.lblYiwu3Value.setObjectName(u"lblYiwu3Value")
        self.lblYiwu3Value.setAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignTrailing|Qt.AlignmentFlag.AlignVCenter)

        self.forwarderYiwuLayout.addWidget(self.lblYiwu3Value, 3, 1, 1, 1)

        self.lblYiwu4Name = QLabel(self.forwarderCardYiwu)
        self.lblYiwu4Name.setObjectName(u"lblYiwu4Name")

        self.forwarderYiwuLayout.addWidget(self.lblYiwu4Name, 4, 0, 1, 1)

        self.lblYiwu4Value = QLabel(self.forwarderCardYiwu)
        self.lblYiwu4Value.setObjectName(u"lblYiwu4Value")
        self.lblYiwu4Value.setAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignTrailing|Qt.AlignmentFlag.AlignVCenter)

        self.forwarderYiwuLayout.addWidget(self.lblYiwu4Value, 4, 1, 1, 1)

        self.lblYiwuTotal = QLabel(self.forwarderCardYiwu)
        self.lblYiwuTotal.setObjectName(u"lblYiwuTotal")
        self.lblYiwuTotal.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.forwarderYiwuLayout.addWidget(self.lblYiwuTotal, 5, 0, 1, 2)

        self.forwarderYiwuLayout.setColumnStretch(0, 1)
        self.forwarderYiwuLayout.setColumnStretch(1, 1)

        self.forwarderCardsLayout.addWidget(self.forwarderCardYiwu)

        self.forwarderCardsLayout.setStretch(0, 1)
        self.forwarderCardsLayout.setStretch(1, 1)

        self.freightLayout.addLayout(self.forwarderCardsLayout)

        self.freightLayout.setStretch(2, 1)

        self.logisticsPanelLayout.addWidget(self.freightSection)

        self.systemCostSection = QFrame(logisticsPanel)
        self.systemCostSection.setObjectName(u"systemCostSection")
        sizePolicy3 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        sizePolicy3.setHorizontalStretch(16)
        sizePolicy3.setVerticalStretch(0)
        sizePolicy3.setHeightForWidth(self.systemCostSection.sizePolicy().hasHeightForWidth())
        self.systemCostSection.setSizePolicy(sizePolicy3)
        self.systemCostSection.setMinimumSize(QSize(220, 0))
        self.systemCostLayout = QVBoxLayout(self.systemCostSection)
        self.systemCostLayout.setSpacing(4)
        self.systemCostLayout.setObjectName(u"systemCostLayout")
        self.systemCostLayout.setContentsMargins(10, 8, 10, 10)
        self.systemCostHeaderLayout = QHBoxLayout()
        self.systemCostHeaderLayout.setSpacing(5)
        self.systemCostHeaderLayout.setObjectName(u"systemCostHeaderLayout")
        self.systemCostHeaderLayout.setContentsMargins(0, 0, 0, 0)
        self.lblSystemCostTitle = QLabel(self.systemCostSection)
        self.lblSystemCostTitle.setObjectName(u"lblSystemCostTitle")
        sizePolicy1.setHeightForWidth(self.lblSystemCostTitle.sizePolicy().hasHeightForWidth())
        self.lblSystemCostTitle.setSizePolicy(sizePolicy1)
        self.lblSystemCostTitle.setMaximumSize(QSize(16777215, 28))

        self.systemCostHeaderLayout.addWidget(self.lblSystemCostTitle)

        self.systemCostHeaderSpacer = QSpacerItem(20, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.systemCostHeaderLayout.addItem(self.systemCostHeaderSpacer)

        self.btnSystemCalculate = QPushButton(self.systemCostSection)
        self.btnSystemCalculate.setObjectName(u"btnSystemCalculate")
        sizePolicy4 = QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        sizePolicy4.setHorizontalStretch(0)
        sizePolicy4.setVerticalStretch(0)
        sizePolicy4.setHeightForWidth(self.btnSystemCalculate.sizePolicy().hasHeightForWidth())
        self.btnSystemCalculate.setSizePolicy(sizePolicy4)
        self.btnSystemCalculate.setMaximumSize(QSize(90, 30))
        self.btnSystemCalculate.setVisible(False)

        self.systemCostHeaderLayout.addWidget(self.btnSystemCalculate)


        self.systemCostLayout.addLayout(self.systemCostHeaderLayout)

        self.systemCostRow0 = QHBoxLayout()
        self.systemCostRow0.setSpacing(5)
        self.systemCostRow0.setObjectName(u"systemCostRow0")
        self.systemCostRow0.setContentsMargins(0, 0, 0, 0)
        self.lblSystemCostName0 = QLabel(self.systemCostSection)
        self.lblSystemCostName0.setObjectName(u"lblSystemCostName0")

        self.systemCostRow0.addWidget(self.lblSystemCostName0)

        self.systemCostSpacer0 = QSpacerItem(20, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.systemCostRow0.addItem(self.systemCostSpacer0)

        self.lblSystemCostValue0 = QLabel(self.systemCostSection)
        self.lblSystemCostValue0.setObjectName(u"lblSystemCostValue0")

        self.systemCostRow0.addWidget(self.lblSystemCostValue0)


        self.systemCostLayout.addLayout(self.systemCostRow0)

        self.systemCostRow1 = QHBoxLayout()
        self.systemCostRow1.setSpacing(5)
        self.systemCostRow1.setObjectName(u"systemCostRow1")
        self.systemCostRow1.setContentsMargins(0, 0, 0, 0)
        self.lblSystemCostName1 = QLabel(self.systemCostSection)
        self.lblSystemCostName1.setObjectName(u"lblSystemCostName1")

        self.systemCostRow1.addWidget(self.lblSystemCostName1)

        self.systemCostSpacer1 = QSpacerItem(20, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.systemCostRow1.addItem(self.systemCostSpacer1)

        self.lblSystemCostValue1 = QLabel(self.systemCostSection)
        self.lblSystemCostValue1.setObjectName(u"lblSystemCostValue1")

        self.systemCostRow1.addWidget(self.lblSystemCostValue1)


        self.systemCostLayout.addLayout(self.systemCostRow1)

        self.systemCostRow2 = QHBoxLayout()
        self.systemCostRow2.setSpacing(5)
        self.systemCostRow2.setObjectName(u"systemCostRow2")
        self.systemCostRow2.setContentsMargins(0, 0, 0, 0)
        self.lblSystemCostName2 = QLabel(self.systemCostSection)
        self.lblSystemCostName2.setObjectName(u"lblSystemCostName2")

        self.systemCostRow2.addWidget(self.lblSystemCostName2)

        self.systemCostSpacer2 = QSpacerItem(20, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.systemCostRow2.addItem(self.systemCostSpacer2)

        self.lblSystemCostValue2 = QLabel(self.systemCostSection)
        self.lblSystemCostValue2.setObjectName(u"lblSystemCostValue2")

        self.systemCostRow2.addWidget(self.lblSystemCostValue2)


        self.systemCostLayout.addLayout(self.systemCostRow2)

        self.systemCostRow3 = QHBoxLayout()
        self.systemCostRow3.setSpacing(5)
        self.systemCostRow3.setObjectName(u"systemCostRow3")
        self.systemCostRow3.setContentsMargins(0, 0, 0, 0)
        self.lblSystemCostName3 = QLabel(self.systemCostSection)
        self.lblSystemCostName3.setObjectName(u"lblSystemCostName3")

        self.systemCostRow3.addWidget(self.lblSystemCostName3)

        self.systemCostSpacer3 = QSpacerItem(20, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.systemCostRow3.addItem(self.systemCostSpacer3)

        self.lblSystemCostValue3 = QLabel(self.systemCostSection)
        self.lblSystemCostValue3.setObjectName(u"lblSystemCostValue3")

        self.systemCostRow3.addWidget(self.lblSystemCostValue3)


        self.systemCostLayout.addLayout(self.systemCostRow3)

        self.systemCostRow4 = QHBoxLayout()
        self.systemCostRow4.setSpacing(5)
        self.systemCostRow4.setObjectName(u"systemCostRow4")
        self.systemCostRow4.setContentsMargins(0, 0, 0, 0)
        self.lblSystemCostName4 = QLabel(self.systemCostSection)
        self.lblSystemCostName4.setObjectName(u"lblSystemCostName4")

        self.systemCostRow4.addWidget(self.lblSystemCostName4)

        self.systemCostSpacer4 = QSpacerItem(20, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.systemCostRow4.addItem(self.systemCostSpacer4)

        self.lblSystemCostValue4 = QLabel(self.systemCostSection)
        self.lblSystemCostValue4.setObjectName(u"lblSystemCostValue4")

        self.systemCostRow4.addWidget(self.lblSystemCostValue4)


        self.systemCostLayout.addLayout(self.systemCostRow4)

        self.systemCostRow6 = QHBoxLayout()
        self.systemCostRow6.setSpacing(5)
        self.systemCostRow6.setObjectName(u"systemCostRow6")
        self.systemCostRow6.setContentsMargins(0, 0, 0, 0)
        self.lblSystemCostName6 = QLabel(self.systemCostSection)
        self.lblSystemCostName6.setObjectName(u"lblSystemCostName6")

        self.systemCostRow6.addWidget(self.lblSystemCostName6)

        self.systemCostSpacer6 = QSpacerItem(20, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.systemCostRow6.addItem(self.systemCostSpacer6)

        self.lblSystemCostValue6 = QLabel(self.systemCostSection)
        self.lblSystemCostValue6.setObjectName(u"lblSystemCostValue6")

        self.systemCostRow6.addWidget(self.lblSystemCostValue6)


        self.systemCostLayout.addLayout(self.systemCostRow6)

        self.systemCostRow5 = QHBoxLayout()
        self.systemCostRow5.setSpacing(5)
        self.systemCostRow5.setObjectName(u"systemCostRow5")
        self.systemCostRow5.setContentsMargins(0, 0, 0, 0)
        self.lblSystemCostName5 = QLabel(self.systemCostSection)
        self.lblSystemCostName5.setObjectName(u"lblSystemCostName5")

        self.systemCostRow5.addWidget(self.lblSystemCostName5)

        self.systemCostSpacer5 = QSpacerItem(20, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.systemCostRow5.addItem(self.systemCostSpacer5)

        self.lblSystemCostValue5 = QLabel(self.systemCostSection)
        self.lblSystemCostValue5.setObjectName(u"lblSystemCostValue5")

        self.systemCostRow5.addWidget(self.lblSystemCostValue5)


        self.systemCostLayout.addLayout(self.systemCostRow5)

        self.systemTotalBox = QFrame(self.systemCostSection)
        self.systemTotalBox.setObjectName(u"systemTotalBox")
        sizePolicy5 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        sizePolicy5.setHorizontalStretch(0)
        sizePolicy5.setVerticalStretch(0)
        sizePolicy5.setHeightForWidth(self.systemTotalBox.sizePolicy().hasHeightForWidth())
        self.systemTotalBox.setSizePolicy(sizePolicy5)
        self.systemTotalBox.setMinimumSize(QSize(0, 48))
        self.systemTotalBox.setMaximumSize(QSize(16777215, 58))
        self.systemTotalLayout = QVBoxLayout(self.systemTotalBox)
        self.systemTotalLayout.setSpacing(1)
        self.systemTotalLayout.setObjectName(u"systemTotalLayout")
        self.systemTotalLayout.setContentsMargins(8, 6, 8, 6)
        self.lblSystemTotalRmb = QLabel(self.systemTotalBox)
        self.lblSystemTotalRmb.setObjectName(u"lblSystemTotalRmb")
        self.lblSystemTotalRmb.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.systemTotalLayout.addWidget(self.lblSystemTotalRmb)

        self.lblSystemTotalUsd = QLabel(self.systemTotalBox)
        self.lblSystemTotalUsd.setObjectName(u"lblSystemTotalUsd")
        self.lblSystemTotalUsd.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.systemTotalLayout.addWidget(self.lblSystemTotalUsd)


        self.systemCostLayout.addWidget(self.systemTotalBox)

        self.systemCostLayout.setStretch(8, 1)

        self.logisticsPanelLayout.addWidget(self.systemCostSection)


        self.retranslateUi(logisticsPanel)

        QMetaObject.connectSlotsByName(logisticsPanel)
    # setupUi

        # --- restored dynamic properties ---
        self.freightSection.setProperty("card", True)
        self.lblFreightTitle.setProperty("sectionTitle", True)
        self.unit_spinTailFreightUsd.setProperty("unitLabel", True)
        self.spinTailFreightRmb.setProperty("preview", True)
        self.unit_spinTailFreightRmb.setProperty("unitLabel", True)
        self.forwarderCardShenzhen.setProperty("selected", True)
        self.lblShenzhenTotal.setProperty("totalValue", True)
        self.forwarderCardShenzhen.setProperty("uiPlaceholder", True)
        self.lblYiwuTotal.setProperty("totalValue", True)
        self.forwarderCardYiwu.setProperty("uiPlaceholder", True)
        self.systemCostSection.setProperty("card", True)
        self.lblSystemCostTitle.setProperty("sectionTitle", True)
        self.systemCostSection.setProperty("sizeType", "QSizePolicy::Policy::Expanding")
        self.systemCostSection.setProperty("sizeType", "QSizePolicy::Policy::Expanding")
        self.systemCostSection.setProperty("sizeType", "QSizePolicy::Policy::Expanding")
        self.systemCostSection.setProperty("sizeType", "QSizePolicy::Policy::Expanding")
        self.systemCostSection.setProperty("sizeType", "QSizePolicy::Policy::Expanding")
        self.systemCostSection.setProperty("sizeType", "QSizePolicy::Policy::Expanding")
        self.systemCostSection.setProperty("sizeType", "QSizePolicy::Policy::Expanding")
        self.systemCostSection.setProperty("sizeType", "QSizePolicy::Policy::Expanding")
        self.systemTotalBox.setProperty("card", True)

    def retranslateUi(self, logisticsPanel):
        self.lblFreightTitle.setText(QCoreApplication.translate("LogisticsPanel", u"\u8d27\u4ee3\u65b9\u6848\uff08\u8fd0\u884c\u65f6\u6309\u542f\u7528\u8d27\u4ee3\u52a8\u6001\u751f\u6210\uff09", None))
        self.lblTailFreight.setText(QCoreApplication.translate("LogisticsPanel", u"\u5c3e\u7a0b\u8d39\u7528", None))
#if QT_CONFIG(tooltip)
        self.spinTailFreightUsd.setToolTip(QCoreApplication.translate("LogisticsPanel", u"\u53ef\u7f16\u8f91\u5c3e\u7a0b\u8d39\u7528\uff08USD\uff09", None))
#endif // QT_CONFIG(tooltip)
        self.unit_spinTailFreightUsd.setText(QCoreApplication.translate("LogisticsPanel", u"USD", None))
#if QT_CONFIG(tooltip)
        self.spinTailFreightRmb.setToolTip(QCoreApplication.translate("LogisticsPanel", u"\u6309\u5f53\u524d\u6c47\u7387\u6362\u7b97\uff0c\u4ec5\u663e\u793a", None))
#endif // QT_CONFIG(tooltip)
        self.unit_spinTailFreightRmb.setText(QCoreApplication.translate("LogisticsPanel", u"RMB", None))
        self.radioForwarderShenzhen.setText(QCoreApplication.translate("LogisticsPanel", u"\u6df1\u5733\u8d27\u4ee3", None))
        self.lblShenzhen1Name.setText(QCoreApplication.translate("LogisticsPanel", u"\u5b9e\u9645\u91cd", None))
        self.lblShenzhen1Value.setText(QCoreApplication.translate("LogisticsPanel", u"0.750 kg", None))
        self.lblShenzhen2Name.setText(QCoreApplication.translate("LogisticsPanel", u"\u4f53\u79ef\u91cd", None))
        self.lblShenzhen2Value.setText(QCoreApplication.translate("LogisticsPanel", u"0.720 kg", None))
        self.lblShenzhen3Name.setText(QCoreApplication.translate("LogisticsPanel", u"\u8ba1\u8d39\u91cd", None))
        self.lblShenzhen3Value.setText(QCoreApplication.translate("LogisticsPanel", u"0.750 kg", None))
        self.lblShenzhen4Name.setText(QCoreApplication.translate("LogisticsPanel", u"\u5934\u7a0b", None))
        self.lblShenzhen4Value.setText(QCoreApplication.translate("LogisticsPanel", u"\u00a560.00", None))
        self.lblShenzhenTotal.setText(QCoreApplication.translate("LogisticsPanel", u"\u7269\u6d41\u603b\u4ef7 \u00a5110.00", None))
        self.radioForwarderYiwu.setText(QCoreApplication.translate("LogisticsPanel", u"\u4e49\u4e4c\u8d27\u4ee3", None))
        self.lblYiwu1Name.setText(QCoreApplication.translate("LogisticsPanel", u"\u5b9e\u9645\u91cd", None))
        self.lblYiwu1Value.setText(QCoreApplication.translate("LogisticsPanel", u"0.750 kg", None))
        self.lblYiwu2Name.setText(QCoreApplication.translate("LogisticsPanel", u"\u4f53\u79ef\u91cd", None))
        self.lblYiwu2Value.setText(QCoreApplication.translate("LogisticsPanel", u"0.720 kg", None))
        self.lblYiwu3Name.setText(QCoreApplication.translate("LogisticsPanel", u"\u8ba1\u8d39\u91cd", None))
        self.lblYiwu3Value.setText(QCoreApplication.translate("LogisticsPanel", u"0.750 kg", None))
        self.lblYiwu4Name.setText(QCoreApplication.translate("LogisticsPanel", u"\u5934\u7a0b", None))
        self.lblYiwu4Value.setText(QCoreApplication.translate("LogisticsPanel", u"\u00a575.00", None))
        self.lblYiwuTotal.setText(QCoreApplication.translate("LogisticsPanel", u"\u7269\u6d41\u603b\u4ef7 \u00a5121.00", None))
        self.lblSystemCostTitle.setText(QCoreApplication.translate("LogisticsPanel", u"\u5f53\u524d\u7cfb\u7edf\u603b\u6210\u672c", None))
        self.btnSystemCalculate.setText(QCoreApplication.translate("LogisticsPanel", u"\u7cfb\u7edf\u8ba1\u7b97", None))
        self.lblSystemCostName0.setText(QCoreApplication.translate("LogisticsPanel", u"\u5305\u88c5\u6863", None))
        self.lblSystemCostValue0.setText(QCoreApplication.translate("LogisticsPanel", u"\u6b63\u5e38\u6863", None))
        self.lblSystemCostName1.setText(QCoreApplication.translate("LogisticsPanel", u"\u5f53\u524d\u8d27\u4ee3", None))
        self.lblSystemCostValue1.setText(QCoreApplication.translate("LogisticsPanel", u"\u6df1\u5733\u8d27\u4ee3", None))
        self.lblSystemCostName2.setText(QCoreApplication.translate("LogisticsPanel", u"\u5b9e\u9645\u91cd", None))
        self.lblSystemCostValue2.setText(QCoreApplication.translate("LogisticsPanel", u"0.750 kg", None))
        self.lblSystemCostName3.setText(QCoreApplication.translate("LogisticsPanel", u"\u4f53\u79ef\u91cd", None))
        self.lblSystemCostValue3.setText(QCoreApplication.translate("LogisticsPanel", u"0.720 kg", None))
        self.lblSystemCostName4.setText(QCoreApplication.translate("LogisticsPanel", u"\u8ba1\u8d39\u91cd", None))
        self.lblSystemCostValue4.setText(QCoreApplication.translate("LogisticsPanel", u"0.750 kg", None))
        self.lblSystemCostName6.setText(QCoreApplication.translate("LogisticsPanel", u"\u5c3e\u7a0b\u8d39\u7528", None))
        self.lblSystemCostValue6.setText(QCoreApplication.translate("LogisticsPanel", u"\u00a540.00", None))
#if QT_CONFIG(tooltip)
        self.lblSystemCostValue6.setToolTip(QCoreApplication.translate("LogisticsPanel", u"\u5c3e\u7a0b\u8d39\u7528\u5355\u72ec\u663e\u793a\uff0c\u5e76\u5df2\u8ba1\u5165\u7269\u6d41\u603b\u4ef7\u548c\u7cfb\u7edf\u603b\u6210\u672c", None))
#endif // QT_CONFIG(tooltip)
        self.lblSystemCostName5.setText(QCoreApplication.translate("LogisticsPanel", u"\u7269\u6d41\u603b\u4ef7", None))
        self.lblSystemCostValue5.setText(QCoreApplication.translate("LogisticsPanel", u"\u00a5110.00", None))
        self.lblSystemTotalRmb.setText(QCoreApplication.translate("LogisticsPanel", u"\u7cfb\u7edf\u603b\u6210\u672c    \u00a5133.80", None))
        self.lblSystemTotalUsd.setText(QCoreApplication.translate("LogisticsPanel", u"$18.58 USD", None))
        pass
    # retranslateUi

