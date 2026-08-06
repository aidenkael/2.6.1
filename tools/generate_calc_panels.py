"""从 forms/calculation/*.ui 生成 Python UI 类到 ui/generated/。

用法:
    python tools/generate_calc_panels.py

生成文件不手动编辑；CI 会检查生成文件与 .ui 一致。
"""
import re, os, subprocess, sys, pathlib

UI_DIR = "src/profit_accounting_26/ui/forms/calculation"
OUT_DIR = "src/profit_accounting_26/ui/generated"

# 查找 pyside6-uic（优先用 venv）
_HERE = pathlib.Path(__file__).resolve().parent.parent
_VENV = _HERE / ".venv" / "Scripts"
UIC = str(_VENV / "pyside6-uic.exe") if (_VENV / "pyside6-uic.exe").exists() else "pyside6-uic"

# Qt 标准属性 — 保留；其他自定义属性在生成前移除
KEEP_PROPERTIES = {
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
    "openExternalLinks", "tabChangesFocus", "tristate",
}

REMOVED_LINES = {"setColumnMinimumWidth"}


def clean_ui(content: str) -> str:
    """移除自定义动态属性。"""
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
        m = re.match(r'\s*<property name="(\w+)"', line)
        if m and m.group(1) not in KEEP_PROPERTIES:
            in_custom = True
            depth = 1
            if "</property>" in stripped:
                in_custom = False
                depth = 0
            continue
        lines.append(line)
    return "\n".join(lines)


def fix_generated(content: str) -> str:
    """后处理 pyside6-uic 输出。"""
    return "\n".join(
        line for line in content.split("\n")
        if not any(bad in line for bad in REMOVED_LINES)
    )


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    panels = ["image_ai", "product_cost", "packaging", "logistics", "profit"]
    for name in panels:
        src = os.path.join(UI_DIR, f"{name}_panel.ui")
        tmp = os.path.join(UI_DIR, f"_{name}_clean.ui")
        out = os.path.join(OUT_DIR, f"{name}_panel_view.py")

        with open(src, "r", encoding="utf-8") as f:
            content = f.read()

        cleaned = clean_ui(content)
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            f.write(cleaned)

        result = subprocess.run(
            [UIC, tmp, "-o", out], capture_output=True, text=True
        )
        os.remove(tmp)

        if result.returncode != 0:
            print(f"ERROR [{name}]: {result.stderr[:300]}")
            return 1

        # Post-process
        with open(out, "r", encoding="utf-8") as f:
            gen = f.read()
        with open(out, "w", encoding="utf-8", newline="\n") as f:
            f.write(fix_generated(gen))

        print(f"  {name}_panel_view.py")

    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
