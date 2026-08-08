# AI 识图 / 包装估算 真实离线评测框架

基线：`main @ 9cc9269`。本框架只读调用生产入口
（`RecognitionService.parse_payload`、`PackagingEstimationService.estimate`），
**不调用任何 API、不修改任何生产代码**。以后所有 AI prompt / CAL / 包装规则修改，
必须先用本框架在真实案例上比较 Baseline vs Experiment。

## 目录结构

```
tests/evaluation/vision_packaging/
  README.md                 本文件
  schema/case.schema.json   案例格式参考
  templates/                空白模板（case.json / ai_raw_response.json）
  harness/                  评测代码（仅测试侧，生产不得 import）
  synthetic/                虚构机制回归案例（不计入真实准确率）
```

真实案例与图片 **只保存在仓库外** 数据目录（绝不提交 GitHub）：

```
E:\Profit-Accounting-2.6.1-evaluation-data\cases\<case_id>\
  case.json               元数据 + 人工标准
  ai_raw_response.json    完整 provider 响应
  images/                 可选真实图片
```

数据目录解析顺序：`--data-dir` > 环境变量 `PROFIT_ACCOUNTING_EVAL_DATA_DIR`
> 默认 `E:\Profit-Accounting-2.6.1-evaluation-data`。
`.gitignore` 另加了 `evaluation-data/`、`tests/evaluation/**/real/` 等保险条目。

## 使用（普通用户最简步骤）

1. 在软件里正常跑一次 AI 识图（诊断日志自动保存 raw response）。
2. `python tools/import_vision_diagnostic_case.py --diagnostic <数据目录\logs> --out E:\Profit-Accounting-2.6.1-evaluation-data`
3. 打开生成的 `case.json`：逐张填 `image_role`（main/dimension/weight/packaging/other），
   填人工标准（允许 unknown、区间、多个可接受包装方式）。
4. `python tools/evaluate_vision_packaging.py --data-dir E:\Profit-Accounting-2.6.1-evaluation-data`

没有真实案例时命令输出 `0 real evaluation cases` 与“评测框架已就绪，需要真实案例。”
`--synthetic` 运行虚构机制回归（明确标注，不计入真实准确率）。
`--list-experiments` 查看 baseline 与实验策略。

## 重放分层（回答“数值在哪一层被改变”）

| 层 | 含义 | 生产入口 |
| --- | --- | --- |
| AI_RAW | provider content 内模型原样 JSON | `_extract_content` + json.loads |
| PARSED | 仅数值清洗 + from_dict（未 normalize） | `_clean_numeric_fields` |
| NORMALIZED | parse_payload 输出（含 normalize、dimension 语义门、视觉补全） | `RecognitionService.parse_payload` |
| FINAL | 仲裁后最终包装提案 | `PackagingEstimationService.estimate` |

每例同时记录：AI 原包装候选、最终候选、`candidate_records`、`rejected_candidates`、
CAL adjustments（`cal_coordination.adjusted_fields`/`risk_only`）、salvage adjustments
（`candidate_field_salvage.diagnostic`）、`proposal_source`、尺寸四层轨迹。

## 评分指标（不设单一总分）

- `ai_candidate_accuracy`：AI 原始候选 vs 人工标准
- `parsed_accuracy`：parser 后候选
- `final_accuracy`：最终包装
- 本地处理分类：`improved` / `unchanged` / `degraded`（+`local_improvement_rate`）
- **`post_ai_degradation_rate` = #(AI正确 且 Final错误) / #(AI正确)**，当前最重要指标

尺寸按人工区间判断（不要求相等）；包装方法按 `acceptable_methods` 集合
（双向子串匹配，`["*"]` 表示任意非空均可）；未填写的标准跳过不计。

## V2 兼容收口（legacy 标记与未来字段）

- 当前生产引擎的 `normal`/`conservative` 双档输出在重放报告 FINAL 层中
  明确标记为 **`legacy_current_engine_output`**，不是 V2 长期数据标准。
- FINAL 层同时给出 V2 单一主结果预留 **`estimated_package`**
  （length/width/height/weight/method，从被采纳正常档派生）。
