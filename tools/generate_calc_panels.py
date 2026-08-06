"""从 forms/calculation/*.ui 生成 Python UI 类到 ui/generated/。

用法:
    python tools/generate_calc_panels.py              # 生成
    python tools/generate_calc_panels.py --check      # CI 验证一致性

生成时：
1. 解析原 .ui，收集每个 widget 的自定义属性（stdset="0" 或非 Qt 标准）
2. pyside6-uic 生成（移除自定义属性的临时 .ui）
3. 在生成代码 setupUi 末尾注入 setProperty() 调用恢复动态属性

--check 模式：在临时目录重新生成，比较输出一致性（不修改工作区）。
"""
import re, os, subprocess, sys, pathlib, tempfile, difflib

UI_DIR = "src/profit_accounting_26/ui/forms/calculation"
OUT_DIR = "src/profit_accounting_26/ui/generated"
PANELS = ["image_ai", "product_cost", "packaging", "logistics", "profit"]

_HERE = pathlib.Path(__file__).resolve().parent.parent
_VENV = _HERE / ".venv" / "Scripts"
UIC = str(_VENV / "pyside6-uic.exe") if (_VENV / "pyside6-uic.exe").exists() else "pyside6-uic"

# Qt 标准属性 — 保留，不删除，不注入
STD_PROPS = {
    "objectName", "geometry", "minimumSize", "maximumSize", "sizePolicy", "font",
    "text", "placeholderText", "readOnly", "enabled", "visible", "toolTip",
    "alignment", "orientation", "spacing", "leftMargin", "topMargin", "rightMargin",
    "bottomMargin", "horizontalSpacing", "verticalSpacing", "stretch",
    "buttonSymbols", "decimals", "minimum", "maximum", "singleStep", "value",
    "checked", "checkable", "autoExclusive", "windowTitle", "focusPolicy",
    "cursor", "acceptDrops", "wordWrap", "frameShape", "frameShadow",
    "autoFillBackground", "styleSheet", "locale", "textFormat", "echoMode",
    "currentIndex", "currentText", "editable", "columnCount", "rowCount",
    "textInteractionFlags", "sizeHint", "displayFormat", "inputMethodHints",
    "openExternalLinks", "tabChangesFocus", "tristate", "palette",
    "layoutDirection", "tabletTracking", "autoFormatting", "html",
    "tabChangesFocus", "documentTitle", "completionMode", "set",
    "frame", "midLineWidth", "lineWidth", "sizeIncrement", "baseSize",
    "toolTipDuration", "autoFillBackground",
}
REMOVED_LINES = {"setColumnMinimumWidth"}


# ---------------------------------------------------------------------------
# 1. 解析自定义属性
# ---------------------------------------------------------------------------

def _extract_custom_props(content: str) -> list[tuple[str, str, object]]:
    """返回 [(widget_name, prop_name, python_value), ...]。

    遍历 .ui 内容，按行追踪 widget context，收集非 STD_PROPS 的属性。
    """
    props: list[tuple[str, str, object]] = []
    widget_stack: list[str] = []
    in_prop = False
    prop_name = ""
    prop_type = ""
    prop_value = ""
    prop_depth = 0

    for line in content.split("\n"):
        stripped = line.strip()

        # Track widget open/close
        w_open = re.match(r'<widget class="[^"]*" name="(\w+)"', stripped)
        if w_open and not stripped.startswith("</"):
            widget_stack.append(w_open.group(1))

        if stripped == "</widget>" and widget_stack:
            widget_stack.pop()

        # Track property state
        if in_prop:
            if "<property" in stripped:
                prop_depth += 1
            if "</property>" in stripped:
                prop_depth -= 1
                if prop_depth <= 0:
                    if widget_stack and prop_name not in STD_PROPS:
                        pv = _coerce_value(prop_type, prop_value.strip())
                        props.append((widget_stack[-1], prop_name, pv))
                    in_prop = False
                    prop_name = ""
                    prop_value = ""
            else:
                # Collect inner value
                m = re.match(r"<(string|number|bool|enum)>(.*)</\1>", stripped)
                if m:
                    prop_type = m.group(1)
                    prop_value = m.group(2)
            continue

        pm = re.match(r'\s*<property name="(\w+)"', line)
        if pm:
            name = pm.group(1)
            if name not in STD_PROPS:
                in_prop = True
                prop_depth = 1
                prop_name = name
                prop_type = ""
                prop_value = ""
                # Check single-line: <property name="x"><type>val</type></property>
                m2 = re.match(r'.*<(string|number|bool)>(.*)</\1>', stripped)
                if m2:
                    prop_type = m2.group(1)
                    prop_value = m2.group(2)
                if "</property>" in stripped:
                    if widget_stack:
                        pv = _coerce_value(prop_type, prop_value.strip())
                        props.append((widget_stack[-1], prop_name, pv))
                    in_prop = False
                    prop_name = ""
    return props


def _coerce_value(typ: str, val: str) -> object:
    if typ == "bool":
        return val.lower() in ("true", "1")
    if typ == "number":
        try:
            return int(val)
        except ValueError:
            return float(val)
    if typ == "enum":
        return val
    # string / unknown
    return val


# ---------------------------------------------------------------------------
# 2. 清洗 .ui（移除自定义属性）
# ---------------------------------------------------------------------------

