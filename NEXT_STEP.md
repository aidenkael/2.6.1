# 下一步

在用户 Windows 电脑的 `E:\Profit-Accounting-2.6` 中，用 Python 3.11 执行：

```powershell
.\verify_release_candidate.bat
.\run_app.bat
```

完成 GUI 人工验收后，再执行：

```powershell
.\build_windows.bat
```

构建成功后，检查 `release\` 下的文件夹版和 ZIP，并执行真实 AI API、拖拽/粘贴、Edge插件、保存记录和重启后历史恢复测试。
