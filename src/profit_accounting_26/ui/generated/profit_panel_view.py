# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file '_profit_clean.ui'
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
from PySide6.QtWidgets import (QAbstractSpinBox, QApplication, QComboBox, QDoubleSpinBox,
    QFrame, QGridLayout, QHBoxLayout, QLabel,
    QSizePolicy, QSpacerItem, QVBoxLayout, QWidget)

class Ui_ProfitPanel(object):
    def setupUi(self, profitPanel):
        if not profitPanel.objectName():
            profitPanel.setObjectName(u"profitPanel")
        self.profitLayout = QVBoxLayout(profitPanel)
        self.profitLayout.setSpacing(8)
        self.profitLayout.setObjectName(u"profitLayout")
        self.profitLayout.setContentsMargins(14, 10, 14, 10)
        self.profitHeaderLayout = QHBoxLayout()
        self.profitHeaderLayout.setSpacing(8)
        self.profitHeaderLayout.setObjectName(u"profitHeaderLayout")
        self.profitHeaderLayout.setContentsMargins(0, 0, 0, 0)
        self.lblProfitTitle = QLabel(profitPanel)
        self.lblProfitTitle.setObjectName(u"lblProfitTitle")

        self.profitHeaderLayout.addWidget(self.lblProfitTitle)

        self.lblProfitHint = QLabel(profitPanel)
        self.lblProfitHint.setObjectName(u"lblProfitHint")

        self.profitHeaderLayout.addWidget(self.lblProfitHint)

        self.profitHeaderSpacer = QSpacerItem(20, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.profitHeaderLayout.addItem(self.profitHeaderSpacer)

        self.lblProfitRuleTitle = QLabel(profitPanel)
        self.lblProfitRuleTitle.setObjectName(u"lblProfitRuleTitle")

        self.profitHeaderLayout.addWidget(self.lblProfitRuleTitle)

        self.cmbProfitRule = QComboBox(profitPanel)
        self.cmbProfitRule.addItem("")
        self.cmbProfitRule.addItem("")
        self.cmbProfitRule.addItem("")
        self.cmbProfitRule.setObjectName(u"cmbProfitRule")
        self.cmbProfitRule.setMinimumSize(QSize(260, 36))

        self.profitHeaderLayout.addWidget(self.cmbProfitRule)


        self.profitLayout.addLayout(self.profitHeaderLayout)

        self.profitFieldsHost = QWidget(profitPanel)
        self.profitFieldsHost.setObjectName(u"profitFieldsHost")
        self.profitFieldsHost.setMinimumSize(QSize(1190, 0))
        self.profitFieldsHost.setMaximumSize(QSize(1190, 16777215))
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.profitFieldsHost.sizePolicy().hasHeightForWidth())
        self.profitFieldsHost.setSizePolicy(sizePolicy)
        self.profitFieldsHostLayout = QVBoxLayout(self.profitFieldsHost)
        self.profitFieldsHostLayout.setSpacing(0)
        self.profitFieldsHostLayout.setObjectName(u"profitFieldsHostLayout")
        self.profitFieldsHostLayout.setContentsMargins(0, 0, 0, 0)
        self.profitFieldsGrid = QGridLayout()
        self.profitFieldsGrid.setSpacing(8)
        self.profitFieldsGrid.setObjectName(u"profitFieldsGrid")
        self.profitFieldsGrid.setHorizontalSpacing(10)
        self.profitFieldsGrid.setVerticalSpacing(6)
        self.profitFieldsGrid.setContentsMargins(0, 0, 0, 0)
        self.lblSheinPrice = QLabel(self.profitFieldsHost)
        self.lblSheinPrice.setObjectName(u"lblSheinPrice")

        self.profitFieldsGrid.addWidget(self.lblSheinPrice, 0, 0, 1, 1)

        self.lblProfitCost = QLabel(self.profitFieldsHost)
        self.lblProfitCost.setObjectName(u"lblProfitCost")

        self.profitFieldsGrid.addWidget(self.lblProfitCost, 0, 1, 1, 1)

        self.lblProfitRate = QLabel(self.profitFieldsHost)
        self.lblProfitRate.setObjectName(u"lblProfitRate")

        self.profitFieldsGrid.addWidget(self.lblProfitRate, 0, 2, 1, 1)

        self.lblNoActivityPrice = QLabel(self.profitFieldsHost)
        self.lblNoActivityPrice.setObjectName(u"lblNoActivityPrice")

        self.profitFieldsGrid.addWidget(self.lblNoActivityPrice, 0, 3, 1, 1)

        self.layoutNoActivityProfitTitle = QHBoxLayout()
        self.layoutNoActivityProfitTitle.setSpacing(5)
        self.layoutNoActivityProfitTitle.setObjectName(u"layoutNoActivityProfitTitle")
        self.layoutNoActivityProfitTitle.setContentsMargins(0, 0, 0, 0)
        self.lblNoActivityProfit = QLabel(self.profitFieldsHost)
        self.lblNoActivityProfit.setObjectName(u"lblNoActivityProfit")

        self.layoutNoActivityProfitTitle.addWidget(self.lblNoActivityProfit)

        self.lblNoActivitySubsidyStatus = QLabel(self.profitFieldsHost)
        self.lblNoActivitySubsidyStatus.setObjectName(u"lblNoActivitySubsidyStatus")

        self.layoutNoActivityProfitTitle.addWidget(self.lblNoActivitySubsidyStatus)


        self.profitFieldsGrid.addLayout(self.layoutNoActivityProfitTitle, 0, 5, 1, 1)

        self.lblPromotionReserve = QLabel(self.profitFieldsHost)
        self.lblPromotionReserve.setObjectName(u"lblPromotionReserve")

        self.profitFieldsGrid.addWidget(self.lblPromotionReserve, 0, 6, 1, 1)

        self.lblActivityPrice = QLabel(self.profitFieldsHost)
        self.lblActivityPrice.setObjectName(u"lblActivityPrice")

        self.profitFieldsGrid.addWidget(self.lblActivityPrice, 0, 7, 1, 1)

        self.layoutActivityProfitTitle = QHBoxLayout()
        self.layoutActivityProfitTitle.setSpacing(5)
        self.layoutActivityProfitTitle.setObjectName(u"layoutActivityProfitTitle")
        self.layoutActivityProfitTitle.setContentsMargins(0, 0, 0, 0)
        self.lblActivityProfit = QLabel(self.profitFieldsHost)
        self.lblActivityProfit.setObjectName(u"lblActivityProfit")

        self.layoutActivityProfitTitle.addWidget(self.lblActivityProfit)

        self.lblActivitySubsidyStatus = QLabel(self.profitFieldsHost)
        self.lblActivitySubsidyStatus.setObjectName(u"lblActivitySubsidyStatus")

        self.layoutActivityProfitTitle.addWidget(self.lblActivitySubsidyStatus)


        self.profitFieldsGrid.addLayout(self.layoutActivityProfitTitle, 0, 8, 1, 1)

        self.layout_txtSheinPriceRmb = QHBoxLayout()
        self.layout_txtSheinPriceRmb.setSpacing(4)
        self.layout_txtSheinPriceRmb.setObjectName(u"layout_txtSheinPriceRmb")
        self.layout_txtSheinPriceRmb.setContentsMargins(0, 0, 0, 0)
        self.txtSheinPriceRmb = QDoubleSpinBox(self.profitFieldsHost)
        self.txtSheinPriceRmb.setObjectName(u"txtSheinPriceRmb")
        self.txtSheinPriceRmb.setMinimumSize(QSize(96, 36))
        self.txtSheinPriceRmb.setReadOnly(True)
        self.txtSheinPriceRmb.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.txtSheinPriceRmb.setDecimals(2)
        self.txtSheinPriceRmb.setMinimum(0.000000000000000)
        self.txtSheinPriceRmb.setMaximum(999999.000000000000000)
        self.txtSheinPriceRmb.setSingleStep(1.000000000000000)
        self.txtSheinPriceRmb.setValue(0.000000000000000)
        self.txtSheinPriceRmb.setMaximumSize(QSize(96, 36))
        sizePolicy1 = QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.txtSheinPriceRmb.sizePolicy().hasHeightForWidth())
        self.txtSheinPriceRmb.setSizePolicy(sizePolicy1)

        self.layout_txtSheinPriceRmb.addWidget(self.txtSheinPriceRmb)

        self.unit_txtSheinPriceRmb = QLabel(self.profitFieldsHost)
        self.unit_txtSheinPriceRmb.setObjectName(u"unit_txtSheinPriceRmb")
        self.unit_txtSheinPriceRmb.setMinimumSize(QSize(32, 36))
        self.unit_txtSheinPriceRmb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.unit_txtSheinPriceRmb.setMaximumSize(QSize(32, 36))
        sizePolicy1.setHeightForWidth(self.unit_txtSheinPriceRmb.sizePolicy().hasHeightForWidth())
        self.unit_txtSheinPriceRmb.setSizePolicy(sizePolicy1)

        self.layout_txtSheinPriceRmb.addWidget(self.unit_txtSheinPriceRmb)


        self.profitFieldsGrid.addLayout(self.layout_txtSheinPriceRmb, 1, 0, 1, 1)

        self.layout_txtSheinPriceUsd = QHBoxLayout()
        self.layout_txtSheinPriceUsd.setSpacing(4)
        self.layout_txtSheinPriceUsd.setObjectName(u"layout_txtSheinPriceUsd")
        self.layout_txtSheinPriceUsd.setContentsMargins(0, 0, 0, 0)
        self.txtSheinPriceUsd = QDoubleSpinBox(self.profitFieldsHost)
        self.txtSheinPriceUsd.setObjectName(u"txtSheinPriceUsd")
        self.txtSheinPriceUsd.setMinimumSize(QSize(96, 36))
        self.txtSheinPriceUsd.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.txtSheinPriceUsd.setDecimals(2)
        self.txtSheinPriceUsd.setMinimum(0.000000000000000)
        self.txtSheinPriceUsd.setMaximum(999999.000000000000000)
        self.txtSheinPriceUsd.setSingleStep(1.000000000000000)
        self.txtSheinPriceUsd.setValue(0.000000000000000)
        self.txtSheinPriceUsd.setReadOnly(False)
        self.txtSheinPriceUsd.setMaximumSize(QSize(96, 36))
        sizePolicy1.setHeightForWidth(self.txtSheinPriceUsd.sizePolicy().hasHeightForWidth())
        self.txtSheinPriceUsd.setSizePolicy(sizePolicy1)

        self.layout_txtSheinPriceUsd.addWidget(self.txtSheinPriceUsd)

        self.unit_txtSheinPriceUsd = QLabel(self.profitFieldsHost)
        self.unit_txtSheinPriceUsd.setObjectName(u"unit_txtSheinPriceUsd")
        self.unit_txtSheinPriceUsd.setMinimumSize(QSize(32, 36))
        self.unit_txtSheinPriceUsd.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.unit_txtSheinPriceUsd.setMaximumSize(QSize(32, 36))
        sizePolicy1.setHeightForWidth(self.unit_txtSheinPriceUsd.sizePolicy().hasHeightForWidth())
        self.unit_txtSheinPriceUsd.setSizePolicy(sizePolicy1)

        self.layout_txtSheinPriceUsd.addWidget(self.unit_txtSheinPriceUsd)


        self.profitFieldsGrid.addLayout(self.layout_txtSheinPriceUsd, 2, 0, 1, 1)

        self.layout_txtCalculatedCostRmb = QHBoxLayout()
        self.layout_txtCalculatedCostRmb.setSpacing(4)
        self.layout_txtCalculatedCostRmb.setObjectName(u"layout_txtCalculatedCostRmb")
        self.layout_txtCalculatedCostRmb.setContentsMargins(0, 0, 0, 0)
        self.txtCalculatedCostRmb = QDoubleSpinBox(self.profitFieldsHost)
        self.txtCalculatedCostRmb.setObjectName(u"txtCalculatedCostRmb")
        self.txtCalculatedCostRmb.setMinimumSize(QSize(96, 36))
        self.txtCalculatedCostRmb.setReadOnly(False)
        self.txtCalculatedCostRmb.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.txtCalculatedCostRmb.setDecimals(2)
        self.txtCalculatedCostRmb.setMinimum(0.000000000000000)
        self.txtCalculatedCostRmb.setMaximum(999999.000000000000000)
        self.txtCalculatedCostRmb.setSingleStep(1.000000000000000)
        self.txtCalculatedCostRmb.setValue(0.000000000000000)
        self.txtCalculatedCostRmb.setMaximumSize(QSize(96, 36))
        sizePolicy1.setHeightForWidth(self.txtCalculatedCostRmb.sizePolicy().hasHeightForWidth())
        self.txtCalculatedCostRmb.setSizePolicy(sizePolicy1)

        self.layout_txtCalculatedCostRmb.addWidget(self.txtCalculatedCostRmb)

        self.unit_txtCalculatedCostRmb = QLabel(self.profitFieldsHost)
        self.unit_txtCalculatedCostRmb.setObjectName(u"unit_txtCalculatedCostRmb")
        self.unit_txtCalculatedCostRmb.setMinimumSize(QSize(32, 36))
        self.unit_txtCalculatedCostRmb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.unit_txtCalculatedCostRmb.setMaximumSize(QSize(32, 36))
        sizePolicy1.setHeightForWidth(self.unit_txtCalculatedCostRmb.sizePolicy().hasHeightForWidth())
        self.unit_txtCalculatedCostRmb.setSizePolicy(sizePolicy1)

        self.layout_txtCalculatedCostRmb.addWidget(self.unit_txtCalculatedCostRmb)


        self.profitFieldsGrid.addLayout(self.layout_txtCalculatedCostRmb, 1, 1, 1, 1)

        self.layout_txtCalculatedCostUsd = QHBoxLayout()
        self.layout_txtCalculatedCostUsd.setSpacing(4)
        self.layout_txtCalculatedCostUsd.setObjectName(u"layout_txtCalculatedCostUsd")
        self.layout_txtCalculatedCostUsd.setContentsMargins(0, 0, 0, 0)
        self.txtCalculatedCostUsd = QDoubleSpinBox(self.profitFieldsHost)
        self.txtCalculatedCostUsd.setObjectName(u"txtCalculatedCostUsd")
        self.txtCalculatedCostUsd.setMinimumSize(QSize(96, 36))
        self.txtCalculatedCostUsd.setReadOnly(True)
        self.txtCalculatedCostUsd.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.txtCalculatedCostUsd.setDecimals(2)
        self.txtCalculatedCostUsd.setMinimum(0.000000000000000)
        self.txtCalculatedCostUsd.setMaximum(999999.000000000000000)
        self.txtCalculatedCostUsd.setSingleStep(1.000000000000000)
        self.txtCalculatedCostUsd.setValue(0.000000000000000)
        self.txtCalculatedCostUsd.setMaximumSize(QSize(96, 36))
        sizePolicy1.setHeightForWidth(self.txtCalculatedCostUsd.sizePolicy().hasHeightForWidth())
        self.txtCalculatedCostUsd.setSizePolicy(sizePolicy1)

        self.layout_txtCalculatedCostUsd.addWidget(self.txtCalculatedCostUsd)

        self.unit_txtCalculatedCostUsd = QLabel(self.profitFieldsHost)
        self.unit_txtCalculatedCostUsd.setObjectName(u"unit_txtCalculatedCostUsd")
        self.unit_txtCalculatedCostUsd.setMinimumSize(QSize(32, 36))
        self.unit_txtCalculatedCostUsd.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.unit_txtCalculatedCostUsd.setMaximumSize(QSize(32, 36))
        sizePolicy1.setHeightForWidth(self.unit_txtCalculatedCostUsd.sizePolicy().hasHeightForWidth())
        self.unit_txtCalculatedCostUsd.setSizePolicy(sizePolicy1)

        self.layout_txtCalculatedCostUsd.addWidget(self.unit_txtCalculatedCostUsd)


        self.profitFieldsGrid.addLayout(self.layout_txtCalculatedCostUsd, 2, 1, 1, 1)

        self.layout_spinProfitRate = QHBoxLayout()
        self.layout_spinProfitRate.setSpacing(4)
        self.layout_spinProfitRate.setObjectName(u"layout_spinProfitRate")
        self.layout_spinProfitRate.setContentsMargins(0, 0, 0, 0)
        self.spinProfitRate = QDoubleSpinBox(self.profitFieldsHost)
        self.spinProfitRate.setObjectName(u"spinProfitRate")
        self.spinProfitRate.setMinimumSize(QSize(96, 36))
        self.spinProfitRate.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.spinProfitRate.setDecimals(2)
        self.spinProfitRate.setMinimum(-999999.000000000000000)
        self.spinProfitRate.setMaximum(999999.000000000000000)
        self.spinProfitRate.setSingleStep(1.000000000000000)
        self.spinProfitRate.setValue(0.000000000000000)
        self.spinProfitRate.setReadOnly(False)
        self.spinProfitRate.setMaximumSize(QSize(96, 36))
        sizePolicy1.setHeightForWidth(self.spinProfitRate.sizePolicy().hasHeightForWidth())
        self.spinProfitRate.setSizePolicy(sizePolicy1)

        self.layout_spinProfitRate.addWidget(self.spinProfitRate)

        self.unit_spinProfitRate = QLabel(self.profitFieldsHost)
        self.unit_spinProfitRate.setObjectName(u"unit_spinProfitRate")
        self.unit_spinProfitRate.setMinimumSize(QSize(32, 36))
        self.unit_spinProfitRate.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.unit_spinProfitRate.setMaximumSize(QSize(32, 36))
        sizePolicy1.setHeightForWidth(self.unit_spinProfitRate.sizePolicy().hasHeightForWidth())
        self.unit_spinProfitRate.setSizePolicy(sizePolicy1)

        self.layout_spinProfitRate.addWidget(self.unit_spinProfitRate)


        self.profitFieldsGrid.addLayout(self.layout_spinProfitRate, 1, 2, 1, 1)

        self.layout_txtNoActivityPriceRmb = QHBoxLayout()
        self.layout_txtNoActivityPriceRmb.setSpacing(4)
        self.layout_txtNoActivityPriceRmb.setObjectName(u"layout_txtNoActivityPriceRmb")
        self.layout_txtNoActivityPriceRmb.setContentsMargins(0, 0, 0, 0)
        self.txtNoActivityPriceRmb = QDoubleSpinBox(self.profitFieldsHost)
        self.txtNoActivityPriceRmb.setObjectName(u"txtNoActivityPriceRmb")
        self.txtNoActivityPriceRmb.setMinimumSize(QSize(96, 36))
        self.txtNoActivityPriceRmb.setReadOnly(True)
        self.txtNoActivityPriceRmb.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.txtNoActivityPriceRmb.setDecimals(2)
        self.txtNoActivityPriceRmb.setMinimum(0.000000000000000)
        self.txtNoActivityPriceRmb.setMaximum(999999.000000000000000)
        self.txtNoActivityPriceRmb.setSingleStep(1.000000000000000)
        self.txtNoActivityPriceRmb.setValue(0.000000000000000)
        self.txtNoActivityPriceRmb.setMaximumSize(QSize(96, 36))
        sizePolicy1.setHeightForWidth(self.txtNoActivityPriceRmb.sizePolicy().hasHeightForWidth())
        self.txtNoActivityPriceRmb.setSizePolicy(sizePolicy1)

        self.layout_txtNoActivityPriceRmb.addWidget(self.txtNoActivityPriceRmb)

        self.unit_txtNoActivityPriceRmb = QLabel(self.profitFieldsHost)
        self.unit_txtNoActivityPriceRmb.setObjectName(u"unit_txtNoActivityPriceRmb")
        self.unit_txtNoActivityPriceRmb.setMinimumSize(QSize(32, 36))
        self.unit_txtNoActivityPriceRmb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.unit_txtNoActivityPriceRmb.setMaximumSize(QSize(32, 36))
        sizePolicy1.setHeightForWidth(self.unit_txtNoActivityPriceRmb.sizePolicy().hasHeightForWidth())
        self.unit_txtNoActivityPriceRmb.setSizePolicy(sizePolicy1)

        self.layout_txtNoActivityPriceRmb.addWidget(self.unit_txtNoActivityPriceRmb)


        self.profitFieldsGrid.addLayout(self.layout_txtNoActivityPriceRmb, 1, 3, 1, 1)

        self.layout_txtNoActivityPriceUsd = QHBoxLayout()
        self.layout_txtNoActivityPriceUsd.setSpacing(4)
        self.layout_txtNoActivityPriceUsd.setObjectName(u"layout_txtNoActivityPriceUsd")
        self.layout_txtNoActivityPriceUsd.setContentsMargins(0, 0, 0, 0)
        self.txtNoActivityPriceUsd = QDoubleSpinBox(self.profitFieldsHost)
        self.txtNoActivityPriceUsd.setObjectName(u"txtNoActivityPriceUsd")
        self.txtNoActivityPriceUsd.setMinimumSize(QSize(96, 36))
        self.txtNoActivityPriceUsd.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.txtNoActivityPriceUsd.setDecimals(2)
        self.txtNoActivityPriceUsd.setMinimum(0.000000000000000)
        self.txtNoActivityPriceUsd.setMaximum(999999.000000000000000)
        self.txtNoActivityPriceUsd.setSingleStep(1.000000000000000)
        self.txtNoActivityPriceUsd.setValue(0.000000000000000)
        self.txtNoActivityPriceUsd.setReadOnly(False)
        self.txtNoActivityPriceUsd.setMaximumSize(QSize(96, 36))
        sizePolicy1.setHeightForWidth(self.txtNoActivityPriceUsd.sizePolicy().hasHeightForWidth())
        self.txtNoActivityPriceUsd.setSizePolicy(sizePolicy1)

        self.layout_txtNoActivityPriceUsd.addWidget(self.txtNoActivityPriceUsd)

        self.unit_txtNoActivityPriceUsd = QLabel(self.profitFieldsHost)
        self.unit_txtNoActivityPriceUsd.setObjectName(u"unit_txtNoActivityPriceUsd")
        self.unit_txtNoActivityPriceUsd.setMinimumSize(QSize(32, 36))
        self.unit_txtNoActivityPriceUsd.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.unit_txtNoActivityPriceUsd.setMaximumSize(QSize(32, 36))
        sizePolicy1.setHeightForWidth(self.unit_txtNoActivityPriceUsd.sizePolicy().hasHeightForWidth())
        self.unit_txtNoActivityPriceUsd.setSizePolicy(sizePolicy1)

        self.layout_txtNoActivityPriceUsd.addWidget(self.unit_txtNoActivityPriceUsd)


        self.profitFieldsGrid.addLayout(self.layout_txtNoActivityPriceUsd, 2, 3, 1, 1)

        self.layout_txtNoActivityProfitRmb = QHBoxLayout()
        self.layout_txtNoActivityProfitRmb.setSpacing(4)
        self.layout_txtNoActivityProfitRmb.setObjectName(u"layout_txtNoActivityProfitRmb")
        self.layout_txtNoActivityProfitRmb.setContentsMargins(0, 0, 0, 0)
        self.txtNoActivityProfitRmb = QDoubleSpinBox(self.profitFieldsHost)
        self.txtNoActivityProfitRmb.setObjectName(u"txtNoActivityProfitRmb")
        self.txtNoActivityProfitRmb.setMinimumSize(QSize(96, 36))
        self.txtNoActivityProfitRmb.setReadOnly(False)
        self.txtNoActivityProfitRmb.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.txtNoActivityProfitRmb.setDecimals(2)
        self.txtNoActivityProfitRmb.setMinimum(-999999.000000000000000)
        self.txtNoActivityProfitRmb.setMaximum(999999.000000000000000)
        self.txtNoActivityProfitRmb.setSingleStep(1.000000000000000)
        self.txtNoActivityProfitRmb.setValue(0.000000000000000)
        self.txtNoActivityProfitRmb.setMaximumSize(QSize(96, 36))
        sizePolicy1.setHeightForWidth(self.txtNoActivityProfitRmb.sizePolicy().hasHeightForWidth())
        self.txtNoActivityProfitRmb.setSizePolicy(sizePolicy1)

        self.layout_txtNoActivityProfitRmb.addWidget(self.txtNoActivityProfitRmb)

        self.unit_txtNoActivityProfitRmb = QLabel(self.profitFieldsHost)
        self.unit_txtNoActivityProfitRmb.setObjectName(u"unit_txtNoActivityProfitRmb")
        self.unit_txtNoActivityProfitRmb.setMinimumSize(QSize(32, 36))
        self.unit_txtNoActivityProfitRmb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.unit_txtNoActivityProfitRmb.setMaximumSize(QSize(32, 36))
        sizePolicy1.setHeightForWidth(self.unit_txtNoActivityProfitRmb.sizePolicy().hasHeightForWidth())
        self.unit_txtNoActivityProfitRmb.setSizePolicy(sizePolicy1)

        self.layout_txtNoActivityProfitRmb.addWidget(self.unit_txtNoActivityProfitRmb)


        self.profitFieldsGrid.addLayout(self.layout_txtNoActivityProfitRmb, 1, 5, 1, 1)

        self.layout_txtNoActivityProfitUsd = QHBoxLayout()
        self.layout_txtNoActivityProfitUsd.setSpacing(4)
        self.layout_txtNoActivityProfitUsd.setObjectName(u"layout_txtNoActivityProfitUsd")
        self.layout_txtNoActivityProfitUsd.setContentsMargins(0, 0, 0, 0)
        self.txtNoActivityProfitUsd = QDoubleSpinBox(self.profitFieldsHost)
        self.txtNoActivityProfitUsd.setObjectName(u"txtNoActivityProfitUsd")
        self.txtNoActivityProfitUsd.setMinimumSize(QSize(96, 36))
        self.txtNoActivityProfitUsd.setReadOnly(True)
        self.txtNoActivityProfitUsd.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.txtNoActivityProfitUsd.setDecimals(2)
        self.txtNoActivityProfitUsd.setMinimum(-999999.000000000000000)
        self.txtNoActivityProfitUsd.setMaximum(999999.000000000000000)
        self.txtNoActivityProfitUsd.setSingleStep(1.000000000000000)
        self.txtNoActivityProfitUsd.setValue(0.000000000000000)
        self.txtNoActivityProfitUsd.setMaximumSize(QSize(96, 36))
        sizePolicy1.setHeightForWidth(self.txtNoActivityProfitUsd.sizePolicy().hasHeightForWidth())
        self.txtNoActivityProfitUsd.setSizePolicy(sizePolicy1)

        self.layout_txtNoActivityProfitUsd.addWidget(self.txtNoActivityProfitUsd)

        self.unit_txtNoActivityProfitUsd = QLabel(self.profitFieldsHost)
        self.unit_txtNoActivityProfitUsd.setObjectName(u"unit_txtNoActivityProfitUsd")
        self.unit_txtNoActivityProfitUsd.setMinimumSize(QSize(32, 36))
        self.unit_txtNoActivityProfitUsd.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.unit_txtNoActivityProfitUsd.setMaximumSize(QSize(32, 36))
        sizePolicy1.setHeightForWidth(self.unit_txtNoActivityProfitUsd.sizePolicy().hasHeightForWidth())
        self.unit_txtNoActivityProfitUsd.setSizePolicy(sizePolicy1)

        self.layout_txtNoActivityProfitUsd.addWidget(self.unit_txtNoActivityProfitUsd)


        self.profitFieldsGrid.addLayout(self.layout_txtNoActivityProfitUsd, 2, 5, 1, 1)

        self.layout_spinPromotionReserve = QHBoxLayout()
        self.layout_spinPromotionReserve.setSpacing(4)
        self.layout_spinPromotionReserve.setObjectName(u"layout_spinPromotionReserve")
        self.layout_spinPromotionReserve.setContentsMargins(0, 0, 0, 0)
        self.spinPromotionReserve = QDoubleSpinBox(self.profitFieldsHost)
        self.spinPromotionReserve.setObjectName(u"spinPromotionReserve")
        self.spinPromotionReserve.setMinimumSize(QSize(96, 36))
        self.spinPromotionReserve.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.spinPromotionReserve.setDecimals(2)
        self.spinPromotionReserve.setMinimum(0.000000000000000)
        self.spinPromotionReserve.setMaximum(999999.000000000000000)
        self.spinPromotionReserve.setSingleStep(1.000000000000000)
        self.spinPromotionReserve.setValue(10.000000000000000)
        self.spinPromotionReserve.setReadOnly(False)
        self.spinPromotionReserve.setMaximumSize(QSize(96, 36))
        sizePolicy1.setHeightForWidth(self.spinPromotionReserve.sizePolicy().hasHeightForWidth())
        self.spinPromotionReserve.setSizePolicy(sizePolicy1)

        self.layout_spinPromotionReserve.addWidget(self.spinPromotionReserve)

        self.unit_spinPromotionReserve = QLabel(self.profitFieldsHost)
        self.unit_spinPromotionReserve.setObjectName(u"unit_spinPromotionReserve")
        self.unit_spinPromotionReserve.setMinimumSize(QSize(32, 36))
        self.unit_spinPromotionReserve.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.unit_spinPromotionReserve.setMaximumSize(QSize(32, 36))
        sizePolicy1.setHeightForWidth(self.unit_spinPromotionReserve.sizePolicy().hasHeightForWidth())
        self.unit_spinPromotionReserve.setSizePolicy(sizePolicy1)

        self.layout_spinPromotionReserve.addWidget(self.unit_spinPromotionReserve)


        self.profitFieldsGrid.addLayout(self.layout_spinPromotionReserve, 1, 6, 1, 1)

        self.layout_txtActivityPriceRmb = QHBoxLayout()
        self.layout_txtActivityPriceRmb.setSpacing(4)
        self.layout_txtActivityPriceRmb.setObjectName(u"layout_txtActivityPriceRmb")
        self.layout_txtActivityPriceRmb.setContentsMargins(0, 0, 0, 0)
        self.txtActivityPriceRmb = QDoubleSpinBox(self.profitFieldsHost)
        self.txtActivityPriceRmb.setObjectName(u"txtActivityPriceRmb")
        self.txtActivityPriceRmb.setMinimumSize(QSize(96, 36))
        self.txtActivityPriceRmb.setReadOnly(True)
        self.txtActivityPriceRmb.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.txtActivityPriceRmb.setDecimals(2)
        self.txtActivityPriceRmb.setMinimum(0.000000000000000)
        self.txtActivityPriceRmb.setMaximum(999999.000000000000000)
        self.txtActivityPriceRmb.setSingleStep(1.000000000000000)
        self.txtActivityPriceRmb.setValue(0.000000000000000)
        self.txtActivityPriceRmb.setMaximumSize(QSize(96, 36))
        sizePolicy1.setHeightForWidth(self.txtActivityPriceRmb.sizePolicy().hasHeightForWidth())
        self.txtActivityPriceRmb.setSizePolicy(sizePolicy1)

        self.layout_txtActivityPriceRmb.addWidget(self.txtActivityPriceRmb)

        self.unit_txtActivityPriceRmb = QLabel(self.profitFieldsHost)
        self.unit_txtActivityPriceRmb.setObjectName(u"unit_txtActivityPriceRmb")
        self.unit_txtActivityPriceRmb.setMinimumSize(QSize(32, 36))
        self.unit_txtActivityPriceRmb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.unit_txtActivityPriceRmb.setMaximumSize(QSize(32, 36))
        sizePolicy1.setHeightForWidth(self.unit_txtActivityPriceRmb.sizePolicy().hasHeightForWidth())
        self.unit_txtActivityPriceRmb.setSizePolicy(sizePolicy1)

        self.layout_txtActivityPriceRmb.addWidget(self.unit_txtActivityPriceRmb)


        self.profitFieldsGrid.addLayout(self.layout_txtActivityPriceRmb, 1, 7, 1, 1)

        self.layout_txtActivityPriceUsd = QHBoxLayout()
        self.layout_txtActivityPriceUsd.setSpacing(4)
        self.layout_txtActivityPriceUsd.setObjectName(u"layout_txtActivityPriceUsd")
        self.layout_txtActivityPriceUsd.setContentsMargins(0, 0, 0, 0)
        self.txtActivityPriceUsd = QDoubleSpinBox(self.profitFieldsHost)
        self.txtActivityPriceUsd.setObjectName(u"txtActivityPriceUsd")
        self.txtActivityPriceUsd.setMinimumSize(QSize(96, 36))
        self.txtActivityPriceUsd.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.txtActivityPriceUsd.setDecimals(2)
        self.txtActivityPriceUsd.setMinimum(0.000000000000000)
        self.txtActivityPriceUsd.setMaximum(999999.000000000000000)
        self.txtActivityPriceUsd.setSingleStep(1.000000000000000)
        self.txtActivityPriceUsd.setValue(0.000000000000000)
        self.txtActivityPriceUsd.setReadOnly(True)
        self.txtActivityPriceUsd.setMaximumSize(QSize(96, 36))
        sizePolicy1.setHeightForWidth(self.txtActivityPriceUsd.sizePolicy().hasHeightForWidth())
        self.txtActivityPriceUsd.setSizePolicy(sizePolicy1)

        self.layout_txtActivityPriceUsd.addWidget(self.txtActivityPriceUsd)

        self.unit_txtActivityPriceUsd = QLabel(self.profitFieldsHost)
        self.unit_txtActivityPriceUsd.setObjectName(u"unit_txtActivityPriceUsd")
        self.unit_txtActivityPriceUsd.setMinimumSize(QSize(32, 36))
        self.unit_txtActivityPriceUsd.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.unit_txtActivityPriceUsd.setMaximumSize(QSize(32, 36))
        sizePolicy1.setHeightForWidth(self.unit_txtActivityPriceUsd.sizePolicy().hasHeightForWidth())
        self.unit_txtActivityPriceUsd.setSizePolicy(sizePolicy1)

        self.layout_txtActivityPriceUsd.addWidget(self.unit_txtActivityPriceUsd)


        self.profitFieldsGrid.addLayout(self.layout_txtActivityPriceUsd, 2, 7, 1, 1)

        self.layout_txtActivityProfitRmb = QHBoxLayout()
        self.layout_txtActivityProfitRmb.setSpacing(4)
        self.layout_txtActivityProfitRmb.setObjectName(u"layout_txtActivityProfitRmb")
        self.layout_txtActivityProfitRmb.setContentsMargins(0, 0, 0, 0)
        self.txtActivityProfitRmb = QDoubleSpinBox(self.profitFieldsHost)
        self.txtActivityProfitRmb.setObjectName(u"txtActivityProfitRmb")
        self.txtActivityProfitRmb.setMinimumSize(QSize(96, 36))
        self.txtActivityProfitRmb.setReadOnly(False)
        self.txtActivityProfitRmb.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.txtActivityProfitRmb.setDecimals(2)
        self.txtActivityProfitRmb.setMinimum(-999999.000000000000000)
        self.txtActivityProfitRmb.setMaximum(999999.000000000000000)
        self.txtActivityProfitRmb.setSingleStep(1.000000000000000)
        self.txtActivityProfitRmb.setValue(0.000000000000000)
        self.txtActivityProfitRmb.setMaximumSize(QSize(96, 36))
        self.txtActivityProfitRmb.setEnabled(True)
        sizePolicy1.setHeightForWidth(self.txtActivityProfitRmb.sizePolicy().hasHeightForWidth())
        self.txtActivityProfitRmb.setSizePolicy(sizePolicy1)

        self.layout_txtActivityProfitRmb.addWidget(self.txtActivityProfitRmb)

        self.unit_txtActivityProfitRmb = QLabel(self.profitFieldsHost)
        self.unit_txtActivityProfitRmb.setObjectName(u"unit_txtActivityProfitRmb")
        self.unit_txtActivityProfitRmb.setMinimumSize(QSize(32, 36))
        self.unit_txtActivityProfitRmb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.unit_txtActivityProfitRmb.setMaximumSize(QSize(32, 36))
        sizePolicy1.setHeightForWidth(self.unit_txtActivityProfitRmb.sizePolicy().hasHeightForWidth())
        self.unit_txtActivityProfitRmb.setSizePolicy(sizePolicy1)

        self.layout_txtActivityProfitRmb.addWidget(self.unit_txtActivityProfitRmb)


        self.profitFieldsGrid.addLayout(self.layout_txtActivityProfitRmb, 1, 8, 1, 1)

        self.layout_txtActivityProfitUsd = QHBoxLayout()
        self.layout_txtActivityProfitUsd.setSpacing(4)
        self.layout_txtActivityProfitUsd.setObjectName(u"layout_txtActivityProfitUsd")
        self.layout_txtActivityProfitUsd.setContentsMargins(0, 0, 0, 0)
        self.txtActivityProfitUsd = QDoubleSpinBox(self.profitFieldsHost)
        self.txtActivityProfitUsd.setObjectName(u"txtActivityProfitUsd")
        self.txtActivityProfitUsd.setMinimumSize(QSize(96, 36))
        self.txtActivityProfitUsd.setReadOnly(True)
        self.txtActivityProfitUsd.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.txtActivityProfitUsd.setDecimals(2)
        self.txtActivityProfitUsd.setMinimum(-999999.000000000000000)
        self.txtActivityProfitUsd.setMaximum(999999.000000000000000)
        self.txtActivityProfitUsd.setSingleStep(1.000000000000000)
        self.txtActivityProfitUsd.setValue(0.000000000000000)
        self.txtActivityProfitUsd.setMaximumSize(QSize(96, 36))
        sizePolicy1.setHeightForWidth(self.txtActivityProfitUsd.sizePolicy().hasHeightForWidth())
        self.txtActivityProfitUsd.setSizePolicy(sizePolicy1)

        self.layout_txtActivityProfitUsd.addWidget(self.txtActivityProfitUsd)

        self.unit_txtActivityProfitUsd = QLabel(self.profitFieldsHost)
        self.unit_txtActivityProfitUsd.setObjectName(u"unit_txtActivityProfitUsd")
        self.unit_txtActivityProfitUsd.setMinimumSize(QSize(32, 36))
        self.unit_txtActivityProfitUsd.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.unit_txtActivityProfitUsd.setMaximumSize(QSize(32, 36))
        sizePolicy1.setHeightForWidth(self.unit_txtActivityProfitUsd.sizePolicy().hasHeightForWidth())
        self.unit_txtActivityProfitUsd.setSizePolicy(sizePolicy1)

        self.layout_txtActivityProfitUsd.addWidget(self.unit_txtActivityProfitUsd)


        self.profitFieldsGrid.addLayout(self.layout_txtActivityProfitUsd, 2, 8, 1, 1)

        self.lblListPriceProfitRateTitle = QLabel(self.profitFieldsHost)
        self.lblListPriceProfitRateTitle.setObjectName(u"lblListPriceProfitRateTitle")

        self.profitFieldsGrid.addWidget(self.lblListPriceProfitRateTitle, 0, 4, 1, 1)

        self.txtListPriceProfitRate = QLabel(self.profitFieldsHost)
        self.txtListPriceProfitRate.setObjectName(u"txtListPriceProfitRate")
        self.txtListPriceProfitRate.setMinimumSize(QSize(96, 36))
        self.txtListPriceProfitRate.setMaximumSize(QSize(96, 36))
        sizePolicy1.setHeightForWidth(self.txtListPriceProfitRate.sizePolicy().hasHeightForWidth())
        self.txtListPriceProfitRate.setSizePolicy(sizePolicy1)
        self.txtListPriceProfitRate.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.profitFieldsGrid.addWidget(self.txtListPriceProfitRate, 1, 4, 1, 1)


        self.profitFieldsHostLayout.addLayout(self.profitFieldsGrid)


        self.profitLayout.addWidget(self.profitFieldsHost, 0, Qt.AlignmentFlag.AlignLeft)

        self.lblProfitConclusion = QLabel(profitPanel)
        self.lblProfitConclusion.setObjectName(u"lblProfitConclusion")
        self.lblProfitConclusion.setWordWrap(True)

        self.profitLayout.addWidget(self.lblProfitConclusion)


        self.retranslateUi(profitPanel)

        QMetaObject.connectSlotsByName(profitPanel)
    # setupUi

        # --- restored dynamic properties ---
        profitPanel.setProperty("card", True)
        self.lblProfitTitle.setProperty("sectionTitle", True)
        self.lblProfitHint.setProperty("hint", True)
        profitPanel.setProperty("sizeType", "QSizePolicy::Policy::Expanding")
        self.lblNoActivitySubsidyStatus.setProperty("subsidyStatus", True)
        self.lblNoActivitySubsidyStatus.setProperty("triggered", False)
        self.lblActivitySubsidyStatus.setProperty("subsidyStatus", True)
        self.lblActivitySubsidyStatus.setProperty("triggered", False)
        self.txtSheinPriceRmb.setProperty("preview", True)
        self.unit_txtSheinPriceRmb.setProperty("unitLabel", True)
        self.txtSheinPriceUsd.setProperty("preview", False)
        self.unit_txtSheinPriceUsd.setProperty("unitLabel", True)
        self.txtCalculatedCostRmb.setProperty("preview", False)
        self.unit_txtCalculatedCostRmb.setProperty("unitLabel", True)
        self.txtCalculatedCostUsd.setProperty("preview", True)
        self.unit_txtCalculatedCostUsd.setProperty("unitLabel", True)
        self.spinProfitRate.setProperty("preview", False)
        self.unit_spinProfitRate.setProperty("unitLabel", True)
        self.txtNoActivityPriceRmb.setProperty("preview", True)
        self.unit_txtNoActivityPriceRmb.setProperty("unitLabel", True)
        self.txtNoActivityPriceUsd.setProperty("preview", False)
        self.unit_txtNoActivityPriceUsd.setProperty("unitLabel", True)
        self.txtNoActivityProfitRmb.setProperty("preview", False)
        self.unit_txtNoActivityProfitRmb.setProperty("unitLabel", True)
        self.txtNoActivityProfitUsd.setProperty("preview", True)
        self.unit_txtNoActivityProfitUsd.setProperty("unitLabel", True)
        self.spinPromotionReserve.setProperty("preview", False)
        self.unit_spinPromotionReserve.setProperty("unitLabel", True)
        self.txtActivityPriceRmb.setProperty("preview", True)
        self.unit_txtActivityPriceRmb.setProperty("unitLabel", True)
        self.txtActivityPriceUsd.setProperty("preview", True)
        self.unit_txtActivityPriceUsd.setProperty("unitLabel", True)
        self.txtActivityProfitRmb.setProperty("preview", False)
        self.unit_txtActivityProfitRmb.setProperty("unitLabel", True)
        self.txtActivityProfitUsd.setProperty("preview", True)
        self.unit_txtActivityProfitUsd.setProperty("unitLabel", True)
        self.profitFieldsHost.setProperty("columnMinimumWidth", "140,140,140,140,140,140,140,140")
        self.txtListPriceProfitRate.setProperty("preview", True)
        self.lblProfitConclusion.setProperty("conclusion", True)

    def retranslateUi(self, profitPanel):
        self.lblProfitTitle.setText(QCoreApplication.translate("ProfitPanel", u"\u5229\u6da6\u6d4b\u7b97", None))
        self.lblProfitHint.setText(QCoreApplication.translate("ProfitPanel", u"\u5f53\u524d\u529f\u80fd\uff1a\u6309\u6700\u540e\u7f16\u8f91\u9879\u5b9e\u65f6\u53cd\u63a8\uff1b\u6d3b\u52a8\u540e\u5229\u6da6\u53ef\u7f16\u8f91\uff0c\u6d3b\u52a8\u9884\u7559\u6bd4\u4f8b\u4fdd\u6301\u72ec\u7acb\u3002", None))
        self.lblProfitRuleTitle.setText(QCoreApplication.translate("ProfitPanel", u"\u5229\u6da6\u89c4\u5219", None))
        self.cmbProfitRule.setItemText(0, QCoreApplication.translate("ProfitPanel", u"SHEIN 29\u7f8e\u5143\u4ee5\u4e0b\u8fd0\u8d39\u8865\u8d34", None))
        self.cmbProfitRule.setItemText(1, QCoreApplication.translate("ProfitPanel", u"\u65e0\u5229\u6da6\u8c03\u6574", None))
        self.cmbProfitRule.setItemText(2, QCoreApplication.translate("ProfitPanel", u"\u63a8\u5e7f\u6263\u9664\u793a\u4f8b", None))

        self.lblSheinPrice.setText(QCoreApplication.translate("ProfitPanel", u"SHEIN \u6838\u4ef7", None))
        self.lblProfitCost.setText(QCoreApplication.translate("ProfitPanel", u"\u8ba1\u7b97\u603b\u6210\u672c", None))
        self.lblProfitRate.setText(QCoreApplication.translate("ProfitPanel", u"\u5229\u6da6\u7387\uff08\u6d3b\u52a8\u540e\uff09", None))
        self.lblNoActivityPrice.setText(QCoreApplication.translate("ProfitPanel", u"SHEIN\u6807\u4ef7", None))
        self.lblNoActivityProfit.setText(QCoreApplication.translate("ProfitPanel", u"\u6807\u4ef7\u5229\u6da6", None))
        self.lblNoActivitySubsidyStatus.setText(QCoreApplication.translate("ProfitPanel", u"\u672a\u89e6\u53d1", None))
