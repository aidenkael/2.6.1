from __future__ import annotations

PRIMARY = "#1769F6"
BACKGROUND = "#F5F8FC"
SIDEBAR = "#F8FAFD"
BORDER = "#DCE5F0"
MUTED = "#6E7B90"
TEXT = "#172033"
DANGER = "#D94A4A"
SUCCESS = "#219B68"
WARNING = "#C77600"

APP_STYLE = f"""
* {{
    font-family: "Microsoft YaHei UI", "Noto Sans CJK SC", sans-serif;
    font-size: 13px;
    color: {TEXT};
}}
QMainWindow, QWidget#appRoot {{ background: {BACKGROUND}; }}
QWidget#sidebar {{ background: {SIDEBAR}; border-right: 1px solid #EAF0F6; }}
QWidget#topBar {{ background: #FFFFFF; border-bottom: 1px solid #EAF0F6; }}
QFrame[card="true"] {{
    background: #FFFFFF;
    border: 1px solid {BORDER};
    border-radius: 10px;
}}
QFrame[softCard="true"] {{
    background: #F8FAFD;
    border: 1px solid #E4EAF2;
    border-radius: 8px;
}}
QFrame[choiceSelected="true"] {{
    background: #FFFFFF;
    border: 1px solid {PRIMARY};
}}
QFrame[choiceFrozen="true"] {{
    background: #F1F4F8;
    border: 1px solid #E0E6EE;
}}
QLabel[heading="true"] {{ font-size: 18px; font-weight: 600; }}
QLabel[subheading="true"] {{ color: {MUTED}; font-size: 11px; }}
QLabel[sectionTitle="true"] {{ font-size: 15px; font-weight: 600; }}
QLabel[muted="true"] {{ color: {MUTED}; }}
QLabel[primary="true"] {{ color: {PRIMARY}; font-weight: 600; }}
QLabel[success="true"] {{ color: {SUCCESS}; font-weight: 600; }}
QLabel[danger="true"] {{ color: {DANGER}; font-weight: 600; }}
QLabel[warning="true"] {{ color: {WARNING}; font-weight: 600; }}
QLineEdit, QDoubleSpinBox, QSpinBox, QComboBox, QTextEdit {{
    background: #FFFFFF;
    border: 1px solid {BORDER};
    border-radius: 7px;
    padding: 5px 8px;
    min-height: 22px;
    selection-background-color: {PRIMARY};
}}
QLineEdit:focus, QDoubleSpinBox:focus, QSpinBox:focus, QComboBox:focus, QTextEdit:focus {{
    border: 1px solid {PRIMARY};
}}
QLineEdit[readOnly="true"], QDoubleSpinBox[readOnly="true"] {{
    background: #F1F4F8;
    color: #5D6A7D;
}}
QLineEdit:disabled, QDoubleSpinBox:disabled, QComboBox:disabled {{
    background: #EEF2F6;
    color: #8590A2;
}}
QPushButton {{
    background: #FFFFFF;
    border: 1px solid {BORDER};
    border-radius: 7px;
    padding: 6px 12px;
    min-height: 26px;
}}
QPushButton:hover {{ border-color: {PRIMARY}; color: {PRIMARY}; }}
QPushButton:pressed {{ background: #EAF2FF; }}
QPushButton:checked {{ border-color: {PRIMARY}; color: {PRIMARY}; font-weight: 600; }}
QPushButton[primary="true"] {{ background: {PRIMARY}; border-color: {PRIMARY}; color: #FFFFFF; font-weight: 600; }}
QPushButton[primary="true"]:hover {{ background: #0E5DE5; color: #FFFFFF; }}
QPushButton[danger="true"] {{ color: {DANGER}; border-color: #F2C9C9; }}
QPushButton[nav="true"] {{
    text-align: left;
    border: none;
    background: transparent;
    padding: 9px 12px;
    border-radius: 9px;
    min-height: 40px;
}}
QPushButton[nav="true"]:checked {{ background: #EAF2FF; color: {PRIMARY}; font-weight: 600; }}
QPushButton[nav="true"]:hover {{ background: #F0F5FD; }}
QTableWidget {{
    background: #FFFFFF;
    alternate-background-color: #FAFCFF;
    border: 1px solid {BORDER};
    border-radius: 8px;
    gridline-color: #EDF1F6;
}}
QTableWidget::item:selected {{
    background: #EAF2FF;
    color: {TEXT};
}}
QHeaderView::section {{
    background: #F7F9FC;
    border: none;
    border-bottom: 1px solid {BORDER};
    padding: 7px;
    font-weight: 600;
}}
QListWidget {{ background: transparent; border: none; outline: none; }}
QListWidget::item {{ padding: 9px; border-radius: 7px; margin: 2px; }}
QListWidget::item:selected {{ background: #EAF2FF; color: {PRIMARY}; }}
QScrollArea {{ border: none; background: transparent; }}
QRadioButton, QCheckBox {{ spacing: 6px; }}
QToolTip {{ background: #172033; color: #FFFFFF; border: none; padding: 5px; }}
"""
