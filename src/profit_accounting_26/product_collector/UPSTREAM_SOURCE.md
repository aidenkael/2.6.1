# Product Collector 上游来源

- **上游 repository**: `aidenkael/Electronic-Commerce-Auto`
- **上游本地路径**: `E:\Electronic Commerce Auto\product_collector`
- **Source commit SHA**: `4f437250bf2aa1fd772d1b2b2f1b29ec76d68309`
- **Migration date**: 2026-08-13
- **2.6.1 目标基线**: `bba01ae` (main HEAD at migration time)

## 约束

- **禁止双主线开发**：采集核心逻辑只在上游 standalone 维护，2.6.1 仅做 package 化适配。
- 本模块迁入后，2.6.1 侧只允许：
  - import 路径调整
  - resource 路径调整
  - 日志目录注入
  - dependency adapter
- 不得重写采集核心（JSONP 解析、商品字段解析、搜索词串行、product_id 去重、随机抽样、KEEP/REMOVED 状态机）。
