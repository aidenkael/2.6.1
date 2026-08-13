# Profit-Accounting-2.6.1

微智能利润管理软件 2.6.1：面向 SHEIN 美国站单个商品、单个 SKC 的 Windows 本地桌面利润与物流核算工具。

## 当前状态

当前 `main` 处于 2.6.1 收口阶段，正式发布 tag 暂未创建。

## 当前主功能

软件主导航固定为：

1. 新商品测算
2. 历史记录管理
3. 设置

主要能力包括：

- PySide6 本地桌面 UI，1920×1080 下完整展示，缩小窗口后通过滚动区域保持布局可用；
- 商品图片识别、按修正重估、包装候选与确定性物流核算；
- SHEIN 核价、标价、活动后售价、利润和利润率计算；
- SQLite 本地历史记录、修改保存和重启持久化；
- 校准反馈 Excel + `Calibration Feedback Export V2` manifest 导出；
- 校准闭环：Feedback V2 → Candidate → Validator → Offline Replay → Promotion → Formal Runtime Bundle → 用户手动启用；
- Formal Bundle 导入默认 inactive，并带完整性校验、启用、删除和 builtin fallback；
- 数据目录隔离、校准包管理、敏感信息扫描和 Windows 文件夹版构建脚本。

## AI / 包装 / 物流边界

生产链固定为：

`冻结的 V1.2 AI → PackagingEstimationService 物理安全校验 → 确定性物流 → 利润`

当前软件不再内置历史校准样本或数值规则。builtin 仅提供 `runtime-safety-baseline-v1` 空校准基线和空 registry，因此在没有正式校准包时，本地层只执行确定性物理安全检查与通用 fallback，不用历史经验覆盖 AI 数值。

新的校准规则必须通过 Formal calibration closed loop 验证，并基于 `runtime-safety-baseline-v1` 构建 Formal Bundle。只有包内 `validated_rule_ids` 对应的规则在用户手动启用后才可参与运行。

## 物流边界

物流核算继续由确定性引擎执行。当前两家货代：

- 深圳：80 元/kg + 10 元固定服务费；
- 义乌：100 元/kg + 6 元固定服务费；
- 计费重取实际重量与体积重较高值；
- 体积重 = 长 × 宽 × 高（cm）/ 8000。

具体当前参数以项目配置文件和软件设置为准。

## 本地运行

在项目根目录双击：

```text
run_app.bat
```

也可手动执行：

```powershell
cd "E:\Profit-Accounting-2.6.1"
.\.venv-311\Scripts\python -m profit_accounting_26.ui.app
```

升级到当前版本后，软件首次启动会清理数据目录中的旧 bundled builtin 校准副本，并建立新的空安全基线；商品历史、反馈数据和 API 设置不受影响。

## 完整验证

```powershell
.\verify_release_candidate.bat
```

发布前必须至少满足：`0 failed`、`0 collection errors`、敏感信息扫描通过，以及 Windows 实机启动/UI 验收通过。

## 本地数据

默认数据目录：

```text
%USERPROFILE%\ProfitAccounting26Data
```

可通过环境变量 `PROFIT_ACCOUNTING_DATA_DIR` 覆盖。数据库、商品图片、导出文件和用户导入的校准包均位于数据目录，不提交 GitHub。

## 校准基线

详见 `docs/CALIBRATION_BASELINE.md`。当前仓库不再携带旧历史校准数据；以后只接受基于当前空基线重新验证构建的 Formal Bundle。
