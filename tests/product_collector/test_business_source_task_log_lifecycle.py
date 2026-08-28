"""采集器任务日志的数据目录生命周期回归。

契约（与 bf442e5 同一规则）：
- 采集日志目录配置在旧数据目录内（<数据目录>/product_collector），
  location.json 切换到新目录且旧目录被删除后，任务日志写入不得重建旧目录，
  也不得让采集崩溃（走既有"日志失败不影响采集结果"降级）；
- 数据目录有效（当前权威目录）时，任务日志照常写入。
"""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

import pytest

from profit_accounting_26.product_collector.collector_core.business_source import (
    CollectionReport,
    _write_task_log,
)
from profit_accounting_26.shared import (
    ApplicationPaths,
    activate_data_dir_lifecycle,
    deactivate_data_dir_lifecycle,
)


def _report() -> CollectionReport:
    return CollectionReport(products=[], status="success", keyword="测试", target_count=5)


@pytest.fixture
def location_json(tmp_path, monkeypatch):
    config = tmp_path / "home" / "location.json"
    monkeypatch.setattr(
        ApplicationPaths,
        "location_config_path",
        classmethod(lambda _cls: config),
    )
    return config


@pytest.fixture
def production_lifecycle(location_json):
    activate_data_dir_lifecycle()
    yield
    deactivate_data_dir_lifecycle()


def test_task_log_does_not_recreate_abandoned_data_dir(tmp_path, location_json, production_lifecycle):
    old_dir = tmp_path / "old_data"
    log_dir = old_dir / "product_collector"
    log_dir.mkdir(parents=True)  # 配置的采集日志目录位于旧数据目录内

    # location.json 切换到新目录，随后用户删除旧目录
    ApplicationPaths.save_data_dir(tmp_path / "new_data")
    shutil.rmtree(old_dir)

    # 任务日志尝试写入：不得抛错（采集不受影响）、不得重建旧目录
    _write_task_log(log_dir, _report(), datetime.now(), "")

    assert not old_dir.exists()


def test_task_log_still_writes_in_valid_current_data_dir(tmp_path, location_json, production_lifecycle):
    data_dir = tmp_path / "new_data"
    log_dir = data_dir / "product_collector"
    log_dir.mkdir(parents=True)

    # location.json 指向该有效数据目录（正常启动后的常态）
    ApplicationPaths.save_data_dir(data_dir)

    _write_task_log(log_dir, _report(), datetime.now(), "")

    logs = list(log_dir.glob("collect_*.log"))
    assert len(logs) == 1
    content = logs[0].read_text(encoding="utf-8")
    assert "keyword: 测试" in content
    assert "status: success" in content
