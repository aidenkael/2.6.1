# Agent → 软件物流校准规则合同 V1

状态：设计冻结候选（未接入生产运行时）

基线：`main@6f0a8cd04edf8c5627d46a55762bd67576585a23`

## 1. 目标与边界

长期链路固定为：

`软件导出事实反馈 → Agent 离线分析 → candidate 规则包 → 软件同引擎 offline replay → validator → validated 规则包 → 软件导入/人工启用 → 确定性运行`

职责边界：

- 软件是唯一生产计算引擎。
- Agent 只负责离线分析和生成候选规则，不参与在线包装判断。
- Agent 不得修改物流费率、体积重公式、货代费率、尾程、利润、汇率、SHEIN 规则。
- 本合同只校准包装估算规则。
- CAL77 本阶段只作为现有兼容背景，不在本合同中决定迁移、保留或删除。

## 2. 当前代码约束

V1 直接沿用 `PackagingEstimationService` 当前真正支持的 aggregate rule 语义，不另造一套动作语言。

当前可消费的匹配字段：

- `any_terms`
- `materials`
- `rigidity`
- `foldability`
- `compressibility`
- `forbid_hard_structure`
- `requires_shape_retention`
- 可选 `guard.any_hard_structure_or_shape_retention`
- 可选 `guard.foldability_not`

当前可消费的动作只有四类：

1. `smallest_axis_scale`
   - `normal`
   - `conservative`
   - 可选 `min_cm`
2. `smallest_axis_add`
   - `normal_cm`
   - `conservative_cm`
3. `volume_ratio`
   - `normal`
   - `conservative`
4. `reference_scaled_template`
   - `reference_product_size_cm`
   - `normal_package_size_cm`
   - `conservative_package_size_cm`
   - 可选 `scale_min`
   - 可选 `scale_max`

重要：当前 `smallest_axis_add` 只能作用于“最短轴”，不支持 `axis=height` 之类的指定轴语义。V1 不引入运行时不存在的动作。

## 3. 三种数据对象

### A. Feedback Package

软件 → Agent 的事实输入。

它保存真实历史事实，不是规则，不可直接进入生产运行时。

### B. Candidate Rule Package

Agent → offline replay 的候选规则包。

Agent 只能生成：

`status = "candidate"`

Agent 不得自行写入 `validated`。

### C. Validated Rule Package

由软件侧 validator + offline replay 通过后产生。

规则主体与 candidate 使用同一 schema，仅由受控晋级流程写入：

`status = "validated"`

并附带软件生成的 `validation` 摘要。

这样只维护一个规则 schema，不维护 Candidate / Production 两套格式。

## 4. Package V1 顶层结构

```json
{
  "schema_version": "agent-calibration-rule-package-v1",
  "package_id": "cal-20260811-001",
  "calibration_version": "agent-v1-r001",
  "created_at": "2026-08-11T00:00:00Z",
  "generator": "offline-agent",
  "source_export_batch_ids": ["batch-id-1"],
  "base_engine_version": "packaging-estimation-v2-candidate-arbitration",
  "base_calibration_version": "local-calibration-v3-77-samples-rules-v1",
  "status": "candidate",
  "rules": [],
  "validation": null
}
```

字段说明：

- `schema_version`：必填；软件决定是否支持该合同。
- `package_id`：必填；包级唯一 ID，防止重复导入。
- `calibration_version`：必填；人工可读版本。
- `created_at`：必填；ISO-8601 UTC。
- `generator`：必填；候选包生成来源。
- `source_export_batch_ids`：必填；追溯到一个或多个反馈导出批次。
- `base_engine_version`：必填；validator 必须与当前引擎兼容性核对。
- `base_calibration_version`：可选；记录生成候选规则时使用的基线校准版本。
- `status`：必填；只允许 `candidate` / `validated`。
- `rules`：必填且非空。
- `validation`：candidate 必须为空；validated 必须由软件侧晋级流程生成。

## 5. Rule V1

```json
{
  "rule_id": "AGR-SOFT-TEXTILE-001",
  "enabled": true,
  "priority": 50,
  "description": "软质可折叠纺织品的最短轴包装余量修正",
  "match": {
    "any_terms": ["scarf", "shawl"],
    "materials": ["cotton", "polyester"],
    "rigidity": ["soft"],
    "foldability": ["good"],
    "forbid_hard_structure": true
  },
  "action": {
    "type": "smallest_axis_add",
    "normal_cm": 2.0,
    "conservative_cm": 3.0
  },
  "evidence": {
    "source_record_ids": ["record-001", "record-003"],
    "sample_count": 2,
    "rationale": "两条真实反馈均显示最短轴低估"
  }
}
```

### 5.1 match

V1 只允许当前引擎已经理解的匹配条件。

不新增商品属性词表，不在合同层发明新的分类体系。

