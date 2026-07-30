from __future__ import annotations

from PySide6.QtWidgets import QFileDialog, QLabel, QMessageBox, QPushButton, QTextEdit, QVBoxLayout, QWidget

from profit_accounting_26.application import AppContext
from profit_accounting_26.ui.widgets import Card, SectionHeader


class ImportExportPage(QWidget):
    def __init__(self, context: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context = context
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 18)
        layout.setSpacing(12)

        card = Card()
        card_layout = QVBoxLayout(card)
        header = SectionHeader("数据导入导出", "使用唯一记录ID判断新增、更新和冲突")
        export_button = QPushButton("导出全部商品记录")
        import_button = QPushButton("导入兼容JSON")
        export_calibration = QPushButton("导出物流校准反馈")
        export_button.setProperty("primary", True)
        header.right_layout.addWidget(export_button)
        header.right_layout.addWidget(import_button)
        header.right_layout.addWidget(export_calibration)
        card_layout.addWidget(header)
        info = QLabel("导入遇到相同记录ID时不会静默覆盖；软件不执行ERP自动同步。")
        info.setWordWrap(True)
        info.setProperty("muted", True)
        card_layout.addWidget(info)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        card_layout.addWidget(self.log)
        layout.addWidget(card)
        layout.addStretch(1)

        export_button.clicked.connect(self.export_records)
        import_button.clicked.connect(self.import_records)
        export_calibration.clicked.connect(self.export_feedback)

    def export_records(self) -> None:
        selected, _ = QFileDialog.getSaveFileName(self, "导出商品记录", "profit-accounting-records.json", "JSON (*.json)")
        if not selected:
            return
        path = self.context.import_export_service.export_records(selected)
        self.log.append(f"已导出：{path}")

    def import_records(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(self, "导入商品记录", "", "JSON (*.json)")
        if not selected:
            return
        try:
            result = self.context.import_export_service.import_records(selected, overwrite=False)
        except Exception as exc:
            QMessageBox.warning(self, "导入失败", str(exc))
            return
        self.log.append(
            f"导入完成：新增 {result['created']}，冲突 {result['conflicts']}。冲突记录未覆盖。"
        )
        if result["conflicts"]:
            self.log.append("冲突ID：" + ", ".join(result["conflict_ids"]))

    def export_feedback(self) -> None:
        selected, _ = QFileDialog.getSaveFileName(self, "导出校准反馈", "logistics-calibration-feedback.json", "JSON (*.json)")
        if not selected:
            return
        path = self.context.import_export_service.export_calibration_feedback(selected)
        self.log.append(f"已导出校准反馈：{path}")
