# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file '_image_ai_clean.ui'
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
from PySide6.QtWidgets import (QApplication, QFrame, QGridLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QSizePolicy,
    QSpacerItem, QVBoxLayout, QWidget)

class Ui_ImageAIPanel(object):
    def setupUi(self, imageAIPanel):
        if not imageAIPanel.objectName():
            imageAIPanel.setObjectName(u"imageAIPanel")
        self.imageAIPanelLayout = QVBoxLayout(imageAIPanel)
        self.imageAIPanelLayout.setSpacing(0)
        self.imageAIPanelLayout.setObjectName(u"imageAIPanelLayout")
        self.imageAIPanelLayout.setContentsMargins(0, 0, 0, 0)
        self.imageInputSection = QFrame(imageAIPanel)
        self.imageInputSection.setObjectName(u"imageInputSection")
        self.imageInputLayout = QVBoxLayout(self.imageInputSection)
        self.imageInputLayout.setSpacing(9)
        self.imageInputLayout.setObjectName(u"imageInputLayout")
        self.imageInputLayout.setContentsMargins(14, 12, 14, 12)
        self.imageHeaderLayout = QHBoxLayout()
        self.imageHeaderLayout.setSpacing(8)
        self.imageHeaderLayout.setObjectName(u"imageHeaderLayout")
        self.imageHeaderLayout.setContentsMargins(0, 0, 0, 0)
        self.lblImageSectionTitle = QLabel(self.imageInputSection)
        self.lblImageSectionTitle.setObjectName(u"lblImageSectionTitle")

        self.imageHeaderLayout.addWidget(self.lblImageSectionTitle)

        self.lblImageSectionHint = QLabel(self.imageInputSection)
        self.lblImageSectionHint.setObjectName(u"lblImageSectionHint")

        self.imageHeaderLayout.addWidget(self.lblImageSectionHint)

        self.imageHeaderSpacer = QSpacerItem(20, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.imageHeaderLayout.addItem(self.imageHeaderSpacer)

        self.btnDecreaseImageSlots = QPushButton(self.imageInputSection)
        self.btnDecreaseImageSlots.setObjectName(u"btnDecreaseImageSlots")
        self.btnDecreaseImageSlots.setMinimumSize(QSize(34, 32))
        self.btnDecreaseImageSlots.setMaximumSize(QSize(34, 32))

        self.imageHeaderLayout.addWidget(self.btnDecreaseImageSlots)

        self.lblImageSlotCount = QLabel(self.imageInputSection)
        self.lblImageSlotCount.setObjectName(u"lblImageSlotCount")
        self.lblImageSlotCount.setMinimumSize(QSize(30, 30))
        self.lblImageSlotCount.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.imageHeaderLayout.addWidget(self.lblImageSlotCount)

        self.btnIncreaseImageSlots = QPushButton(self.imageInputSection)
        self.btnIncreaseImageSlots.setObjectName(u"btnIncreaseImageSlots")
        self.btnIncreaseImageSlots.setMinimumSize(QSize(34, 32))
        self.btnIncreaseImageSlots.setMaximumSize(QSize(34, 32))

        self.imageHeaderLayout.addWidget(self.btnIncreaseImageSlots)

        self.btnSaveImageLayout = QPushButton(self.imageInputSection)
        self.btnSaveImageLayout.setObjectName(u"btnSaveImageLayout")
        self.btnSaveImageLayout.setMinimumSize(QSize(130, 34))

        self.imageHeaderLayout.addWidget(self.btnSaveImageLayout)

        self.btnAiRecognize = QPushButton(self.imageInputSection)
        self.btnAiRecognize.setObjectName(u"btnAiRecognize")
        self.btnAiRecognize.setMinimumSize(QSize(98, 36))

        self.imageHeaderLayout.addWidget(self.btnAiRecognize)


        self.imageInputLayout.addLayout(self.imageHeaderLayout)

        self.imageSlotsLayout = QHBoxLayout()
        self.imageSlotsLayout.setSpacing(10)
        self.imageSlotsLayout.setObjectName(u"imageSlotsLayout")
        self.imageSlotsLayout.setContentsMargins(0, 0, 0, 0)
        self.imageCard1 = QFrame(self.imageInputSection)
        self.imageCard1.setObjectName(u"imageCard1")
        self.imageCard1.setMinimumSize(QSize(210, 180))
        self.imageCard1Layout = QVBoxLayout(self.imageCard1)
        self.imageCard1Layout.setSpacing(6)
        self.imageCard1Layout.setObjectName(u"imageCard1Layout")
        self.imageCard1Layout.setContentsMargins(8, 8, 8, 8)
        self.imageCard1HeaderLayout = QHBoxLayout()
        self.imageCard1HeaderLayout.setSpacing(5)
        self.imageCard1HeaderLayout.setObjectName(u"imageCard1HeaderLayout")
        self.imageCard1HeaderLayout.setContentsMargins(0, 0, 0, 0)
        self.lblImageNumber1 = QLabel(self.imageCard1)
        self.lblImageNumber1.setObjectName(u"lblImageNumber1")

        self.imageCard1HeaderLayout.addWidget(self.lblImageNumber1)

        self.imageCard1Spacer = QSpacerItem(20, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.imageCard1HeaderLayout.addItem(self.imageCard1Spacer)

        self.btnUploadImage1 = QPushButton(self.imageCard1)
        self.btnUploadImage1.setObjectName(u"btnUploadImage1")
        self.btnUploadImage1.setMinimumSize(QSize(58, 30))
        self.btnUploadImage1.setMaximumSize(QSize(70, 30))

        self.imageCard1HeaderLayout.addWidget(self.btnUploadImage1)

        self.btnDeleteImage1 = QPushButton(self.imageCard1)
        self.btnDeleteImage1.setObjectName(u"btnDeleteImage1")
        self.btnDeleteImage1.setMinimumSize(QSize(58, 30))
        self.btnDeleteImage1.setMaximumSize(QSize(70, 30))

        self.imageCard1HeaderLayout.addWidget(self.btnDeleteImage1)


        self.imageCard1Layout.addLayout(self.imageCard1HeaderLayout)

        self.lblImageDropZone1 = QLabel(self.imageCard1)
        self.lblImageDropZone1.setObjectName(u"lblImageDropZone1")
        self.lblImageDropZone1.setMinimumSize(QSize(0, 130))
        self.lblImageDropZone1.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lblImageDropZone1.setWordWrap(True)

        self.imageCard1Layout.addWidget(self.lblImageDropZone1)


        self.imageSlotsLayout.addWidget(self.imageCard1)

        self.imageCard2 = QFrame(self.imageInputSection)
        self.imageCard2.setObjectName(u"imageCard2")
        self.imageCard2.setMinimumSize(QSize(210, 180))
        self.imageCard2Layout = QVBoxLayout(self.imageCard2)
        self.imageCard2Layout.setSpacing(6)
        self.imageCard2Layout.setObjectName(u"imageCard2Layout")
        self.imageCard2Layout.setContentsMargins(8, 8, 8, 8)
        self.imageCard2HeaderLayout = QHBoxLayout()
        self.imageCard2HeaderLayout.setSpacing(5)
        self.imageCard2HeaderLayout.setObjectName(u"imageCard2HeaderLayout")
        self.imageCard2HeaderLayout.setContentsMargins(0, 0, 0, 0)
        self.lblImageNumber2 = QLabel(self.imageCard2)
        self.lblImageNumber2.setObjectName(u"lblImageNumber2")

        self.imageCard2HeaderLayout.addWidget(self.lblImageNumber2)

        self.imageCard2Spacer = QSpacerItem(20, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.imageCard2HeaderLayout.addItem(self.imageCard2Spacer)

        self.btnUploadImage2 = QPushButton(self.imageCard2)
        self.btnUploadImage2.setObjectName(u"btnUploadImage2")
        self.btnUploadImage2.setMinimumSize(QSize(58, 30))
        self.btnUploadImage2.setMaximumSize(QSize(70, 30))

        self.imageCard2HeaderLayout.addWidget(self.btnUploadImage2)

        self.btnDeleteImage2 = QPushButton(self.imageCard2)
        self.btnDeleteImage2.setObjectName(u"btnDeleteImage2")
        self.btnDeleteImage2.setMinimumSize(QSize(58, 30))
        self.btnDeleteImage2.setMaximumSize(QSize(70, 30))

        self.imageCard2HeaderLayout.addWidget(self.btnDeleteImage2)


        self.imageCard2Layout.addLayout(self.imageCard2HeaderLayout)

        self.lblImageDropZone2 = QLabel(self.imageCard2)
        self.lblImageDropZone2.setObjectName(u"lblImageDropZone2")
        self.lblImageDropZone2.setMinimumSize(QSize(0, 130))
        self.lblImageDropZone2.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lblImageDropZone2.setWordWrap(True)

        self.imageCard2Layout.addWidget(self.lblImageDropZone2)


        self.imageSlotsLayout.addWidget(self.imageCard2)

        self.imageCard3 = QFrame(self.imageInputSection)
        self.imageCard3.setObjectName(u"imageCard3")
        self.imageCard3.setMinimumSize(QSize(210, 180))
        self.imageCard3Layout = QVBoxLayout(self.imageCard3)
        self.imageCard3Layout.setSpacing(6)
        self.imageCard3Layout.setObjectName(u"imageCard3Layout")
        self.imageCard3Layout.setContentsMargins(8, 8, 8, 8)
        self.imageCard3HeaderLayout = QHBoxLayout()
        self.imageCard3HeaderLayout.setSpacing(5)
        self.imageCard3HeaderLayout.setObjectName(u"imageCard3HeaderLayout")
        self.imageCard3HeaderLayout.setContentsMargins(0, 0, 0, 0)
        self.lblImageNumber3 = QLabel(self.imageCard3)
        self.lblImageNumber3.setObjectName(u"lblImageNumber3")

        self.imageCard3HeaderLayout.addWidget(self.lblImageNumber3)

        self.imageCard3Spacer = QSpacerItem(20, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.imageCard3HeaderLayout.addItem(self.imageCard3Spacer)

        self.btnUploadImage3 = QPushButton(self.imageCard3)
        self.btnUploadImage3.setObjectName(u"btnUploadImage3")
        self.btnUploadImage3.setMinimumSize(QSize(58, 30))
        self.btnUploadImage3.setMaximumSize(QSize(70, 30))

        self.imageCard3HeaderLayout.addWidget(self.btnUploadImage3)

        self.btnDeleteImage3 = QPushButton(self.imageCard3)
        self.btnDeleteImage3.setObjectName(u"btnDeleteImage3")
        self.btnDeleteImage3.setMinimumSize(QSize(58, 30))
        self.btnDeleteImage3.setMaximumSize(QSize(70, 30))

        self.imageCard3HeaderLayout.addWidget(self.btnDeleteImage3)


        self.imageCard3Layout.addLayout(self.imageCard3HeaderLayout)

        self.lblImageDropZone3 = QLabel(self.imageCard3)
        self.lblImageDropZone3.setObjectName(u"lblImageDropZone3")
        self.lblImageDropZone3.setMinimumSize(QSize(0, 130))
        self.lblImageDropZone3.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lblImageDropZone3.setWordWrap(True)

        self.imageCard3Layout.addWidget(self.lblImageDropZone3)


        self.imageSlotsLayout.addWidget(self.imageCard3)

        self.imageCard4 = QFrame(self.imageInputSection)
        self.imageCard4.setObjectName(u"imageCard4")
        self.imageCard4.setMinimumSize(QSize(210, 180))
        self.imageCard4Layout = QVBoxLayout(self.imageCard4)
        self.imageCard4Layout.setSpacing(6)
        self.imageCard4Layout.setObjectName(u"imageCard4Layout")
        self.imageCard4Layout.setContentsMargins(8, 8, 8, 8)
        self.imageCard4HeaderLayout = QHBoxLayout()
        self.imageCard4HeaderLayout.setSpacing(5)
        self.imageCard4HeaderLayout.setObjectName(u"imageCard4HeaderLayout")
        self.imageCard4HeaderLayout.setContentsMargins(0, 0, 0, 0)
        self.lblImageNumber4 = QLabel(self.imageCard4)
        self.lblImageNumber4.setObjectName(u"lblImageNumber4")

        self.imageCard4HeaderLayout.addWidget(self.lblImageNumber4)

        self.imageCard4Spacer = QSpacerItem(20, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.imageCard4HeaderLayout.addItem(self.imageCard4Spacer)

        self.btnUploadImage4 = QPushButton(self.imageCard4)
        self.btnUploadImage4.setObjectName(u"btnUploadImage4")
        self.btnUploadImage4.setMinimumSize(QSize(58, 30))
        self.btnUploadImage4.setMaximumSize(QSize(70, 30))

        self.imageCard4HeaderLayout.addWidget(self.btnUploadImage4)

        self.btnDeleteImage4 = QPushButton(self.imageCard4)
        self.btnDeleteImage4.setObjectName(u"btnDeleteImage4")
        self.btnDeleteImage4.setMinimumSize(QSize(58, 30))
        self.btnDeleteImage4.setMaximumSize(QSize(70, 30))

        self.imageCard4HeaderLayout.addWidget(self.btnDeleteImage4)


        self.imageCard4Layout.addLayout(self.imageCard4HeaderLayout)

        self.lblImageDropZone4 = QLabel(self.imageCard4)
        self.lblImageDropZone4.setObjectName(u"lblImageDropZone4")
        self.lblImageDropZone4.setMinimumSize(QSize(0, 130))
        self.lblImageDropZone4.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lblImageDropZone4.setWordWrap(True)

        self.imageCard4Layout.addWidget(self.lblImageDropZone4)


        self.imageSlotsLayout.addWidget(self.imageCard4)

        self.imageCard5 = QFrame(self.imageInputSection)
        self.imageCard5.setObjectName(u"imageCard5")
        self.imageCard5.setMinimumSize(QSize(210, 180))
        self.imageCard5Layout = QVBoxLayout(self.imageCard5)
        self.imageCard5Layout.setSpacing(6)
        self.imageCard5Layout.setObjectName(u"imageCard5Layout")
        self.imageCard5Layout.setContentsMargins(8, 8, 8, 8)
        self.imageCard5HeaderLayout = QHBoxLayout()
        self.imageCard5HeaderLayout.setSpacing(5)
        self.imageCard5HeaderLayout.setObjectName(u"imageCard5HeaderLayout")
        self.imageCard5HeaderLayout.setContentsMargins(0, 0, 0, 0)
        self.lblImageNumber5 = QLabel(self.imageCard5)
        self.lblImageNumber5.setObjectName(u"lblImageNumber5")

        self.imageCard5HeaderLayout.addWidget(self.lblImageNumber5)

        self.imageCard5Spacer = QSpacerItem(20, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.imageCard5HeaderLayout.addItem(self.imageCard5Spacer)

        self.btnUploadImage5 = QPushButton(self.imageCard5)
        self.btnUploadImage5.setObjectName(u"btnUploadImage5")
        self.btnUploadImage5.setMinimumSize(QSize(58, 30))
        self.btnUploadImage5.setMaximumSize(QSize(70, 30))

        self.imageCard5HeaderLayout.addWidget(self.btnUploadImage5)

        self.btnDeleteImage5 = QPushButton(self.imageCard5)
        self.btnDeleteImage5.setObjectName(u"btnDeleteImage5")
        self.btnDeleteImage5.setMinimumSize(QSize(58, 30))
        self.btnDeleteImage5.setMaximumSize(QSize(70, 30))

        self.imageCard5HeaderLayout.addWidget(self.btnDeleteImage5)


        self.imageCard5Layout.addLayout(self.imageCard5HeaderLayout)

        self.lblImageDropZone5 = QLabel(self.imageCard5)
        self.lblImageDropZone5.setObjectName(u"lblImageDropZone5")
        self.lblImageDropZone5.setMinimumSize(QSize(0, 130))
        self.lblImageDropZone5.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lblImageDropZone5.setWordWrap(True)

        self.imageCard5Layout.addWidget(self.lblImageDropZone5)


        self.imageSlotsLayout.addWidget(self.imageCard5)

        self.imageSlotsLayout.setStretch(0, 1)
        self.imageSlotsLayout.setStretch(1, 1)
        self.imageSlotsLayout.setStretch(2, 1)
        self.imageSlotsLayout.setStretch(3, 1)
        self.imageSlotsLayout.setStretch(4, 1)

        self.imageInputLayout.addLayout(self.imageSlotsLayout)


        self.imageAIPanelLayout.addWidget(self.imageInputSection)

        self.aiSummarySection = QFrame(imageAIPanel)
        self.aiSummarySection.setObjectName(u"aiSummarySection")
        self.aiSummaryLayout = QGridLayout(self.aiSummarySection)
        self.aiSummaryLayout.setSpacing(8)
        self.aiSummaryLayout.setObjectName(u"aiSummaryLayout")
        self.aiSummaryLayout.setContentsMargins(14, 10, 14, 10)
        self.lblAiSummaryTitle = QLabel(self.aiSummarySection)
        self.lblAiSummaryTitle.setObjectName(u"lblAiSummaryTitle")

        self.aiSummaryLayout.addWidget(self.lblAiSummaryTitle, 0, 0, 1, 1)

        self.txtAiSummary = QLineEdit(self.aiSummarySection)
        self.txtAiSummary.setObjectName(u"txtAiSummary")

        self.aiSummaryLayout.addWidget(self.txtAiSummary, 0, 1, 1, 1)

        self.lblPackingStateTitle = QLabel(self.aiSummarySection)
        self.lblPackingStateTitle.setObjectName(u"lblPackingStateTitle")

        self.aiSummaryLayout.addWidget(self.lblPackingStateTitle, 0, 2, 1, 1)

        self.txtPackingState = QLineEdit(self.aiSummarySection)
        self.txtPackingState.setObjectName(u"txtPackingState")

        self.aiSummaryLayout.addWidget(self.txtPackingState, 0, 3, 1, 1)

        self.btnPartialReestimate = QPushButton(self.aiSummarySection)
        self.btnPartialReestimate.setObjectName(u"btnPartialReestimate")
        self.btnPartialReestimate.setMinimumSize(QSize(110, 36))

        self.aiSummaryLayout.addWidget(self.btnPartialReestimate, 0, 4, 1, 1)

        self.aiSummaryLayout.setColumnStretch(1, 5)
        self.aiSummaryLayout.setColumnStretch(3, 2)

        self.imageAIPanelLayout.addWidget(self.aiSummarySection)


        self.retranslateUi(imageAIPanel)

        QMetaObject.connectSlotsByName(imageAIPanel)
    # setupUi

        # --- restored dynamic properties ---
        self.imageInputSection.setProperty("card", True)
        self.lblImageSectionTitle.setProperty("sectionTitle", True)
        self.lblImageSectionHint.setProperty("hint", True)
        self.imageInputSection.setProperty("sizeType", "QSizePolicy::Policy::Expanding")
        self.btnAiRecognize.setProperty("primary", True)
        self.imageCard1.setProperty("sizeType", "QSizePolicy::Policy::Expanding")
        self.lblImageDropZone1.setProperty("dropZone", True)
        self.imageCard1.setProperty("uiPlaceholder", True)
        self.imageCard2.setProperty("sizeType", "QSizePolicy::Policy::Expanding")
        self.lblImageDropZone2.setProperty("dropZone", True)
        self.imageCard2.setProperty("uiPlaceholder", True)
        self.imageCard3.setProperty("sizeType", "QSizePolicy::Policy::Expanding")
        self.lblImageDropZone3.setProperty("dropZone", True)
        self.imageCard3.setProperty("uiPlaceholder", True)
        self.imageCard4.setProperty("sizeType", "QSizePolicy::Policy::Expanding")
        self.lblImageDropZone4.setProperty("dropZone", True)
        self.imageCard4.setProperty("uiPlaceholder", True)
        self.imageCard5.setProperty("sizeType", "QSizePolicy::Policy::Expanding")
        self.lblImageDropZone5.setProperty("dropZone", True)
        self.imageCard5.setProperty("uiPlaceholder", True)
        self.aiSummarySection.setProperty("card", True)
        self.lblAiSummaryTitle.setProperty("sectionTitle", True)

    def retranslateUi(self, imageAIPanel):
        self.lblImageSectionTitle.setText(QCoreApplication.translate("ImageAIPanel", u"\u56fe\u7247\u8f93\u5165", None))
        self.lblImageSectionHint.setText(QCoreApplication.translate("ImageAIPanel", u"\u5f53\u524d\u529f\u80fd\uff1a\u52a8\u6001 3\u20136 \u4e2a\u56fe\u7247\u6846\uff0c\u987a\u5e8f\u4e0d\u5f71\u54cd\u591a\u56fe\u8bc6\u522b", None))
        self.btnDecreaseImageSlots.setText(QCoreApplication.translate("ImageAIPanel", u"\u2212", None))
        self.lblImageSlotCount.setText(QCoreApplication.translate("ImageAIPanel", u"5", None))
        self.btnIncreaseImageSlots.setText(QCoreApplication.translate("ImageAIPanel", u"\uff0b", None))
        self.btnSaveImageLayout.setText(QCoreApplication.translate("ImageAIPanel", u"\u4fdd\u5b58\u56fe\u7247\u6846\u914d\u7f6e", None))
        self.btnAiRecognize.setText(QCoreApplication.translate("ImageAIPanel", u"AI\u8bc6\u56fe", None))
        self.lblImageNumber1.setText(QCoreApplication.translate("ImageAIPanel", u"\u56fe\u7247 1", None))
#if QT_CONFIG(tooltip)
        self.btnUploadImage1.setToolTip(QCoreApplication.translate("ImageAIPanel", u"\u4e0a\u4f20\u7b2c 1 \u5f20\u56fe\u7247", None))
#endif // QT_CONFIG(tooltip)
        self.btnUploadImage1.setText(QCoreApplication.translate("ImageAIPanel", u"\u4e0a\u4f20", None))
#if QT_CONFIG(tooltip)
        self.btnDeleteImage1.setToolTip(QCoreApplication.translate("ImageAIPanel", u"\u5220\u9664\u7b2c 1 \u5f20\u56fe\u7247", None))
#endif // QT_CONFIG(tooltip)
        self.btnDeleteImage1.setText(QCoreApplication.translate("ImageAIPanel", u"\u5220\u9664", None))
        self.lblImageDropZone1.setText(QCoreApplication.translate("ImageAIPanel", u"\u2601\n"
"\u8fd0\u884c\u65f6\u751f\u6210\u56fe\u7247\u6846\n"
"\u652f\u6301\u4e0a\u4f20 / \u62d6\u62fd / Ctrl+V", None))
        self.lblImageNumber2.setText(QCoreApplication.translate("ImageAIPanel", u"\u56fe\u7247 2", None))
#if QT_CONFIG(tooltip)
        self.btnUploadImage2.setToolTip(QCoreApplication.translate("ImageAIPanel", u"\u4e0a\u4f20\u7b2c 2 \u5f20\u56fe\u7247", None))
#endif // QT_CONFIG(tooltip)
        self.btnUploadImage2.setText(QCoreApplication.translate("ImageAIPanel", u"\u4e0a\u4f20", None))
#if QT_CONFIG(tooltip)
        self.btnDeleteImage2.setToolTip(QCoreApplication.translate("ImageAIPanel", u"\u5220\u9664\u7b2c 2 \u5f20\u56fe\u7247", None))
#endif // QT_CONFIG(tooltip)
        self.btnDeleteImage2.setText(QCoreApplication.translate("ImageAIPanel", u"\u5220\u9664", None))
        self.lblImageDropZone2.setText(QCoreApplication.translate("ImageAIPanel", u"\u2601\n"
"\u8fd0\u884c\u65f6\u751f\u6210\u56fe\u7247\u6846\n"
"\u652f\u6301\u4e0a\u4f20 / \u62d6\u62fd / Ctrl+V", None))
        self.lblImageNumber3.setText(QCoreApplication.translate("ImageAIPanel", u"\u56fe\u7247 3", None))
#if QT_CONFIG(tooltip)
        self.btnUploadImage3.setToolTip(QCoreApplication.translate("ImageAIPanel", u"\u4e0a\u4f20\u7b2c 3 \u5f20\u56fe\u7247", None))
#endif // QT_CONFIG(tooltip)
        self.btnUploadImage3.setText(QCoreApplication.translate("ImageAIPanel", u"\u4e0a\u4f20", None))
#if QT_CONFIG(tooltip)
        self.btnDeleteImage3.setToolTip(QCoreApplication.translate("ImageAIPanel", u"\u5220\u9664\u7b2c 3 \u5f20\u56fe\u7247", None))
#endif // QT_CONFIG(tooltip)
        self.btnDeleteImage3.setText(QCoreApplication.translate("ImageAIPanel", u"\u5220\u9664", None))
        self.lblImageDropZone3.setText(QCoreApplication.translate("ImageAIPanel", u"\u2601\n"
"\u8fd0\u884c\u65f6\u751f\u6210\u56fe\u7247\u6846\n"
"\u652f\u6301\u4e0a\u4f20 / \u62d6\u62fd / Ctrl+V", None))
        self.lblImageNumber4.setText(QCoreApplication.translate("ImageAIPanel", u"\u56fe\u7247 4", None))
#if QT_CONFIG(tooltip)
        self.btnUploadImage4.setToolTip(QCoreApplication.translate("ImageAIPanel", u"\u4e0a\u4f20\u7b2c 4 \u5f20\u56fe\u7247", None))
#endif // QT_CONFIG(tooltip)
        self.btnUploadImage4.setText(QCoreApplication.translate("ImageAIPanel", u"\u4e0a\u4f20", None))
#if QT_CONFIG(tooltip)
        self.btnDeleteImage4.setToolTip(QCoreApplication.translate("ImageAIPanel", u"\u5220\u9664\u7b2c 4 \u5f20\u56fe\u7247", None))
#endif // QT_CONFIG(tooltip)
        self.btnDeleteImage4.setText(QCoreApplication.translate("ImageAIPanel", u"\u5220\u9664", None))
        self.lblImageDropZone4.setText(QCoreApplication.translate("ImageAIPanel", u"\u2601\n"
"\u8fd0\u884c\u65f6\u751f\u6210\u56fe\u7247\u6846\n"
"\u652f\u6301\u4e0a\u4f20 / \u62d6\u62fd / Ctrl+V", None))
        self.lblImageNumber5.setText(QCoreApplication.translate("ImageAIPanel", u"\u56fe\u7247 5", None))
#if QT_CONFIG(tooltip)
        self.btnUploadImage5.setToolTip(QCoreApplication.translate("ImageAIPanel", u"\u4e0a\u4f20\u7b2c 5 \u5f20\u56fe\u7247", None))
#endif // QT_CONFIG(tooltip)
        self.btnUploadImage5.setText(QCoreApplication.translate("ImageAIPanel", u"\u4e0a\u4f20", None))
#if QT_CONFIG(tooltip)
        self.btnDeleteImage5.setToolTip(QCoreApplication.translate("ImageAIPanel", u"\u5220\u9664\u7b2c 5 \u5f20\u56fe\u7247", None))
#endif // QT_CONFIG(tooltip)
        self.btnDeleteImage5.setText(QCoreApplication.translate("ImageAIPanel", u"\u5220\u9664", None))
        self.lblImageDropZone5.setText(QCoreApplication.translate("ImageAIPanel", u"\u2601\n"
"\u8fd0\u884c\u65f6\u751f\u6210\u56fe\u7247\u6846\n"
"\u652f\u6301\u4e0a\u4f20 / \u62d6\u62fd / Ctrl+V", None))
        self.lblAiSummaryTitle.setText(QCoreApplication.translate("ImageAIPanel", u"\u5546\u54c1\u7b80\u6d01\u6458\u8981", None))
        self.txtAiSummary.setText("")
        self.txtAiSummary.setPlaceholderText(QCoreApplication.translate("ImageAIPanel", u"\u5546\u54c1\u4e3b\u4f53\uff1b\u4e3b\u8981\u7ed3\u6784\uff1b\u53ef\u6298\u53e0/\u538b\u7f29\u7279\u5f81", None))
        self.lblPackingStateTitle.setText(QCoreApplication.translate("ImageAIPanel", u"\u9884\u8ba1\u5305\u88c5\u65b9\u5f0f", None))
        self.txtPackingState.setText("")
        self.txtPackingState.setPlaceholderText(QCoreApplication.translate("ImageAIPanel", u"\u5305\u88c5\u5904\u7406\u65b9\u5f0f\uff1b\u6700\u7ec8\u5355\u4ef6\u5305\u88c5\u7c7b\u578b", None))
        self.btnPartialReestimate.setText(QCoreApplication.translate("ImageAIPanel", u"\u5c40\u90e8\u91cd\u4f30", None))
        pass
    # retranslateUi