#if QT_CONFIG(tooltip)
        self.lblNoActivitySubsidyStatus.setToolTip(QCoreApplication.translate("ProfitPanel", u"\u6839\u636e\u8be5\u573a\u666f\u7f8e\u5143\u552e\u4ef7\u5355\u72ec\u5224\u65ad\u5f53\u524d\u5229\u6da6\u89c4\u5219\u662f\u5426\u89e6\u53d1", None))
#endif // QT_CONFIG(tooltip)
        self.lblPromotionReserve.setText(QCoreApplication.translate("ProfitPanel", u"\u6d3b\u52a8\u9884\u7559", None))
        self.lblActivityPrice.setText(QCoreApplication.translate("ProfitPanel", u"\u6d3b\u52a8\u540e\u552e\u4ef7", None))
        self.lblActivityProfit.setText(QCoreApplication.translate("ProfitPanel", u"\u6d3b\u52a8\u540e\u5229\u6da6", None))
        self.lblActivitySubsidyStatus.setText(QCoreApplication.translate("ProfitPanel", u"\u672a\u89e6\u53d1", None))
#if QT_CONFIG(tooltip)
        self.lblActivitySubsidyStatus.setToolTip(QCoreApplication.translate("ProfitPanel", u"\u6839\u636e\u8be5\u573a\u666f\u7f8e\u5143\u552e\u4ef7\u5355\u72ec\u5224\u65ad\u5f53\u524d\u5229\u6da6\u89c4\u5219\u662f\u5426\u89e6\u53d1", None))
