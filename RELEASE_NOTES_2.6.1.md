# Profit-Accounting-2.6.1 Release Notes

## 发布状态

2.6.1 已完成最终发布前验收，结论：

`PROFIT-ACCOUNTING-2.6.1 RELEASE ACCEPTANCE = PASS`

发布验收基线 commit：

`bba01ae9f0de48c61582072c4ae97e3e632d1862`

正式发布 tag 必须指向本次版本元数据收口合并后的最终 `main` commit，而不是更早的验收基线。

## 验收结果

- 全量测试：909 passed，0 failed；
- sensitive scan：0 findings；
- Windows 真实启动：通过；
- 1920×1080 UI：通过；
- 缩小窗口滚动行为：通过；
- 新商品测算完整流程：通过；
- 历史保存、修改与重启持久化：通过；
- Calibration Feedback Export V2：通过；
- Settings 校准包管理：通过；
- Formal Runtime Bundle 导入 / 手动启用 / 重启 / 删除 fallback：通过；
- data_dir 隔离：通过；
- CAL77 conservative migration：通过；
- 发布 blocker：无。

## 2.6.1 校准架构

生产计算由软件确定性引擎负责。校准闭环固定为：

`软件导出 Feedback V2 → Agent 生成 Candidate → Validator → Offline Replay → Promotion → Formal Runtime Bundle → 软件导入 → 用户手动启用 → 确定性运行`

Agent 不拥有生产规则的直接激活权。

## CAL77 最终定位

CAL77 原始 77 条历史样本字节级保留，不删除、不伪装成新闭环 validated truth。

builtin registry：

- version：`packaging-rules-v2-cal77-conservative`
- sample_rules：77 total / 0 enabled
- aggregate_rules：9 total / 1 enabled
- 唯一 enabled aggregate：`AGR-THIN-TEXTILE-001`
- 该规则为 low confidence legacy fallback，仍需未来真实 Feedback V2 重新验证。

未来新增真实校准不再手工增加 CAL-078 等旧式规则。

## 发布边界

本次发布收口不改变：

- PackagingEstimationService 生产算法；
- DB schema；
- 物流公式；
- 利润公式；
- 已冻结 UI 布局；
- CAL77 原始 77 条历史记录。

## 版本元数据

发布前将 Python 项目元数据从旧 RC 标识更新为正式版本：

`2.6.1`

正式 tag 建议：

`v2.6.1`

Tag 应在版本元数据 PR 合并并确认 CI 通过后创建。
