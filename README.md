# Profit-Accounting-2.6

本任务以 `Development rules-2.6.1.md` 为最高需求。

微智能利润管理软件 2.6：面向 SHEIN 美国站单个商品、单个 SKC 的 Windows 本地桌面工具。

## 当前版本

```text
2.6.0-rc1
```

当前属于 **Windows 发布候选源码版**。核心业务、数据和 PySide6 页面已经实现；真实视觉 API、Edge 插件通信和 Windows 成品打包仍需在用户本机完成最终验收。

## 当前最高准则与固定来源

- 最高准则：`Development rules-2.6.1.md`
- R2 冻结标签：`profit-legacy-freeze-20260728-r2`
- R2 来源 Commit：`d0c07d374c9ee61926de9cd3e01b8c35260c8e5c`
- 物流核算 2.0 固定接入 Commit：`ddad3b7486c2afc7de0b266defb3f5dd22028d00`
- 本地候选校准数据：`local-calibration-v3-77-samples`

## 已实现

- 最新 Figma PNG/SVG 对应的 PySide6 主界面和设置页；
- 左侧 6 项导航、顶部保存状态和本地数据目录；
- 3～6 图片框，支持点击上传、拖拽、Ctrl+V、预览、删除和类型修改；
- `AIObservation` 与 `PackagingProposal` 分层；
- 正常档、保守档、人工采用值和复核状态；
- 77 条本地校准数据驱动的包装候选服务；
- 动态货代、体积重、计费重、头程、固定费和尾程确定性计算；
- 利润正算、按当前条件规则执行的目标利润/利润率反推和活动预留；
- 可配置的 29 USD 以下 2.99 USD 补贴规则；
- SQLite 商品记录、不可变初始快照和重算/反馈快照；
- 图片保存后复制到数据目录，源文件不移动、不删除；
- 历史记录、实际反馈、误差展示；
- 数据导入导出、校准反馈导出、校准包结构校验、即时启用和回滚；
- 以图搜图本机入口、候选链接复制和发送到测算页；
- 数据目录持久切换（重启生效）与图片估算过期提示；
- Windows 验证、运行、PyInstaller构建和文件夹版打包脚本。

## 本地运行

在项目根目录双击：

```text
run_app.bat
```

首次运行会创建 `.venv-311` 并安装运行依赖。

也可手动执行：

```powershell
cd "E:\Profit-Accounting-2.6"
py -3.11 -m venv .venv-311
.\.venv-311\Scripts\python -m pip install -U pip
.\.venv-311\Scripts\python -m pip install -e ".[dev]"
.\.venv-311\Scripts\python -m profit_accounting_26.ui.app
```

## 完整验证

```powershell
.\verify_release_candidate.bat
```

必须达到：

- `0 failed`
- `0 collection errors`
- 敏感信息扫描通过
- PySide6 环境存在时 UI 离屏烟测通过

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

数据库、保存后的商品图片、导出文件和校准包均位于该目录，不提交 GitHub。

## 重要限制

- 当前真实视觉 AI API 未配置时，点击“AI识图”使用明确的人工回退，不伪造识别结果；
- Edge + 1688 插件自动通信依赖用户本机插件环境，当前候选链接可人工粘贴与复制；
- 上传的本地物流压缩包缺少已复审 `ddad3b...` 安全补丁文件，因此只导入校准数据，不覆盖固定物流适配边界；
- Windows GUI、DPI、真实 API、Edge 插件和 PyInstaller成品必须在用户电脑最终验收。

详细资料：

- `docs/LOCAL_INTEGRATION_AUDIT.md`
- `docs/UI_IMPLEMENTATION_REPORT.md`
- `PROGRESS_STATUS.md`
- `BLOCKERS.md`
- `NEXT_STEP.md`
