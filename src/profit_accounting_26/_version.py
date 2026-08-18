"""软件版本唯一来源（Single Source of Truth）。

pyproject.toml 通过 ``attr:`` 读取此值；所有 Python 代码通过
``from profit_accounting_26._version import __version__`` 获取版本号。

修改软件版本只需修改此文件，然后重新构建/安装即可。

注意：UI 产品显示版本（如 "UU护航 3.0.1"）在 main_window.ui 中维护，
与包版本（本文件）有意分离——包版本面向 pip/构建系统，UI 版本面向用户。
"""

__version__ = "3.0.1"
