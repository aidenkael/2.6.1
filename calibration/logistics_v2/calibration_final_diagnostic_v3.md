# CALIBRATION FINAL DIAGNOSTIC (v3)

## 数据概览
- 总记录数: 77 (CAL-001 ~ CAL-077)
- 首次估算可用样本: 71
- after_actual (不参与首次统计): 3
- benchmark_corrected_only (仍可参与): 2
- root_cause_corrected_only (仍可参与): 1
- unknown (不参与): 2
- 排除样本: 6
- 独立商品组: 69

## 首次估算准确率
- 命中(match): 9 (12.7%)
- 保守命中(conservative_match): 1 (1.4%)
- 高估(overestimate): 28 (39.4%)
- 低估(underestimate): 33 (46.5%)
- 平均误差: 38.2%
- 中位误差: 20.0%

## after_actual 样本 (估算在看到实际后被替换, 不参与首次统计)
- CAL-054: est=8.0, act=8.0, dir=match
- CAL-057: est=14.0, act=14.0, dir=match
- CAL-062: est=10.0, act=10.0, dir=match

## benchmark_corrected_only (只修正实际费用口径/证据解释, 估算未替换, 仍可参与)
- CAL-001: est=55.0, act=44.2, dir=overestimate
- CAL-026: est=12.0, act=12.0, dir=conservative_match

## root_cause_corrected_only (只修正root_cause名称, 估算未替换, 仍可参与)
- CAL-002: est=38.4, act=18.05, dir=overestimate

## unknown 样本 (无法确认估算来源, 不参与)
- CAL-029: 估算来源未知; 无估算值
- CAL-070: 估算来源未知; 实际尺寸已忘记

## 排除样本详情
- CAL-009: 无实际运费 (origin=before_actual)
- CAL-029: 估算来源未知; 无估算值 (origin=unknown)
- CAL-054: 估算在看到实际后被替换 (origin=after_actual)
- CAL-057: 估算在看到实际后被替换 (origin=after_actual)
- CAL-062: 估算在看到实际后被替换 (origin=after_actual)
- CAL-070: 估算来源未知; 实际尺寸已忘记 (origin=unknown)

## stored_estimate_origin 逐条审计依据
(原v2中15条corrected_after_actual的重新审计结果)

- **CAL-001**: 估算55.0未替换。notes修正的是实际费用口径(44.2=纯头程非合计), 反推体积比从62%修正为80%。估算字段本身从未改动。
  - resolved_est=55.0, resolved_act=44.2, dir=overestimate, origin=benchmark_corrected_only
- **CAL-002**: 估算38.4未替换。root_cause从SOFT_GOODS_UNDER_FOLDED修正为AI_VISUAL_ERROR。估算字段未改动。
  - resolved_est=38.4, resolved_act=18.05, dir=overestimate, origin=root_cause_corrected_only
- **CAL-007**: 估算73.9未替换。notes描述了修正过程(73.9->18.48), 但stored字段仍为73.9(原始首次估算值)。修正只在notes中描述。
  - resolved_est=73.9, resolved_act=18.5, dir=overestimate, origin=before_actual
- **CAL-009**: 估算9.0未替换。notes修正了重量解释(硅胶密度), 估算字段未改。无实际运费(resolve返回None), 排除。
  - resolved_est=9.0, resolved_act=None, dir=unknown, origin=before_actual
- **CAL-021**: 估算6.0(estimated_head_freight_no_trust)未替换。notes建议<=50g不加+0.05kg修正, 是规则建议非字段替换。
  - resolved_est=6.0, resolved_act=4.75, dir=overestimate, origin=before_actual
- **CAL-026**: 估算12.0未替换。notes修正的是匹配口径解释: 正常档含20g包材余量=保守级命中。估算字段未改动。
  - resolved_est=12.0, resolved_act=12.0, dir=conservative_match, origin=benchmark_corrected_only
- **CAL-031**: 估算12.0未替换。notes中"不加+0.05kg修正"指不应用修正规则, 非看到实际后修正。估算字段从首次起就是12.0。
  - resolved_est=12.0, resolved_act=12.0, dir=match, origin=before_actual
- **CAL-033**: 估算6.0(estimated_no_trust_head)未替换。notes"不加修正命中0%"指不应用+0.05kg规则, 非看到实际后替换。
  - resolved_est=6.0, resolved_act=6.0, dir=match, origin=before_actual
- **CAL-037**: 估算10.0(正常档)未替换。保守档12.0命中实际, 但正常档10.0字段未改动。方向=underestimate(10.0<12.0)。
  - resolved_est=10.0, resolved_act=12.0, dir=underestimate, origin=before_actual