#endif // QT_CONFIG(tooltip)
#if QT_CONFIG(tooltip)
        self.txtSheinPriceRmb.setToolTip(QCoreApplication.translate("ProfitPanel", u"\u7531\u7528\u6237\u8f93\u5165\u7684\u7f8e\u5143\u6838\u4ef7\u6309\u5f53\u524d\u6c47\u7387\u5b9e\u65f6\u6362\u7b97\uff1b\u4ec5\u8bb0\u5f55\u6bd4\u8f83\uff0c\u4e0d\u53c2\u4e0e\u5229\u6da6\u8ba1\u7b97", None))
#endif // QT_CONFIG(tooltip)
        self.unit_txtSheinPriceRmb.setText(QCoreApplication.translate("ProfitPanel", u"RMB", None))
#if QT_CONFIG(tooltip)
        self.txtSheinPriceUsd.setToolTip(QCoreApplication.translate("ProfitPanel", u"\u7528\u6237\u8f93\u5165 SHEIN \u6700\u7ec8\u6838\u4ef7\uff1b\u4ec5\u8bb0\u5f55\u6bd4\u8f83\uff0c\u4e0d\u53c2\u4e0e\u5229\u6da6\u8ba1\u7b97", None))
#endif // QT_CONFIG(tooltip)
        self.unit_txtSheinPriceUsd.setText(QCoreApplication.translate("ProfitPanel", u"USD", None))
