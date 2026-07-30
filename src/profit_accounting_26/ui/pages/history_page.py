from __future__ import annotations

import json

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from profit_accounting_26.application import AppContext
from profit_accounting_26.ui.widgets import Card, SectionHeader


class HistoryPage(QWidget):
    recordRequested = Signal(str)

    def __init__(self, context: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context = context
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 18)
        layout.setSpacing(12)

        card = Card()
        card_layout = QVBoxLayout(card)
        header = SectionHeader("历史记录管理", "搜索、查看保存时快照并录入实际反馈")
        self.search = QLineEdit()
        self.search.setPlaceholderText("按商品名称、记录ID或状态搜索")
        refresh = QPushButton("刷新")
        open_button = QPushButton("打开到测算页")
        feedback_button = QPushButton("录入实际反馈")
        open_button.setProperty("primary", True)
        refresh.clicked.connect(self.refresh)
        open_button.clicked.connect(self.open_selected)
        feedback_button.clicked.connect(self.edit_actual_feedback)
        header.right_layout.addWidget(self.search)
        header.right_layout.addWidget(refresh)
        header.right_layout.addWidget(feedback_button)
        header.right_layout.addWidget(open_button)
        card_layout.addWidget(header)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["商品", "状态", "包装档", "货代", "利润", "更新时间"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.itemSelectionChanged.connect(self.show_details)
        self.table.cellDoubleClicked.connect(lambda _row, _col: self.open_selected())
        card_layout.addWidget(self.table)
        layout.addWidget(card, 3)

        details_card = Card()
        details_layout = QVBoxLayout(details_card)
        details_layout.addWidget(QLabel("记录详情与快照"))
        self.details = QTextEdit()
        self.details.setReadOnly(True)
        details_layout.addWidget(self.details)
        layout.addWidget(details_card, 2)
        self.refresh()

    def refresh(self) -> None:
        self.records = self.context.record_service.list(search=self.search.text())
        self.table.setRowCount(0)
        for record in self.records:
            row = self.table.rowCount()
            self.table.insertRow(row)
            adopted = record.get("layers", {}).get("adopted", {})
            calculated = record.get("layers", {}).get("calculated", {})
            values = [
                record.get("product_name") or "未命名商品",
                record.get("status") or "active",
                adopted.get("selected_packaging") or "—",
                adopted.get("selected_forwarder_id") or "—",
                f"¥{float(calculated.get('profit_rmb', 0)):.2f}",
                record.get("_updated_at") or record.get("updated_at") or "",
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if col == 0:
                    item.setData(256, record.get("id"))
                self.table.setItem(row, col, item)
        if self.records:
            self.table.selectRow(0)

    def selected_record_id(self) -> str | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        return str(item.data(256)) if item and item.data(256) else None

    def show_details(self) -> None:
        record_id = self.selected_record_id()
        if not record_id:
            self.details.clear()
            return
        record = self.context.record_service.load(record_id)
        snapshots = self.context.record_service.snapshots(record_id)
        payload = {
            "record": record,
            "snapshots": [
                {"id": item["id"], "kind": item["kind"], "created_at": item["created_at"]}
                for item in snapshots
            ],
        }
        self.details.setPlainText(json.dumps(payload, ensure_ascii=False, indent=2))

    def open_selected(self) -> None:
        record_id = self.selected_record_id()
        if not record_id:
            QMessageBox.information(self, "未选择", "请先选择一条记录。")
            return
        self.recordRequested.emit(record_id)
    def edit_actual_feedback(self) -> None:
        record_id = self.selected_record_id()
        if not record_id:
            QMessageBox.information(self, "未选择", "请先选择一条记录。")
            return
        record = self.context.record_service.load(record_id)
        actual = record.get("layers", {}).get("actual", {})
        dialog = QDialog(self)
        dialog.setWindowTitle("录入实际包装与物流反馈")
        form = QFormLayout(dialog)
        fields = {}
        for key, label, suffix, maximum in (
            ("length_cm", "实际包装长", " cm", 500),
            ("width_cm", "实际包装宽", " cm", 500),
            ("height_cm", "实际包装高", " cm", 500),
            ("weight_g", "实际包装重量", " g", 100000),
            ("head_freight_rmb", "实际头程费用", " RMB", 1000000),
            ("total_logistics_rmb", "实际物流总费用", " RMB", 1000000),
        ):
            spin = QDoubleSpinBox()
            spin.setRange(0, maximum)
            spin.setDecimals(2)
            spin.setSuffix(suffix)
            spin.setValue(float(actual.get(key, 0) or 0))
            fields[key] = spin
            form.addRow(label, spin)
        status = QLineEdit(str(record.get("status") or "active"))
        form.addRow("商品状态", status)
        buttons = QHBoxLayout()
        save = QPushButton("保存反馈")
        save.setProperty("primary", True)
        cancel = QPushButton("取消")
        buttons.addWidget(save)
        buttons.addWidget(cancel)
        form.addRow(buttons)
        cancel.clicked.connect(dialog.reject)

        def commit() -> None:
            payload = self.context.record_service.load(record_id)
            layers = payload.setdefault("layers", {})
            calculated = layers.setdefault("calculated", {})
            actual_layer = layers.setdefault("actual", {})
            for key, spin in fields.items():
                actual_layer[key] = spin.value() or None
            estimated = float(calculated.get("total_logistics_rmb", 0) or 0)
            real_total = float(actual_layer.get("total_logistics_rmb", 0) or 0)
            if estimated and real_total:
                actual_layer["error_amount_rmb"] = real_total - estimated
                actual_layer["error_percent"] = (real_total - estimated) / estimated
                actual_layer["error_direction"] = (
                    "underestimate" if real_total > estimated else "overestimate" if real_total < estimated else "match"
                )
            payload["status"] = status.text().strip() or "active"
            self.context.store.update_record(record_id, payload, snapshot_kind="actual_feedback")
            dialog.accept()

        save.clicked.connect(commit)
        if dialog.exec():
            self.refresh()
