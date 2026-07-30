# SVG 检查报告（SVG_CHECK_REPORT.md）

> 对 `original/main-ui-original.svg`、`original/settings-ui-original.svg` 进行的完整性、兼容性、可重建性检查报告。

## 1. 文件基本信息

| 项目 | 主界面 SVG | 设置界面 SVG |
|------|------------|--------------|
| 文件路径 | `original/main-ui-original.svg` | `original/settings-ui-original.svg` |
| 文件大小 | 1,595,378 字节 (≈ 1.52 MB) | 1,029,539 字节 (≈ 0.98 MB) |
| 行数 | 440 | 275 |
| 画布尺寸 | 1920 × 1080 | 1920 × 1080 |
| viewBox | `0 0 1920 1080` | `0 0 1920 1080` |
| xmlns | `http://www.w3.org/2000/svg` | `http://www.w3.org/2000/svg` |
| 命名空间 | 默认 svg 命名空间 | 默认 svg 命名空间 |

## 2. XML / SVG 合法性

| 检查项 | 主界面 SVG | 设置界面 SVG |
|--------|------------|--------------|
| 是否为有效 XML | ✅ 是 | ✅ 是 |
| 是否为有效 SVG | ✅ 是（标准 svg 根元素） | ✅ 是 |
| 标签闭合 | ✅ 全部闭合（`</svg>`） | ✅ 全部闭合 |
| 唯一根元素 | ✅ 仅一个 `<svg>` | ✅ 仅一个 `<svg>` |
| ID 唯一性 | ✅ 内部 ID（如 `clip0_2_2`、`path-1-inside-1_2_2`）唯一，无冲突 | ✅ 内部 ID 唯一 |

## 3. 外部资源引用

| 资源类型 | 检测情况 |
|----------|----------|
| 外部图片（`<image>`、`<use href>` 外部链接） | ❌ 未发现 |
| 外部字体（`@font-face`、`font-family` 远程加载） | ❌ 未发现 |
| 外部样式表（`<link>`、`<?xml-stylesheet?>`） | ❌ 未发现 |
| 远程链接（`http://`、`https://`） | ❌ 未发现 |
| 内部 clip-path / mask 引用 | ✅ 均为内部 ID 引用（`url(#xxx)`），全部可在文件内找到定义 |
| 内部 `<use>` 引用 | ❌ 未使用（所有元素直接绘制） |

**结论**：两个 SVG 都是完全自包含的离线文件，不依赖任何外部资源。可以安全地复制、移动、嵌入到其他项目中。

## 4. 字体信息

| 项目 | 状态 |
|------|------|
| SVG 内 `@font-face` 声明 | ❌ 未声明 |
| SVG 内 `font-family` 属性 | ❌ 未使用（因文字均为 path） |
| 实际渲染字体（视觉判断） | 推测为「思源黑体」/「阿里巴巴普惠体」类中文无衬线字体（待确认） |
| 字符是否转为 path | ✅ 全部转为 path（无 `<text>` 元素） |

**关键影响**：
- 文字以 path 形式存在 ⇒ 无法搜索/复制/翻译/换字体
- 重做 UI 时，文案需要从原始设计稿或本目录的 PNG 预览中获取
- 字号、行距、字间距等信息未在 SVG 中保留，只能通过视觉估计

## 5. 主要颜色（从 fill 属性提取）

| 颜色值 | 用途（高频） |
|--------|--------------|
| `#1769F6` | 主品牌色：Logo、按钮、激活状态、强调数字 |
| `#F5F8FC` | 主背景 |
| `#F8FAFD` | 次背景（侧边栏、内容卡片） |
| `#FFFFFF` | 卡片底色、输入框底 |
| `#EAF0F6` | 分隔线 |
| `#EAF2FF` | 选中项背景（导航） |
| `#DCE5F0` | 描边 |
| `#6E7B90` | 次要文字 / 图标 |
| `#172033` | 主要文字（深色） |
| `#FFF4E5` | 警告徽章底色（未保存） |
| `#F53F3F` | 危险操作（归档/删除） |
| `#E8F5E9` / `#1AB759` | 成功 / 启用状态（绿色系，具体色值需在 SVG 中 grep 二次确认） |

**说明**：
- 颜色均为十六进制，与 Figma 导出风格一致
- 没有 CSS 变量或渐变（`<linearGradient>` 等）使用
- 没有阴影效果（`<filter>`）

## 6. Figma 特有结构

判断依据：图层 ID 命名风格。

| 特征 | 出现位置 |
|------|----------|
| `clip0_2_2`、`clip1_2_2` ... | 主界面 SVG 中存在多个 clip-path ID |
| `path-1-inside-1_2_2`、`path-43-inside-2_2_2` | mask path 命名风格 |
| `clip0_17_2` ... | 设置界面 SVG 中使用 `_17_` 前缀 |

**结论**：两个 SVG 均来自 Figma 导出。命名规律为 `类型_图层ID_节点ID_导出版本`，中间数字（`2_2` / `17_2`）可能对应 Figma 文件中的页面 ID 与导出序号。

