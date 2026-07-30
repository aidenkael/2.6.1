# 本地四源合并审计（2026-07-29）

本任务以 `Development rules-2.6.1.md` 为最高需求。

## 输入资料

1. `Profit-Accounting-2.6.zip`
2. `logistics-cost-skill-2.0(1).zip`
3. `Profit-Accounting-UI-Handoff.zip`
4. `Desktop.zip`

输入文件 SHA256 记录在 `docs/LOCAL_INPUT_SHA256.txt`。

## 主工程结论

- 本地主工程 Git HEAD：`325aeed00e9a64caf29e8bfd8dc1b90983bac212`。
- 已包含 R2 迁移、固定 `ddad3b...` 物流适配边界、确定性利润/物流引擎、SQLite 基础与 PySide6 空壳。
- 本轮从该 Commit 建立功能分支继续开发，不使用压缩包中因跨平台换行导致的“全文件修改”状态；实际开发基线由本地 Git 对象重新检出。

## UI 资料结论

- UI 交接包包含两张 1920×1080 PNG、对应 SVG、结构文档、组件文档与机器可读 manifest。
- 资料包**不包含可直接运行的 PySide6、React 或其他界面代码**；所谓“Figma 转化”主要是 SVG 与结构化交接资料。
- `Desktop.zip` 中 PNG 与交接包 PNG 哈希一致；TXT 实际内容为原始 SVG。
- 上传的最终 PNG 与仓库旧 UI 基准图哈希不同，因此本轮以用户最新上传的 PNG 替换旧基准，并保留 normalized SVG 供坐标、颜色和结构复核。
- PySide6 使用原生控件重建，未将 SVG 直接当作交互界面。

## 物流 2.0 资料结论

上传的物流压缩包包含：

- `calibration_all_cleaned_v3.json`：77 条校准记录；
- `calibration_final_diagnostic_v3.md`；
- `CALIBRATION_ROUND_02_STATUS.md`；
- 当前费率配置；
- 旧 `simple-v2.1` 运行代码和大量开发档案、缓存、WorkBuddy记忆与示例。

审计发现：

- Round 02 状态文档明确写明“本次未修改算法，仅封存校准数据”；
- 本地压缩包未包含已复审 `ddad3b...` 安全补丁中应存在的 `packaging_calibration.py`、`test_final_calibration.py` 和对应安全补丁报告；
- 其 `ai_schema.py` 仍包含 50g、60g、15×10×4cm 等旧回放兼容默认值，且部分结构布尔值默认 `false`，不能直接作为 2.6.1 正式生产事实；
- 因此，本轮**没有用该本地压缩包覆盖已固定的 `ddad3b...` 适配边界和确定性费用引擎**。

本轮采用的安全接入方式：

1. 导入 v3 的 77 条校准数据、诊断文档和费率配置；
2. 新增 `PackagingEstimationService`，将校准样本作为版本化候选建议源；
3. 结构字段未知时不解释为 `false`，按保护性候选处理；
4. 单样本或通用比例均标记 `needs_review`；
5. 外部 AI 与本地候选冲突时保存原始、拟调整和最终采用三组数据，不静默覆盖；
6. 所有金额仍只由 `engines/logistics/` 与 `engines/profit/` 计算；
7. 校准包仅接受经过结构验证的 JSON 或 ZIP；启用和回滚会立即刷新包装估算服务，不修改费用公式。

## 排除项

未进入正式运行目录：

- `.pytest_cache`、`__pycache__`；
- `.workbuddy` 记忆；
- 79条原始开发档案；
- 全量示例 JSON；
- 清洗脚本与回放脚本；
- 本地用户图片目录；
- 旧压缩包。

## 当前限制

- 当前执行环境无 Python 3.11 和 PySide6，无法在此处完成真实 Qt 窗口烟测；纯逻辑测试和 Python 语法编译可执行。
- 当前执行环境不是 Windows，不能生成可信的 Windows EXE/文件夹版；仓库已提供 Windows 构建脚本和 PyInstaller spec，需在 Windows 3.11 环境执行。
- 真实视觉 AI API 与 Edge + 1688 插件仍需在用户本机做最终验收。
