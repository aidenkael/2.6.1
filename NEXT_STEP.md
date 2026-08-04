# 下一步：冻结 UI 接入与利润双场景（进行中）

## 当前进度（2026-08-04）

分支：`ui/integrate-2.6.1-contract`（基于 `main` @ `9436b970`）

### 已完成

| 阶段 | 内容 | 状态 |
|---|---|---|
| 1 | forms/ 目录 + 两份 .ui 文件（SHA 验证一致） | ✅ |
| 2 | 利润引擎双场景（`calculate_profit_scenario` / `calculate_dual_profit` / 反推函数） | ✅ |
| 3 | 记录 schema 双场景编解码器（`profit_scenario_codec.py`，向后兼容） | ✅ |
| 4 | `ui_loader.py` + `main_window_binder.py` + `calculation_binder.py`（已测试）+ `settings_binder.py`（骨架） | ✅ |
| 5a | `main_window.py` 重写为 .ui 加载 + Binder 绑定 | ✅ |
| 6 | 36 个新测试（12 利润联动 + 24 UI 合同），全量 155 通过，敏感扫描 0 findings | ✅ |

### 未完成（需下一会话继续）

| 阶段 | 内容 | 说明 |
|---|---|---|
| 5b | 重写 `calculation_page.py`（1707行）使用 .ui 的 `pageCalculation` widget | 现有 CalculationPage 仍为程序化构建；CalculationBinder 已就绪并测试通过，但尚未接入 |
| 5c | 重写 `settings_page.py`（721行）使用 `settings_page.ui` | 现有 SettingsPage 仍为程序化构建；SettingsBinder 骨架已就绪 |
| 7 | Windows 1920×1080 截图验收 | 需实际运行 GUI |
| 8 | Git push + PR | 当前仅本地 commit，未推送 |

## 关键架构决策

1. **.ui 加载方式**：使用 `QUiLoader` 运行时加载，不生成 Python 布局副本
2. **MainWindow**：加载 .ui 后将 centralWidget 移植到 QMainWindow 子类，通过 `MainWindowBinder` 绑定
3. **利润双场景**：每个场景用 `reserve_rate=0` 调用 `calculate_profit`，差异在传入的 `sale_price_usd`（无活动用原价，活动用折后价）
4. **driver 状态机**：`_profit_driver` 记录当前主输入字段，`_profit_updating` + `QSignalBlocker` 防递归
5. **objectName 命名差异**（以 .ui 为准）：`btnAiRecognize`（非 `btnAiRecognition`）、`btnPartialReestimate`（非 `btnPartialEstimate`）、`txtAiSummary`（非 `txtProductSummary`）

## 下一会话执行步骤

1. **重写 CalculationPage**：
   - 从 `CalculationPage(QWidget)` 改为接收 .ui 的 `pageCalculation` widget
   - 用 `findChild` 获取所有图片/AI/包装/货代/利润控件
   - 利润区逻辑委托给 `CalculationBinder`
   - 保留所有图片上传/AI识图/包装估算/货代报价/记录保存逻辑
   - 测试：运行全量测试 + 手动 GUI 验收

2. **重写 SettingsPage**：
   - 加载 `settings_page.ui` 并用 `SettingsBinder` 绑定
   - 保留 API Profile / 货代 / 利润规则编辑逻辑

3. **Windows 截图验收**：
   - 1920×1080 主计算页
   - 窗口缩小后滚动状态
   - 设置页
   - 无活动与活动分别命中/不命中规则的利润区

4. **Git push + PR**：
   ```bash
   git add -A
   git commit -m "refactor: bind frozen ui and add dual profit scenarios"
   git push -u origin ui/integrate-2.6.1-contract
   ```
   创建 PR（head: `ui/integrate-2.6.1-contract`, base: `main`），不自动合并。

## 边界确认

```
未修改视觉AI请求
未增加AI调用
未修改AI/CAL协调
未修改77条CAL
未修改包装估算
未修改物流公式与费率
```
