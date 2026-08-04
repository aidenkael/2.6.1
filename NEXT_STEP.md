# 下一步：冻结 UI 接入与利润双场景（进行中）

## 当前进度（2026-08-04 下午）

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
| 5b | `calculation_page.py` 重写为 .ui 绑定版（`pageCalculation` + findChild + CalculationBinder） | ✅ |
| 5c | `settings_page.py` 重写为 .ui 绑定版（运行时加载 settings_page.ui，保留全部货代/规则/API Profile 逻辑） | ✅ |
| 7 | Windows 1920×1080 截图验收（`docs/assets/ui_acceptance_2026-08-04/`） | ✅ |

### 未完成（等待用户确认）

| 阶段 | 内容 | 说明 |
|---|---|---|
| 8 | Git push + PR | 用户要求完成前不推送、不建 PR；仅本地提交 |

### 验收结果（2026-08-04）

- 1920×1080 最大化：主计算页无滚动条（`calculationScrollArea` max=0），区域顺序与冻结 .ui 一致；
- 缩小到 1280×800：UI 尺寸不压缩，垂直/水平滚动条出现（max>0 且 visible）；
- 设置页：API 第 2、3 行预览与测试/删除按钮隐藏，货代表格 8 列与规则编辑器完整；
- 利润区一致性断言：无活动利润=售价RMB−总成本；活动后售价=无活动售价×(1−预留)；
  修改活动预留时保持无活动售价不变；编辑活动后利润保持预留不变并反推两售价；
  两场景规则独立判断（27<29 仅活动场景触发 +¥21.53）；负利润不截断；
- 全量 pytest 155 通过；`tools/sensitive_scan.py` 0 findings。

## 关键架构决策

1. **.ui 加载方式**：使用 `QUiLoader` 运行时加载，不生成 Python 布局副本
2. **MainWindow**：加载 .ui 后将 centralWidget 移植到 QMainWindow 子类，通过 `MainWindowBinder` 绑定
3. **页面挂载**：`.ui` 的 `pageCalculation` 被 CalculationPage 接管（`setParent` 后显式 `setVisible(True)`，
   `setParent` 会清除可见标记——这是早期截图空白的根因，`_replace_placeholder` 对设置页同样处理）
4. **利润双场景**：每个场景用 `reserve_rate=0` 调用 `calculate_profit`，差异在传入的 `sale_price_usd`（无活动用原价，活动用折后价）
5. **driver 状态机**：`_profit_driver` 记录当前主输入字段，`_profit_updating` + `QSignalBlocker` 防递归
6. **动态区域**：图片框（3–6）清掉 Designer 预览卡 `imageCard1-5` 后挂 `imageSlotsLayout`；
   货代报价卡清掉 `forwarderCardShenzhen/Yiwu` 后挂 `forwarderCardsLayout`（保守档之后、系统成本之前）
7. **隐藏结构选项**：软硬度/折叠/压缩/硬结构复选框为内部观察数据，放入隐藏容器保留旧逻辑
8. **objectName 命名差异**（以 .ui 为准）：`btnAiRecognize`、`btnPartialReestimate`、`txtAiSummary`
9. **记录兼容**：`profit_scenarios` 附加字段 + 旧字段保持；旧记录经 `extract_profit_scenarios` 映射为无活动场景

## 待用户确认后执行

```bash
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
