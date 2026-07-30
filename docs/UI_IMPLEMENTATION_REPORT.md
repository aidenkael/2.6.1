# UI 实现报告

## 视觉来源

- `docs/assets/ui_baseline/new_product_calculation.png`
- `docs/assets/ui_baseline/settings.png`
- `docs/assets/ui_handoff/main-ui.svg`
- `docs/assets/ui_handoff/settings-ui.svg`
- `docs/assets/ui_handoff/ui_manifest.json`

## 已重建

- 左侧 6 项固定导航及底部数据目录、汇率、版本信息；
- 顶部标题、副标题、保存状态、用户信息；
- 新商品测算页的 3～6 图片框；
- 点击上传、Windows拖拽、Ctrl+V或“粘贴图片”按钮、预览、删除、类型修改；
- AI摘要、重新估算规格；
- 商品成本、国内运费、裸尺寸、裸重；
- 正常档、保守档及人工采用；
- 动态货代对比、尾程 USD/RMB 联动、系统总成本；
- 利润正算、目标利润反推、目标利润率反推、预留和规则效果；
- 保存记录、清空并新建、上游字段变化后的估算过期提示；
- 设置页基础设置、货代管理、利润调整规则；
- 历史记录、快照详情与实际反馈；
- 导入导出、校准包验证/即时启用/回滚、以图搜图本机入口；
- 左侧数据目录更改入口和汇率刷新。

## 视觉实现原则

- 主色：`#1769F6`；
- 背景、侧栏、卡片、边框和状态色按最新 Figma 交接资料映射；
- Windows 字体优先使用 `Microsoft YaHei UI`；
- 固定画布改为可滚动、可缩放的桌面布局，保留区域顺序与信息层级；
- SVG 仅作视觉参考，不作为交互层。

## 未完成的真实环境项

- 真实视觉 API 的模型配置和调用；
- Edge + 1688 插件返回候选链接的自动通信；
- Windows 100%、125%、150% 缩放下的人工视觉验收；
- Windows PyInstaller 成品构建与真实启动测试。
