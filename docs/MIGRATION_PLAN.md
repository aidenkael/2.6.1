# MIGRATION_PLAN

## 1. 目标

从唯一 R2 冻结标签 `profit-legacy-freeze-20260728-r2` 和 Commit `d0c07d374c9ee61926de9cd3e01b8c35260c8e5c` 建立干净的 `Profit-Accounting-2.6/` 迁移基线。

本计划不开发完整产品，只建立可导入、可测试、可启动、可由 Agent 直接克隆的独立仓库迁移基线。

## 2. 人工参与点

1. 当前：用户确认阶段 0 文档与 UI 功能矩阵；
2. 后续完整功能完成后：用户进行真实 GUI 验收。

阶段 0 确认后，阶段 1 和阶段 2连续自动执行，不因普通可修复问题暂停。

## 3. 分支与来源锁定

建议阶段分支：

```text
migration/r2-baseline
```

执行前记录：

```text
source_repository = aidenkael/EcommerceSkills
source_tag = profit-legacy-freeze-20260728-r2
source_commit = d0c07d374c9ee61926de9cd3e01b8c35260c8e5c
```

禁止从当前工作区未提交内容、浮动 `master`、旧冻结标签或其他分支复制来源文件。

## 4. 新项目目标结构

```text
Profit-Accounting-2.6/
├─ Development rules-2.6.md
├─ README_FIRST.md
├─ pyproject.toml
├─ requirements.txt
├─ src/
│  └─ profit_accounting_26/
│     ├─ ui/
│     ├─ application/
│     ├─ domain/
│     ├─ engines/
│     │  ├─ profit/
│     │  └─ logistics/
│     ├─ adapters/
│     │  ├─ vision/
│     │  └─ image_search/
│     ├─ storage/
│     ├─ calibration/
│     ├─ config/
│     └─ shared/
├─ tests/
├─ config/
├─ calibration/
├─ docs/
│  ├─ assets/ui_baseline/
│  ├─ UI_BASELINE.md
│  ├─ UI_FUNCTION_MATRIX.md
│  ├─ UI_DEVIATION_REGISTER.md
│  ├─ OUT_OF_SCOPE.md
│  ├─ DECISION_LOG.md
│  └─ MIGRATION_PLAN.md
├─ tools/
├─ verify_baseline.bat
├─ MIGRATION_MANIFEST.md
├─ SOURCE_PROVENANCE.md
├─ TEST_REPORT.md
└─ SHA256SUMS.txt
```

阶段 1 只建立必要文件，不为未实现功能创建大量空接口。

## 5. 迁移分类与目标

### 5.1 利润核心

| R2 来源 | 分类 | 2.6 目标 | 处理 |
|---|---|---|---|
| `Profit accounting-Auto/calculation/profit.py` | ADAPT | `src/.../engines/profit/` | 保留纯函数行为，适配包路径和领域模型 |
| `calculation/profit_adjustments.py` | ADAPT | `engines/profit/` | 保留可配置规则引擎，不硬编码补贴 |
| `calculation/rules.py` | ADAPT | `domain/` 或 `engines/profit/` | 保留规则生命周期和快照语义 |
| `tests/test_profit.py` | ADAPT | `tests/profit/` | 更新 import，保持正算/反推边界 |
| `tests/test_profit_adjustments.py` | ADAPT | `tests/profit/` | 保持规则启停、归档和计算测试 |

### 5.2 货代与配置

| R2 来源 | 分类 | 2.6 目标 | 处理 |
|---|---|---|---|
| `calculation/logistics.py` | ADAPT | `engines/logistics/` 的费用适配层 | 不与物流上游核心重复 |
| `config/config_manager.py` | ADAPT | `config/` + `storage/` | 只迁移稳定读写逻辑 |
| `config/forwarder_manager.py` | ADAPT | `application/SettingsService` 相关 | 稳定 ID、启停、归档/恢复 |
| `config/profit_adjustment_manager.py` | ADAPT | `application/SettingsService` 相关 | 保留版本化和持久化语义 |
| `tests/test_logistics.py` | ADAPT | `tests/logistics/` | 验证费用拆分与全局尾程配置 |
| `tests/test_unlimited_forwarders.py` | ADAPT | `tests/settings/` | 验证动态货代，不假设只有深圳/义乌 |

### 5.3 图片录入与结果模型

| R2 来源 | 分类 | 2.6 目标 | 处理 |
|---|---|---|---|
| `image_intake/image_types.py` | ADAPT | `domain/` | 只保留三类图片类型 |
| `image_intake/result_models.py` | ADAPT | `domain/` | 拆分 AI 原始值与人工采用值 |
| `image_intake/intake_service.py` | ADAPT | `application/RecognitionService` 或图片会话服务 | 保留上传、拖拽、粘贴和会话能力 |
| `image_intake/intake_controller.py` | REFERENCE_ONLY | 不直接迁移 | 参考流程，不保留 Tkinter 控制器 |
| `image_intake/extractors/*` | ADAPT/REFERENCE_ONLY | 测试或离线辅助 | 不主导正式视觉识别 UI |
| `ocr/base_engine.py` | REFERENCE_ONLY | 不作为正式主识别 | 仅保留接口经验 |
| `adapters/fake_vision.py` | REFERENCE_ONLY | 新建最小测试 Fake 适配器 | 不直接依赖旧路径 |

### 5.4 旧 UI

| R2 来源 | 分类 | 处理 |
|---|---|---|
| `ui/main_window.py` | REFERENCE_ONLY | 不迁移代码，只参考行为 |
| `ui/product_page.py` | REFERENCE_ONLY | 不迁移 8 区 Tkinter 实现 |
| `ui/history_page.py` | REFERENCE_ONLY | 不迁移代码 |
| `ui/ocr_intake_dialog.py` | REFERENCE_ONLY | 不作为最终入口 |