**对重建的影响**：
- Figma 的 clip-path 嵌套结构可以正常被 SVG 渲染
- 跨软件导入时（如 Adobe XD、Sketch、Inkscape）ID 名称可能被保留或重命名，但不影响渲染
- 不依赖 Figma 特有的 `figma:` 命名空间，跨工具兼容

## 7. 跨软件导入可能丢失的内容

| 内容 | 跨软件丢失风险 |
|------|----------------|
| `<rect>` / `<path>` 等基础元素 | ✅ 低（标准 SVG） |
| `clip-path` / `mask` | ⚠️ 中（部分老旧工具支持有限，但主流浏览器、Inkscape、Illustrator 均支持） |
| 字符 path（已转为 path 的文字） | ⚠️ 中（视觉保留但不可编辑） |
| 渐变、滤镜 | ✅ 低（本文件未使用） |
| 字体声明 | ✅ 不适用（本文件无字体声明） |
| CSS 动画 | ✅ 不适用（本文件无动画） |

## 8. 对 PySide6 桌面软件重建的注意事项

> 下游若使用 PySide6（Qt for Python）重建该 UI，请关注以下事项：

### 8.1 渲染层选型

- 可使用 `QSvgWidget` 直接加载 SVG 作为静态参考图，但 **不能直接当成交互 UI 使用**。
- 建议：根据本资料包的结构化数据（`ui_manifest.json`） + 截图（`original/*.png`） + normalized-svg（用于取坐标）用 Qt 原生组件重建。

### 8.2 像素与 DPI

- 原始 SVG 是 1920×1080 设计稿，对应主流桌面分辨率。
- PySide6 在不同 DPI 下的缩放：建议在 `main.py` 中固定 `Qt.AA_EnableHighDpiScaling`，并按 `devicePixelRatio()` 缩放坐标。

### 8.3 颜色与样式

- 颜色值已在 `UI_COMPONENTS.md` 与 `SVG_CHECK_REPORT.md` 列出，可在 Qt 样式表（QSS）中映射。
- 主品牌色 `#1769F6` 建议抽为 QSS 变量或 Python 常量。

### 8.4 字体

- 因 SVG 中文字已转为 path，原字体未声明。建议在 PySide6 中显式设置：
  - Windows：`"Microsoft YaHei UI"` 或 `"PingFang SC"`
  - macOS：`"PingFang SC"`
  - Linux：`"Noto Sans CJK SC"`
- 字重建议：`normal`（正文）、`medium`（标题）、避免 `bold`（与设计稿不符）

### 8.5 控件对应（Qt 控件映射）

| 设计稿组件 | 建议 Qt 控件 |
|------------|--------------|
| 主按钮（蓝底） | `QPushButton`（自定义 QSS） |
| 次按钮（白底） | `QPushButton`（自定义 QSS） |
| 输入框 | `QLineEdit` |
| 下拉框 | `QComboBox` |
| 标签/徽章 | `QLabel` |
| 卡片容器 | `QFrame` + QSS |
| 图片上传框 | 自定义 `QWidget` + `dragEnterEvent` / `dropEvent` |
| 数据表 | `QTableWidget` 或 `QTableView` + Model |
| 列表（含徽章） | `QListWidget` + 自定义 item |
| 导航栏 | `QListWidget` + 自定义 item |

### 8.6 图标

- SVG 中所有图标都是 path 形式。
- 建议在 PySide6 中抽出图标库（如 QtAwesome / 自定义 SVG icon set），按视觉意图选择对应图标。

### 8.7 状态补充

当前 SVG 是静态快照。PySide6 重建时需要补齐：
- hover / pressed / disabled / focus 视觉
- 输入校验错误提示
- loading / 空数据 / 错误页

## 9. 已知问题

1. **文字不可编辑**：所有可读文字都是 `<path>`，重建时需通过本资料包或原设计稿还原文案。
2. **未提供交互态**：快照未涵盖 hover、active、disabled、focus、loading。
3. **未提供响应式**：固定 1920×1080；高分屏或小窗口需要单独处理。
4. **未提供多语言**：当前快照为单一中文版本。
5. **PNG 为压缩预览**：肉眼识别存在小字符模糊情况（详见 `UI_TEXT_CONTENT.md` 复核清单）。
6. **Figma ID 命名**：不影响渲染，但会让文件看起来「工程感较弱」。若需美化命名，可在 normalized-svg 上做 ID 重命名（不影响视觉）。

## 10. 跨平台验证清单

下游开发人员可用以下方式快速验证 SVG 可用性：

```bash
# Linux / macOS（需要 xmllint）
xmllint --noout original/main-ui-original.svg
xmllint --noout original/settings-ui-original.svg

# 或者 Python
python -c "import xml.etree.ElementTree as ET; ET.parse('original/main-ui-original.svg'); ET.parse('original/settings-ui-original.svg'); print('OK')"
```

打开方式：

```bash
# Linux
xdg-open original/main-ui-original.svg

# macOS
open original/main-ui-original.svg

# Windows
start original/main-ui-original.svg
```

或者直接拖入浏览器（Chrome / Firefox / Edge 均支持）。