- case.json 人工标准新增三组可选字段（全部允许 null / unknown，不强制填写）：
  - `estimated_package`：V2 单一主包装结果标准（区间格式同 normal_packaging）；
  - `structure_feedback`：rigidity/shape_retention/foldability/compressibility、
    foldable/coilable/detachable/rigid_parts、axis_behavior；
  - `actual_feedback`：actual_first_mile_fee_rmb、actual_chargeable_weight_kg、
    actual_forwarder、actual_package_dimensions/weight、actual_packaging_method。
- 业务评分字段预留：`chargeable_weight_error`、`shipping_cost_error`、
  `underestimate`、`severe_underestimate`（估计低于实际计费重 10% 以上）。
  事实不足时输出 `unavailable`，**绝不编造**；重放不运行物流引擎，
  因此本轮 `shipping_cost_error` 恒为 unavailable。
- real = 0 的现状如实保持；synthetic 与 real 继续严格分开。

## Baseline / Experiment（阶段 E/I）

实验策略在 `harness/experiments.py` 中以 `PackagingEstimationService` 子类实现，
位于 `tests/` 下，生产软件不会也不能 import；不修改生产类本身。
当前登记三个审计假设实验（仅接口与最小实现，**结论需真实案例支撑**）：

- `expA_relaxed_outline_check`：放宽 `packing_action_not_reflected_in_outline`
- `expB_independent_packaging_candidate`：dimension 语义问题不株连独立包装候选
- `expC_cal_risk_only_for_complete_ai`：AI 完整候选时 CAL risk-only

## DiagnosticLogger 导入（阶段 F）

生产 `DiagnosticLogger` 已在 parser 前把脱敏后的 `provider_raw_response` 写入
`<数据目录>/logs/<时间>_<操作>_<id>/ai-response.json`（`_sanitize` 已剔除
authorization/api_key 等键并替换 base64 图片）。importer 只做复制 + 二次脱敏
（路径去全路径、再扫敏感模式），不修改生产 Logger。

## 上一份审计结论重新校准（阶段 A）

### A 类：已由当前源码直接证明（机制事实）

- prompt 单次要求约 70 个字段、30+ enum，且要求证据定位（`RecognitionService._prompt`）。
- `estimate` 用 observation 层语义问题（如 `dimension_evidence_not_outer_dimensions`）
  整批否决 AI 包装候选，salvage 后用本地公式补全
  （`_validate_ai_semantics` + `_salvage_ai_candidate`）。
- `_transport_outline` 的 flat_fold/coil 机械折叠公式存在（如最长边/3）。
- `packing_action_not_reflected_in_outline` 否决逻辑存在：包装最长边 ≥ 商品外廓最长边即否决。
- CAL strong 匹配且 AI 非 high 置信时逐字段覆盖（`_coordinate_ai_cal_fields`）。
- 声明“包装盒”类方式而无定位证据即否决 method/weight（`_has_individual_package_evidence`）。
- `ImageSlotWidget.image_type()` 恒返回 MAIN、`set_image_type()` 空操作（`ui/widgets.py`）。
- DiagnosticLogger 在 parser 前落盘脱敏 raw response（`recognition_service.recognize`）。

### B 类：由合成重放证明“可能发生”（机制可复现，非业务频率）

- 软质可扁平商品被折叠公式压小后替换 AI 更合理的候选（本轮 syn_02 仍复现该路径）。
- dimension 范围语义触发整批否决、AI 独立包装候选被株连（syn_02）。
- CAL strong 匹配在 AI 非 high 时改写数值（机制存在；触发条件依赖 registry 词表）。

### C 类：尚需真实商品验证的推断（不得当作事实引用）

- “70 字段导致模型推理能力明显下降”——需同图同模型的简化/完整 prompt 对照。
- “source_image_index 会迫使 AI 虚构证据”——需真实 raw response 中证据与图片核对。
- “方案 B 一定提高准确率”——需 expB vs baseline 在真实案例上的对比。
- “CAL 是实际错误率第二/第三大来源”——无任何真实频率数据。
- P1–P7 对实际业务错误率的占比——全部待本框架积累真实案例后统计。

原则：**机制发现不撤销；业务发生频率必须有真实案例证据。**