def clean_ui(content: str) -> str:
    """移除自定义属性，返回可供 pyside6-uic 编译的内容。"""
    lines = []
    in_custom = False
    depth = 0
    for line in content.split("\n"):
        stripped = line.strip()
        if in_custom:
            if "<property" in stripped:
                depth += 1
            if "</property>" in stripped:
                depth -= 1
                if depth <= 0:
                    in_custom = False
            continue
        pm = re.match(r'\s*<property name="(\w+)"', line)
        if pm and pm.group(1) not in STD_PROPS:
            in_custom = True
            depth = 1
            if "</property>" in stripped:
                in_custom = False
                depth = 0
            continue
        lines.append(line)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 3. 后处理生成文件：注入 setProperty 调用
# ---------------------------------------------------------------------------

def _inject_properties(gen_content: str, props: list[tuple[str, str, object]], root_name: str) -> str:
    """在 setupUi 末尾（pass 前）注入 setProperty() 调用。

    root_name: 面板根 widget 的 objectName——其属性使用参数名引用（非 self.xxx）。
    """
    if not props:
        return gen_content

    calls = ["        # --- restored dynamic properties ---"]
    for widget_name, prop_name, py_value in props:
        # 根 widget 的引用是参数名，不是 self.xxx
        ref = widget_name if widget_name == root_name else f"self.{widget_name}"
        if isinstance(py_value, bool):
            calls.append(f'        {ref}.setProperty("{prop_name}", {py_value})')
        elif isinstance(py_value, str):
            escaped = py_value.replace("\\", "\\\\").replace('"', '\\"')
            calls.append(f'        {ref}.setProperty("{prop_name}", "{escaped}")')
        else:
            calls.append(f'        {ref}.setProperty("{prop_name}", {py_value})')
    calls.append("")

    # 插入到 retranslateUi 定义之前（即 setupUi 末尾）
    lines = gen_content.split("\n")
    result_lines = []
    injected = False
    for i, line in enumerate(lines):
        if not injected and line.strip().startswith("def retranslateUi"):
            for call_line in calls:
                result_lines.append(call_line)
            injected = True
        result_lines.append(line)

    return "\n".join(result_lines)


def post_process(gen_content: str, props: list[tuple[str, str, object]], root_name: str) -> str:
    """后处理：移除问题行 + 注入属性。"""
    gen = "\n".join(
        line for line in gen_content.split("\n")
        if not any(bad in line for bad in REMOVED_LINES)
    )
    gen = _inject_properties(gen, props, root_name)
    return gen


# ---------------------------------------------------------------------------
# 4. 生成流程
# ---------------------------------------------------------------------------

def generate_panel(name: str, out_dir: str) -> str:
    """生成单个面板，返回输出文件路径。"""
    src = os.path.join(UI_DIR, f"{name}_panel.ui")
    tmp = os.path.join(out_dir, f"_{name}_clean.ui")
    out = os.path.join(out_dir, f"{name}_panel_view.py")

    with open(src, "r", encoding="utf-8") as f:
        original = f.read()

    # 收集自定义属性 + 获取根 widget 名
    props = _extract_custom_props(original)
    root_match = re.search(r'<widget class="[^"]*" name="(\w+)"', original)
    root_name = root_match.group(1) if root_match else ""

    # 清洗
    cleaned = clean_ui(original)
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(cleaned)

    # pyside6-uic
    result = subprocess.run([UIC, tmp, "-o", out], capture_output=True, text=True)
    os.remove(tmp)
    if result.returncode != 0:
        raise RuntimeError(f"uic failed for {name}: {result.stderr[:300]}")

    # 后处理
    with open(out, "r", encoding="utf-8") as f:
        gen = f.read()
    fixed = post_process(gen, props, root_name)
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(fixed)

    return out


def generate_all(out_dir: str = OUT_DIR) -> None:
    os.makedirs(out_dir, exist_ok=True)
    for name in PANELS:
        generate_panel(name, out_dir)
        print(f"  {name}_panel_view.py")


# ---------------------------------------------------------------------------
# 5. --check 模式
# ---------------------------------------------------------------------------

def _normalize_generated(content: str) -> str:
    """规范换行符，移除生成器版本注释中的时间戳。"""
    content = content.replace("\r\n", "\n").replace("\r", "\n")
    # 移除 "# Form generated from reading UI file" 注释行
    lines = []
    for line in content.split("\n"):
        if "Form generated from reading UI file" in line:
            continue
        if "Created by: Qt User Interface Compiler" in line:
            continue
        if line.startswith("##"):
            continue
        lines.append(line)
    return "\n".join(lines).strip() + "\n"


def check_consistency() -> bool:
    """--check: 在临时目录重新生成，比较是否一致。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        generate_all(tmpdir)
        ok = True
        for name in PANELS:
            actual = os.path.join(OUT_DIR, f"{name}_panel_view.py")
            regenerated = os.path.join(tmpdir, f"{name}_panel_view.py")
            with open(actual, "r", encoding="utf-8") as f:
                a = _normalize_generated(f.read())
            with open(regenerated, "r", encoding="utf-8") as f:
                b = _normalize_generated(f.read())
            if a != b:
                ok = False
                diff = list(difflib.unified_diff(
                    a.splitlines(keepends=True), b.splitlines(keepends=True),
                    fromfile=f"committed/{name}_panel_view.py",
                    tofile=f"regenerated/{name}_panel_view.py",
                ))
                print(f"  MISMATCH [{name}]:")
                for line in diff[:20]:
                    print(f"    {line.rstrip()}")
                print()
        if ok:
            print("  All generated files match .ui sources.")
        else:
            print("  ERROR: generated files out of sync. Run: python tools/generate_calc_panels.py")
        return ok


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--check":
        ok = check_consistency()
        raise SystemExit(0 if ok else 1)
    generate_all()
    print("Done.")


if __name__ == "__main__":
    main()