#if QT_CONFIG(tooltip)
        self.txtCalculatedCostRmb.setToolTip(QCoreApplication.translate("ProfitPanel", u"\u5229\u6da6\u533a\u91c7\u7528\u7684\u8ba1\u7b97\u603b\u6210\u672c\uff1b\u624b\u52a8\u4fee\u6539\u53ea\u5f71\u54cd\u5229\u6da6\u533a\uff0c\u4e0d\u53cd\u5199\u4e0a\u65b9\u6210\u672c\u3001\u5305\u88c5\u6216\u7269\u6d41\uff0c\u5e76\u5b9e\u65f6\u66f4\u65b0\u5168\u90e8\u5229\u6da6\u7ed3\u679c\u3002", None))
#endif // QT_CONFIG(tooltip)
        self.unit_txtCalculatedCostRmb.setText(QCoreApplication.translate("ProfitPanel", u"RMB", None))
#if QT_CONFIG(tooltip)
        self.txtCalculatedCostUsd.setToolTip(QCoreApplication.translate("ProfitPanel", u"\u7531\u8ba1\u7b97\u603b\u6210\u672c\u4eba\u6c11\u5e01\u6309\u5f53\u524d\u6c47\u7387\u5b9e\u65f6\u6362\u7b97", None))
#endif // QT_CONFIG(tooltip)
        self.unit_txtCalculatedCostUsd.setText(QCoreApplication.translate("ProfitPanel", u"USD", None))