`match` 至少应包含一个有效约束，禁止空 match 形成无条件全局规则。

### 5.2 action

V1 只允许当前 `_apply_action()` 已实现的四类动作。

不得在规则包中直接写最终包装尺寸作为一般规则动作；若确需模板缩放，只使用当前已有 `reference_scaled_template`。

### 5.3 priority

`priority` 是确定性冲突顺序的一部分。

V1 原则：

- 高 priority 优先。
- 同 priority 且适用范围重叠，不允许直接晋级为 validated；由 validator/replay 报冲突。
- 生产运行时禁止在线 AI 决定采用哪一条。

### 5.4 evidence

每条 Agent 新规则必须可追溯：

- `source_record_ids`：至少 1 条。
- `sample_count`：必须与有效证据数量一致或更大，并由 validator 核对。
- `rationale`：可选，供人工复核。

证据只解释“为什么产生该规则”，不参与运行时匹配。

## 6. validation 的所有权

Agent 生成 candidate 时：

```json
"status": "candidate",
"validation": null
```

Agent 不得自行填写 replay 通过结果。

未来 offline replay + promotion 流程完成后，由软件侧生成：

```json
{
  "status": "validated",
  "validation": {
    "replay_id": "replay-001",
    "engine_version": "packaging-estimation-v2-candidate-arbitration",
    "baseline_calibration_version": "...",
    "total_records": 50,
    "matched": 12,
    "improved": 10,
    "unchanged": 2,
    "degraded": 0,
    "conflicts": 0
  }
}
```

具体晋级阈值不在本合同中提前写死。阈值必须在 offline replay 实现阶段依据真实数据确定，避免现在凭空规定 `0 degradation`、`20% unmatched` 等未经验证的业务标准。

## 7. Import / Validator 边界

未来 validator 至少分三层：

### 7.1 Schema 硬拒绝

- schema_version 不支持
- 缺少必填字段
- rules 为空
- 包内 rule_id 重复
- match/action 含未支持字段
- action type 不支持
- 数值类型错误或非有限数
- 尺寸/比例为非法非正值
- package_id / rule_id 非法

### 7.2 语义硬拒绝

JSON Schema 无法表达、由 Python validator 检查：

- candidate 却携带伪造的 validation
- validated 缺少合法软件侧 validation
- conservative 参数小于 normal 参数
- reference template 维度非法
- 空 match
- 同优先级、重叠 match 导致不可确定冲突
- base_engine_version 与当前运行时不兼容

### 7.3 可导入但不可启用

可以保存用于审查，但不能进入生产：

- `status = candidate`
- replay 未完成
- replay 有未解决冲突
- evidence 不足
- 兼容性需要人工确认

## 8. Offline Replay 接口冻结原则

本轮不实现 replay，只冻结边界：

输入：

- 机器可读历史事实反馈
- candidate rule package
- 当前 `PackagingEstimationService`
- 基线 calibration version

核心要求：

- 必须调用软件同一套 `PackagingEstimationService`。
- 不允许 Agent 复制包装公式。
- baseline 与 candidate 使用同一组历史事实运行。

最小输出：

- total
- matched / unmatched
- improved / unchanged / degraded
- extreme_degradations
- conflicts
- per_record 命中规则与前后误差

具体误差函数和晋级阈值在 replay 阶段单独冻结。

## 9. 当前系统与 V1 的关系

当前 `CalibrationManager.import_package()` 仍只支持旧样本型 calibration JSON / ZIP，并会归一化为 `runtime_calibration.json`。

因此：

**本 V1 目前不是可直接导入生产的软件格式。**

这是有意设计：先冻结合同，再实现 validator/replay，最后才改软件导入层。

不得为了“现在就能导入”而把新规则包伪装成旧样本列表。

## 10. 暂不处理事项

本阶段不决定：

- CAL77 retain / migrate / delete
- sample_rules 是否长期保留
- builtin calibration 最终迁移方式
- runtime arbitration 重构
- Settings UI 新增规则详情页
- replay 阈值
- 自动启用 validated 包

这些必须在 V1 validator + replay 可运行后再决定。

## 11. 下一施工顺序

1. 冻结本合同与 JSON Schema。
2. 升级 Feedback manifest 为机器可读事实 V2，但保持 Excel 7 列不变。
3. 实现 V1 Python validator。
4. 实现最小 offline replay，并冻结误差函数/晋级阈值。
5. 软件导入层兼容 validated V1；之后再审计 CAL77 去留。

## 12. V1 核心原则

- 一个长期生产规则格式。
- Agent 只能产 candidate，不能自证 validated。
- 规则语言只使用当前确定性引擎真实支持的字段与动作。
- evidence 可追溯但不进入运行时判断。
- replay 必须复用软件现有引擎。
- 先验证，再导入，再人工启用。