PySide6 空壳依据两张 UI 基准从零建立，只需启动、导航占位和基础资源加载，不实现完整功能。

### 5.5 物流上游

| R2 来源 | 分类 | 2.6 处理 |
|---|---|---|
| `logistics_cost/calculator.py` | KEEP | 作为冻结引擎基线导入，并记录来源元数据 |
| `logistics_cost/estimator.py` | ADAPT | 通过稳定服务接口调用 |
| `logistics_cost/weight_rules.py` | KEEP | 保持 R2 行为 |
| `logistics_cost/ai_schema.py` | ADAPT | 适配统一领域模型和错误码 |
| `config/logistics_config.json` | KEEP | 作为初始配置格式参考，不把值写死 |
| `tests/test_integration.py` | ADAPT | 迁入物流兼容测试 |
| `tests/test_replay_validation.py` | ADAPT | 迁入校准回放验证 |

物流源文件在 2.6 中的初始副本只代表已发布基线。后续算法更新必须回到上游项目完成并发布版本包。

### 5.6 校准数据

KEEP：

- Round 01 51 样本；
- Round 01 清洗样本；
- Round 02 14 样本；
- R2 已跟踪 AI JSON 示例；
- 回放脚本和清洗脚本按需 ADAPT。

DOCUMENT_ONLY：回放报告、校准验证报告、下一轮指导和反馈表模板。

EXCLUDE：R2 标签之外的三份 AI JSON 和任何真实用户反馈文件。

### 5.7 仓库工具

KEEP/ADAPT：

- 根 `AGENTS.md` 中与新项目不重复的通用规则；
- `docs/AGENT_WORKFLOW.md`；
- `tools/generate_step_report.py`；
- `tools/report_config.json`；
- `tools/run_step_report.bat`；
- `.gitignore` 的安全排除规则。

## 6. 阶段 1 执行步骤

### Step 1：建立干净结构与来源记录

- 创建项目目录；
- 放入阶段 0 文档和 UI 图片；
- 创建最小 `pyproject.toml`、依赖文件和 `.gitignore`；
- 生成 `SOURCE_PROVENANCE.md` 和初始 `MIGRATION_MANIFEST.md`；
- Commit 1。

### Step 2：迁移利润、规则和配置核心

- 提取 ADAPT 文件；
- 移除 UI 依赖；
- 统一包 import；
- 迁移利润与动态货代相关测试；
- 运行关联测试；
- Commit 2。

### Step 3：迁移物流发布基线与校准样本

- 导入 R2 物流核心、schema、配置和校准数据；
- 增加来源/版本元数据；
- 建立稳定应用接口，不让 UI 直连内部文件；
- 迁移集成与回放测试；
- Commit 3。

### Step 4：迁移图片会话、领域模型与存储基础

- 迁移三类图片类型、会话、哈希、相对路径和结果模型；
- 建立最小 SQLite schema，只服务新项目；
- 不迁移真实旧库；
- 迁移基础测试；
- Commit 4。

### Step 5：建立 PySide6 最小空壳

- 主窗口可启动；
- 左侧六项导航可见；
- 新商品测算和设置页只做最小占位或静态骨架；
- 能加载两张基准图片作为开发文档资源；
- 不实现完整 UI 功能；
- Commit 5。

### Step 6：报告、验证脚本和收口

- 创建 `verify_baseline.bat`；
- 生成迁移清单、测试报告和排除清单；
- 全量运行阶段 2 测试；
- 敏感信息扫描；
- Commit 6。

## 7. 阶段 2 测试矩阵

| 测试组 | 目标 | 最低要求 |
|---|---|---|
| 利润核心 | 正算、利润反推、利润率反推、防循环更新依赖的纯函数 | 0 failed |
| 利润调整 | 条件、币种、固定额/百分比、启停、归档 | 0 failed |
| 物流核心 | 计费重、体积重、费用拆分、动态货代、尾程 | 0 failed |
| 物流回放 | Round 01 + Round 02 样本兼容 | 0 failed |
| AI schema | R2 示例校验、缺失值、不填假默认 | 0 failed |
| 图片录入 | 上传路径、粘贴/拖拽服务逻辑、三类图片、哈希与临时会话 | 0 failed；GUI 环境跳过需说明 |
| 数据模型 | AI/人工/系统/实际四类值、快照、相对路径 | 0 failed |
| 存储 | 新 SQLite 初始化、事务、备份边界 | 0 failed |
| PySide6 启动 | 最小窗口导入和启动烟测 | 0 collection errors；无头环境可说明 |
| 报告工具 | 自动收集 Git、文件和测试信息 | 0 failed |
| 安全扫描 | Key、Token、Cookie、真实数据库和图片排除 | 0 发现 |

阶段总要求：

```text
0 failed
0 collection errors
```

任何 skipped 必须记录环境、原因、是否影响最终 GUI 验收。

## 8. 敏感与无效文件排除

必须排除：

- `.git/`、`.venv/`、缓存；
- `build/`、`dist/`；
- 旧压缩包；
- 真实数据库；
- 真实用户图片；
- Token、Cookie、API Key；
- 浏览器 Profile；
- 测试临时输出；
- 未纳入 R2 的 `Image Search/` 修改；
- 无效阶段报告。

## 9. 独立仓库交付

本阶段不生成迁移压缩包。验证通过后推送 `migration/r2-baseline`，记录完整 Commit SHA，并执行干净克隆验证。正式软件达到发布阶段后再单独生成解压即用文件夹版。