- **CAL-041**: 估算3.0(estimated_no_trust_head)未替换。notes"不加修正命中0%"同CAL-033模式。估算字段未改动。
  - resolved_est=3.0, resolved_act=3.0, dir=match, origin=before_actual
- **CAL-044**: 估算17.3未替换。notes描述偏差原因(纸板内衬多15-20g), 未替换估算字段。
  - resolved_est=17.3, resolved_act=19.0, dir=underestimate, origin=before_actual
- **CAL-047**: 估算18.48未替换。notes描述偏差原因(乳胶3->2cm), 未替换估算字段。
  - resolved_est=18.48, resolved_act=12.0, dir=overestimate, origin=before_actual
- **CAL-054**: 第一轮估算4.5(10x3x3cm/30-40g), 看到实际8.0后修正为12x5x4cm/80g->8.0。stored字段已替换为命中值。
  - resolved_est=8.0, resolved_act=8.0, dir=match, origin=after_actual
- **CAL-057**: 第一轮估算6.0(OPP袋45g), 看到实际14.0后修正为挂卡+纸盒140g->14.0。stored字段已替换为命中值。
  - resolved_est=14.0, resolved_act=14.0, dir=match, origin=after_actual
- **CAL-062**: 第一轮估算6.0(60g), 看到实际10.0后按商家规格100g修正->10.0。stored字段已替换为命中值。
  - resolved_est=10.0, resolved_act=10.0, dir=match, origin=after_actual

## 候选规则 (v3 修正分组)

### 1. thin_soft_fabric_volume_correction
- 适用: 薄袜/薄针织/袖套类, 折叠后体积重偏高40-50%
- 支持条目: CAL-004, CAL-014, CAL-016, CAL-018, CAL-024, CAL-028, CAL-055, CAL-059
- 独立组数: 8
- v3修正: 移除CAL-068(PVC包)和CAL-075(PVC包), 仅保留真正薄款面料

### 2a. leather_bag_compression
- 适用: PU皮/真皮半硬包, 厚度x0.65
- 支持条目: CAL-065
- 独立组数: 1
- 状态: 单样本, 仅观察

### 2b. thin_pvc_full_fold
- 适用: PVC薄款透明化妆包, 全折叠(10x10x3cm模板)
- 支持条目: CAL-068
- 独立组数: 1
- 反例/边界: CAL-075 (CAL-075: PVC但压缩非全折叠, 证明需区分薄款vs有底厚款)
- 状态: 单样本+1反例, 仅观察

### 2c. fabric_backpack_compression
- 适用: 牛津布/帆布软包, 厚度x0.4
- 支持条目: CAL-076
- 独立组数: 1
- 状态: 单样本, 仅观察

### 3. rigid_protrusion_packaging
- 适用: 不可压缩硬质突出(手柄/夹扣/扳手), 包装厚度>=本体+2cm
- 支持条目: CAL-054, CAL-056
- 独立组数: 2
- v3修正: 移除CAL-047(乳胶头套=soft_flattened_protrusion, 方向是压平减小厚度, 非硬质加厚)
- 移至观察: CAL-047 (软质压平, 非硬质突出)

## 最终建议 (不实施)

### 可进入AI包装估算提示规则
- thin_soft_fabric_volume_correction: 8独立组支持, 方向一致(均高估), 可建议薄款袜/袖套ai_package_size_cm厚度从4cm->3cm
- rigid_protrusion_packaging: 2独立组支持, 可建议手柄/夹扣类包装厚度+2cm

### 仅保留观察
- leather_bag_compression (CAL-065): 单样本, 需更多皮包验证
- thin_pvc_full_fold (CAL-068): 单样本+1反例(CAL-075), 需更多PVC包验证
- fabric_backpack_compression (CAL-076): 单样本, 需更多布包验证
- soft_flattened_protrusion (CAL-047): 单样本, 乳胶/软质突出压平

### 数据不足不得实施
- 包袋三档压缩规则各仅1样本, 不得合并为已验证固定规则
- leather/pvc/fabric三个子类型需各自>=3独立组方可实施

## 方向判定方法
- 方向按 resolved_estimated vs resolved_actual 对比
- conservative_match保留: 正常档数值碰巧相等但含包材余量, 不计为true match
- 原始error_direction不一致时以 resolved est vs act 为准
- est或act为None -> unknown

## 实际运费解析方法
- 优先级: actual_head_freight_rmb > actual_head_freight_avg_rmb > actual_head_freight_range_rmb中点 > None
- CAL-003: actual_head_freight_avg_rmb=4.35 (actual_head_freight_rmb不存在)
- CAL-016: actual_head_freight_avg_rmb=4.65 (actual_head_freight_rmb不存在)

## 已排除/不修改
- Round 01 原始校准文件不变
- Round 02 原始校准文件不变
- 物流算法、配置、AI JSON均未修改
