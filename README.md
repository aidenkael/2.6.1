# Profit-Accounting-2.6.1

本项目以 `Development rules-2.6.1.md` 为最高需求。

微智能利润管理软件 2.6.1：面向 SHEIN 美国站单个商品、单个 SKC 的 Windows 本地桌面利润与物流核算工具。

## 当前版本

```text
2.6.1
```

2.6.1 已完成 Windows 实机发布前验收。正式发布 tag 应指向本次版本元数据收口完成后的最终 `main` commit。

## 当前主功能

软件主导航固定为：

1. 新商品测算
2. 历史记录管理
3. 设置

主要能力包括：

- PySide6 本地桌面 UI，1920×1080 下完整展示，缩小窗口后通过滚动区域保持布局可用；
- 商品图片、名称、材质、类型、重量和尺寸输入；
- 正常档 / 保守档包装估算与确定性物流核算；
- SHEIN 核价、标价、标价利率、活动预留、活动后售价、利润和利润率计算；
- SQLite 本地历史记录、修改保存和重启持久化；
- 校准反馈 Excel + `Calibration Feedback Export V2` manifest 导出；
- 校准闭环：Feedback V2 → Candidate → Validator → Offline Replay → Promotion → Formal Runtime Bundle → 用户手动启用；
- Formal Bundle 导入默认 inactive，启用、重启、删除和 builtin fallback 均带完整性校验；
- CAL77 原始 77 条历史样本完整保留，但 sample runtime 已全部停用；builtin registry 仅保留低置信 `AGR-THIN-TEXTILE-001` 作为 legacy fallback；
- 数据目录隔离、校准包管理、敏感信息扫描和 Windows 文件夹版构建脚本。

## 物流边界

物流核算继续由确定性引擎执行。当前两家货代：

- 深圳：80 元/kg + 10 元固定服务费；
- 义乌：100 元/kg + 6 元固定服务费；
- 计费重取实际重量与体积重较高值；
- 体积重 = 长 × 宽 × 高（cm）/ 8000。

具体当前参数仍以项目配置文件和软件设置为准。

## 本地运行

在项目根目录双击：

```text
run_app.bat
```

首次运行会创建 `.venv-311` 并安装运行依赖。

也可手动执行：

```powershell
cd "E:\Profit-Accounting-2.6.1"
py -3.11 -m venv .venv-311
.\.venv-311\Scripts\python -m pip install -U pip
.\.venv-311\Scripts\python -m pip install -e ".[dev]"
.\.venv-311\Scripts\python -m profit_accounting_26.ui.app
```

## 完整验证

```powershell
.\verify_release_candidate.bat
```

发布前必须至少满足：

- `0 failed`
- `0 collection errors`
- 敏感信息扫描通过
- Windows 实机启动和 UI 验收通过

2.6.1 最终发布前验收基线：`909 passed`、敏感扫描 `0 findings`、Windows 实机启动与 1920×1080 / 缩小窗口验收通过。

## Windows 文件夹版打包

```powershell
.\build_windows.bat
```

输出位置：

```text
release\
```

优先交付解压即用文件夹版和对应 ZIP，不以单文件 EXE 作为唯一交付方式。

## 本地数据

默认数据目录：

```text
%USERPROFILE%\ProfitAccounting26Data
```

可通过环境变量覆盖：

```powershell
$env:PROFIT_ACCOUNTING_DATA_DIR = "E:\Profit-Accounting-Data"
```

数据库、商品图片、导出文件和校准包均位于数据目录，不提交 GitHub。

## 版本冻结说明

2.6.1 的发布验收与校准闭环均已完成。发布后新增真实校准数据不再手工扩展 CAL77，而统一走 Formal calibration closed loop。

详细发布说明见：

- `RELEASE_NOTES_2.6.1.md`
- `calibration/logistics_v2/CAL77_CONSERVATIVE_MIGRATION.md`
- `Development rules-2.6.1.md`
