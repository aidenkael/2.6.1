# TEST_REPORT

- generated_at_utc: `2026-07-28T13:19:01.818624+00:00`
- repository: `aidenkael/Profit-Accounting-2.6`
- branch: `migration/r2-baseline`
- workflow_base_commit: `efb311039ff13dfb38fc2545885eebc335fc732b`
- R2 source_tag: `profit-legacy-freeze-20260728-r2`
- R2 source_commit: `d0c07d374c9ee61926de9cd3e01b8c35260c8e5c`
- tracked_file_count_before_report_commit: `203`
- clean_clone_verification: `passed`

## Pytest

```text
....................                                                     [100%]
20 passed in 1.12s
```

目标：`0 failed`、`0 collection errors`。PySide6 已安装时执行离屏窗口烟测；未安装时只允许该环境测试跳过并必须在 pytest 摘要中可见。

## Sensitive scan

```text
Sensitive scan passed: 0 findings
```

## Exclusions

未提交 `.venv`、缓存、构建产物、真实数据库、真实用户图片、Token、Cookie、API Key、浏览器 Profile、旧压缩包和 R2 外三份校准数据。