#if QT_CONFIG(tooltip)
        self.spinProfitRate.setToolTip(QCoreApplication.translate("ProfitPanel", u"\u6309\u6210\u672c\u8ba1\u7b97\u7684\u76ee\u6807\u5229\u6da6\u7387\uff1b\u7f16\u8f91\u540e\u53cd\u63a8\u6d3b\u52a8\u540e\u5229\u6da6\u3001\u6d3b\u52a8\u540e\u552e\u4ef7\u3001SHEIN\u6807\u4ef7\u548c\u6807\u4ef7\u5229\u6da6\u3002", None))
#endif // QT_CONFIG(tooltip)
        self.unit_spinProfitRate.setText(QCoreApplication.translate("ProfitPanel", u"%", None))
#if QT_CONFIG(tooltip)
        self.txtNoActivityPriceRmb.setToolTip(QCoreApplication.translate("ProfitPanel", u"\u7531\u65e0\u6d3b\u52a8\u552e\u4ef7\u7f8e\u5143\u6309\u5f53\u524d\u6c47\u7387\u5b9e\u65f6\u6362\u7b97", None))
#endif // QT_CONFIG(tooltip)
        self.unit_txtNoActivityPriceRmb.setText(QCoreApplication.translate("ProfitPanel", u"RMB", None))
