from __future__ import annotations

from PySide6.QtWidgets import QFileDialog, QLabel, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from profit_accounting_26.application import AppContext
from profit_accounting_26.ui.widgets import Card, SectionHeader


class CalibrationPage(QWidget):
    def __init__(self, context: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context = context
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 18)
        layout.setSpacing(12)

        card = Card()
        card_layout = QVBoxLayout(card)
        header = SectionHeader("模型校准反馈", "软件只管理校准数据和版本，不自动训练或修改Python代码")
        import_button = QPushButton("导入校准包")
        rollback = QPushButton("回滚上一版本")
        refresh = QPushButton("刷新")
        import_button.setProperty("primary", True)
        header.right_layout.addWidget(import_button)
        header.right_layout.addWidget(rollback)
        header.right_layout.addWidget(refresh)
        card_layout.addWidget(header)
        self.status = QLabel("校准版本加载中")
        self.status.setProperty("muted", True)
        card_layout.addWidget(self.status)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["版本", "状态", "导入时间", "文件"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        card_layout.addWidget(self.table)
        layout.addWidget(card)

        feedback_card = Card()
        feedback_layout = QVBoxLayout(feedback_card)
        feedback_layout.addWidget(SectionHeader("实际反馈误差", "仅展示已录入实际数据的记录"))
        self.feedback_table = QTableWidget(0, 6)
        self.feedback_table.setHorizontalHeaderLabels(["商品", "估算物流", "实际物流", "误差金额", "误差比例", "方向"])
        self.feedback_table.horizontalHeader().setStretchLastSection(True)
        self.feedback_table.verticalHeader().setVisible(False)
        feedback_layout.addWidget(self.feedback_table)
        layout.addWidget(feedback_card)
        layout.addStretch(1)

        import_button.clicked.connect(self.import_package)
        rollback.clicked.connect(self.rollback)
        refresh.clicked.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        packages = self.context.calibration_manager.list_packages()
        active = self.context.calibration_manager.active_package()
        if active:
            count = active.get("metadata", {}).get("sample_count", "未知")
            self.status.setText(f"当前启用：{active['version']} · {count} 条样本")
        else:
            self.status.setText("当前没有启用的校准数据")
        self.table.setRowCount(0)
        for package in packages:
            row = self.table.rowCount()
            self.table.insertRow(row)
            values = [
                package["version"],
                "当前启用" if package["active"] else "历史版本",
                package["imported_at"],
                package["path"],
            ]
            for col, value in enumerate(values):
                self.table.setItem(row, col, QTableWidgetItem(str(value)))
        self.feedback_table.setRowCount(0)
        for record in self.context.store.export_records():
            layers = record.get("layers", {})
            actual = layers.get("actual", {})
            calculated = layers.get("calculated", {})
            if not actual:
                continue
            row = self.feedback_table.rowCount()
            self.feedback_table.insertRow(row)
            estimated = float(calculated.get("total_logistics_rmb", 0) or 0)
            real = float(actual.get("total_logistics_rmb", 0) or 0)
            error = float(actual.get("error_amount_rmb", real - estimated) or 0)
            percent = float(actual.get("error_percent", (error / estimated if estimated else 0)) or 0)
            values = [
                record.get("product_name") or "未命名商品",
                f"¥{estimated:.2f}",
                f"¥{real:.2f}",
                f"¥{error:.2f}",
                f"{percent * 100:.2f}%",
                actual.get("error_direction") or "unknown",
            ]
            for col, value in enumerate(values):
                self.feedback_table.setItem(row, col, QTableWidgetItem(str(value)))

    def import_package(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(self, "导入校准包", "", "校准包 (*.json *.zip);;全部文件 (*)")
        if not selected:
            return
        try:
            result = self.context.calibration_manager.import_package(selected)
        except Exception as exc:
            QMessageBox.warning(self, "导入失败", str(exc))
            return
        QMessageBox.information(self, "导入成功", f"已导入并启用：{result['version']}")
        self.refresh()

    def rollback(self) -> None:
        result = self.context.calibration_manager.rollback()
        if result is None:
            QMessageBox.information(self, "无法回滚", "当前没有可回滚的上一版本。")
            return
        QMessageBox.information(self, "已回滚", f"当前版本：{result['version']}")
        self.refresh()