#if QT_CONFIG(tooltip)
        self.txtNoActivityPriceUsd.setToolTip(QCoreApplication.translate("ProfitPanel", u"\u7528\u6237\u5728 SHEIN \u5e97\u94fa\u586b\u5199\u7684\u771f\u5b9e\u6807\u4ef7\uff1b\u7f16\u8f91\u540e\u91cd\u7b97\u6807\u4ef7\u5229\u6da6\u3001\u6d3b\u52a8\u540e\u552e\u4ef7\u3001\u6d3b\u52a8\u540e\u5229\u6da6\u548c\u5229\u6da6\u7387\u3002", None))
#endif // QT_CONFIG(tooltip)
        self.unit_txtNoActivityPriceUsd.setText(QCoreApplication.translate("ProfitPanel", u"USD", None))
#if QT_CONFIG(tooltip)
        self.txtNoActivityProfitRmb.setToolTip(QCoreApplication.translate("ProfitPanel", u"\u6807\u4ef7\u573a\u666f\u4eba\u6c11\u5e01\u5229\u6da6\u53ef\u7f16\u8f91\uff1b\u7f16\u8f91\u540e\u53cd\u63a8SHEIN\u6807\u4ef7\uff0c\u5e76\u540c\u6b65\u6d3b\u52a8\u540e\u573a\u666f\u4e0e\u5229\u6da6\u7387\u3002", None))
#endif // QT_CONFIG(tooltip)
        self.unit_txtNoActivityProfitRmb.setText(QCoreApplication.translate("ProfitPanel", u"RMB", None))
#if QT_CONFIG(tooltip)
        self.txtNoActivityProfitUsd.setToolTip(QCoreApplication.translate("ProfitPanel", u"\u7531\u65e0\u6d3b\u52a8\u5229\u6da6\u4eba\u6c11\u5e01\u6309\u5f53\u524d\u6c47\u7387\u5b9e\u65f6\u6362\u7b97", None))
#endif // QT_CONFIG(tooltip)
        self.unit_txtNoActivityProfitUsd.setText(QCoreApplication.translate("ProfitPanel", u"USD", None))
#if QT_CONFIG(tooltip)
        self.spinPromotionReserve.setToolTip(QCoreApplication.translate("ProfitPanel", u"\u6d3b\u52a8\u6216\u964d\u4ef7\u9884\u7559\u6bd4\u4f8b\uff1b\u7f16\u8f91\u540e\u4fdd\u6301\u5f53\u524d\u8ba1\u7b97\u76ee\u6807\uff0c\u91cd\u65b0\u63a8\u6f14\u6d3b\u52a8\u540e\u552e\u4ef7\u3001\u6d3b\u52a8\u540e\u5229\u6da6\u53ca\u4e24\u4e2a\u573a\u666f\u7684\u8865\u8d34\u72b6\u6001\u3002", None))
#endif // QT_CONFIG(tooltip)
        self.unit_spinPromotionReserve.setText(QCoreApplication.translate("ProfitPanel", u"%", None))
#if QT_CONFIG(tooltip)
        self.txtActivityPriceRmb.setToolTip(QCoreApplication.translate("ProfitPanel", u"\u7531\u65e0\u6d3b\u52a8\u552e\u4ef7\u548c\u6d3b\u52a8\u9884\u7559\u81ea\u52a8\u8ba1\u7b97\uff0c\u518d\u6309\u5f53\u524d\u6c47\u7387\u663e\u793a\u4eba\u6c11\u5e01\uff1b\u4e0d\u53ef\u76f4\u63a5\u7f16\u8f91\u3002", None))
#endif // QT_CONFIG(tooltip)
        self.unit_txtActivityPriceRmb.setText(QCoreApplication.translate("ProfitPanel", u"RMB", None))
#if QT_CONFIG(tooltip)
        self.txtActivityPriceUsd.setToolTip(QCoreApplication.translate("ProfitPanel", u"\u7531\u65e0\u6d3b\u52a8\u552e\u4ef7 \u00d7\uff081\uff0d\u6d3b\u52a8\u9884\u7559\u6bd4\u4f8b\uff09\u5b9e\u65f6\u8ba1\u7b97\uff1b\u4e0d\u53ef\u76f4\u63a5\u7f16\u8f91\u3002", None))
#endif // QT_CONFIG(tooltip)
        self.unit_txtActivityPriceUsd.setText(QCoreApplication.translate("ProfitPanel", u"USD", None))
#if QT_CONFIG(tooltip)
        self.txtActivityProfitRmb.setToolTip(QCoreApplication.translate("ProfitPanel", u"\u6d3b\u52a8\u540e\u5229\u6da6\u4eba\u6c11\u5e01\u53ef\u7f16\u8f91\uff1b\u7f16\u8f91\u540e\u4fdd\u6301\u6d3b\u52a8\u9884\u7559\u6bd4\u4f8b\u4e0d\u53d8\uff0c\u53cd\u63a8\u6d3b\u52a8\u540e\u552e\u4ef7\u3001\u65e0\u6d3b\u52a8\u552e\u4ef7\u3001\u65e0\u6d3b\u52a8\u5229\u6da6\u548c\u5229\u6da6\u7387\u3002", None))
#endif // QT_CONFIG(tooltip)
        self.unit_txtActivityProfitRmb.setText(QCoreApplication.translate("ProfitPanel", u"RMB", None))
#if QT_CONFIG(tooltip)
        self.txtActivityProfitUsd.setToolTip(QCoreApplication.translate("ProfitPanel", u"\u7531\u6d3b\u52a8\u540e\u5229\u6da6\u4eba\u6c11\u5e01\u6309\u5f53\u524d\u6c47\u7387\u5b9e\u65f6\u6362\u7b97\uff1b\u4e0d\u53ef\u76f4\u63a5\u7f16\u8f91\u3002", None))
#endif // QT_CONFIG(tooltip)
        self.unit_txtActivityProfitUsd.setText(QCoreApplication.translate("ProfitPanel", u"USD", None))
        self.lblListPriceProfitRateTitle.setText(QCoreApplication.translate("ProfitPanel", u"\u6807\u4ef7\u5229\u7387", None))
#if QT_CONFIG(tooltip)
        self.lblListPriceProfitRateTitle.setToolTip(QCoreApplication.translate("ProfitPanel", u"\u6807\u4ef7\u5229\u6da6RMB \u00f7 \u8ba1\u7b97\u603b\u6210\u672cRMB \u00d7 100%\uff1b\u51bb\u7ed3\u53ea\u8bfb", None))
#endif // QT_CONFIG(tooltip)
        self.txtListPriceProfitRate.setText(QCoreApplication.translate("ProfitPanel", u"--", None))
#if QT_CONFIG(tooltip)
        self.txtListPriceProfitRate.setToolTip(QCoreApplication.translate("ProfitPanel", u"\u6807\u4ef7\u5229\u6da6RMB \u00f7 \u8ba1\u7b97\u603b\u6210\u672cRMB \u00d7 100%\uff1b\u53ea\u8bfb", None))
#endif // QT_CONFIG(tooltip)
        self.lblProfitConclusion.setText(QCoreApplication.translate("ProfitPanel", u"SHEIN\u6838\u4ef7\u4ec5\u8bb0\u5f55\u6bd4\u8f83\uff0c\u4e0d\u53c2\u4e0e\u8ba1\u7b97\uff1b\u8ba1\u7b97\u603b\u6210\u672c\u53ef\u5728\u5229\u6da6\u533a\u8986\u5199\uff1b\u5229\u6da6\u7387\u3001SHEIN\u6807\u4ef7\u3001\u6807\u4ef7\u5229\u6da6\u6216\u6d3b\u52a8\u540e\u5229\u6da6\u4efb\u4e00\u9879\u7f16\u8f91\u540e\u540c\u6b65\u5176\u4f59\u7ed3\u679c\uff1b\u7f16\u8f91\u6d3b\u52a8\u540e\u5229\u6da6\u65f6\u4fdd\u6301\u6d3b\u52a8\u9884\u7559\u4e0d\u53d8\uff0c\u5e76\u5206\u522b\u66f4\u65b0\u4e24\u4e2a\u552e\u4ef7\u3001\u5229\u6da6\u53ca\u8865\u8d34\u72b6\u6001\u3002", None))
        pass
    # retranslateUi

