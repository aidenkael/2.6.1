# -*- coding: utf-8 -*-
"""商品风险检测独立日志。

写入 ``<数据目录>/logs/product_risk/product_risk.log``。

约束：
- 自动创建 logs/product_risk/ 目录；
- 使用 RotatingFileHandler（maxBytes≈2MB，backupCount=3，UTF-8）；
- 只挂载在本模块 logger 上，不修改全局 root logger 行为（propagate=False）；
- configure() 幂等：重复调用不会重复注册 handler；
- 严禁写入 API Key / Authorization / 完整 Prompt / base64 图片。

调用方（TitleRiskScanService / ImageRiskScanService / 页面）只传入
非敏感字段；payload 仅记录字节数。
"""

from __future__ import annotations

import logging
import logging.handlers
import time
from pathlib import Path

_LOGGER_NAME = "profit_accounting_26.product_risk"
_logger = logging.getLogger(_LOGGER_NAME)
_logger.propagate = False  # 不冒泡到 root，保持全局 logger 行为不变
_logger.setLevel(logging.INFO)

MAX_BYTES = 2 * 1024 * 1024
BACKUP_COUNT = 3
LOG_RELATIVE_PATH = Path("logs") / "product_risk" / "product_risk.log"


def log_file_path(data_dir: str | Path | None) -> Path | None:
    """返回日志文件路径；data_dir 为空时返回 None。"""
    if not data_dir:
        return None
    return Path(data_dir) / LOG_RELATIVE_PATH


def configure(data_dir: str | Path | None) -> Path | None:
    """配置风险日志目录。

    幂等：同一路径不会重复注册 handler；换路径时替换旧 handler。
    返回日志文件路径，未配置时返回 None。
    """
    path = log_file_path(data_dir)
    if path is None:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    for handler in list(_logger.handlers):
        if (
            isinstance(handler, logging.handlers.RotatingFileHandler)
            and Path(handler.baseFilename).resolve() == path.resolve()
        ):
            return path
        _logger.removeHandler(handler)
        handler.close()
    handler = logging.handlers.RotatingFileHandler(
        path,
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    )
    handler.setLevel(logging.INFO)
    _logger.addHandler(handler)
    return path


def elapsed_ms(start: float) -> int:
    return int((time.monotonic() - start) * 1000)


# ----------------------------------------------------------------------
# 标题检测
# ----------------------------------------------------------------------


def title_scan_start(profile_name: str, provider: str, model: str, count: int) -> None:
    """标题检测开始（含 API Profile 名称 / provider / model / 商品数量）。"""
    _logger.info(
        "[标题检测] 开始 profile=%s provider=%s model=%s 商品数量=%d",
        profile_name,
        provider,
        model,
        count,
    )


def title_request_started(payload_bytes: int) -> None:
    """API 请求开始（仅记录 payload 字节数）。"""
    _logger.info("[标题检测] API请求开始 payload_bytes=%d", payload_bytes)


def title_request_finished(
    *,
    duration_ms: int,
    success: int,
    missing: int,
    status: str,
    timeout: bool = False,
    http_error: str = "",
) -> None:
    """API 请求结束：耗时 / 成功数 / 缺失非法数 / 最终状态 / 超时与 HTTP 摘要。"""
    _logger.info(
        "[标题检测] API请求结束 duration_ms=%d success=%d missing=%d status=%s"
        " timeout=%s http_error=%s",
        duration_ms,
        success,
        missing,
        status,
        timeout,
        http_error,
    )


def title_scan_cancelled() -> None:
    """用户取消标题检测。"""
    _logger.info("[标题检测] 用户取消")


def title_batch_started(batch_index: int, batch_size: int) -> None:
    """单批开始：批次编号 / 当前批数量。"""
    _logger.info("[标题检测] 批次%d开始 本批数量=%d", batch_index, batch_size)


def title_batch_finished(
    *,
    batch_index: int,
    duration_ms: int,
    success: int,
    failed: int,
    status: str,
    timeout: bool = False,
    http_error: str = "",
) -> None:
    """单批结束：耗时 / 成功失败数 / 状态 / 超时与 HTTP 摘要。"""
    _logger.info(
        "[标题检测] 批次%d结束 duration_ms=%d success=%d failed=%d status=%s"
        " timeout=%s http_error=%s",
        batch_index,
        duration_ms,
        success,
        failed,
        status,
        timeout,
        http_error,
    )


def title_batch_diagnostics(
    *,
    batch_index: int,
    finish_reason: str,
    content_chars: int,
    results_is_list: bool,
    raw_results_count: int,
    valid_count: int,
    missing_id_count: int,
    invalid_risk_count: int,
    unknown_id_count: int,
    duplicate_id_count: int,
) -> None:
    """单批返回结构诊断（API HTTP 成功后记录，用于排查 success=0 missing=N）。

    只记录统计字段，不记录完整 AI 返回内容 / 标题 / Prompt。
    """
    _logger.info(
        "[标题检测] 批次%d诊断 finish_reason=%s content_chars=%d results_is_list=%s"
        " raw_results_count=%d valid_count=%d missing_id_count=%d invalid_risk_count=%d"
        " unknown_id_count=%d duplicate_id_count=%d",
        batch_index,
        finish_reason,
        content_chars,
        results_is_list,
        raw_results_count,
        valid_count,
        missing_id_count,
        invalid_risk_count,
        unknown_id_count,
        duplicate_id_count,
    )


def title_scan_finished(
    *,
    total: int,
    batches: int,
    checked: int,
    failed: int,
    status: str,
    timeout: bool = False,
    http_error: str = "",
) -> None:
    """标题检测最终状态（batches 为实际执行批次数）。"""
    _logger.info(
        "[标题检测] 结束 总商品数=%d 批次数=%d checked=%d failed=%d status=%s"
        " timeout=%s http_error=%s",
        total,
        batches,
        checked,
        failed,
        status,
        timeout,
        http_error,
    )


# ----------------------------------------------------------------------
# 图片检测
# ----------------------------------------------------------------------


def image_scan_start(total: int) -> None:
    """图片检测开始（总商品数）。"""
    _logger.info("[图片检测] 开始 总商品数=%d", total)


def image_batch_started(batch_index: int, batch_size: int) -> None:
    """单批开始：批次编号 / 当前批数量。"""
    _logger.info("[图片检测] 批次%d开始 本批数量=%d", batch_index, batch_size)


def image_batch_finished(
    *,
    batch_index: int,
    download_ms: int,
    download_failed: int,
    payload_bytes: int,
    api_ms: int,
    success: int,
    failed: int,
    status: str,
    timeout: bool = False,
    http_error: str = "",
) -> None:
    """单批结束：下载耗时 / 下载失败数 / payload 字节数 / API 耗时 / 成功失败数。"""
    _logger.info(
        "[图片检测] 批次%d结束 download_ms=%d download_failed=%d payload_bytes=%d"
        " api_ms=%d success=%d failed=%d status=%s timeout=%s http_error=%s",
        batch_index,
        download_ms,
        download_failed,
        payload_bytes,
        api_ms,
        success,
        failed,
        status,
        timeout,
        http_error,
    )


def image_scan_finished(
    *,
    total: int,
    batches: int,
    checked: int,
    failed: int,
    status: str,
    timeout: bool = False,
    http_error: str = "",
) -> None:
    """图片检测最终状态。"""
    _logger.info(
        "[图片检测] 结束 总商品数=%d 批次数=%d checked=%d failed=%d status=%s"
        " timeout=%s http_error=%s",
        total,
        batches,
        checked,
        failed,
        status,
        timeout,
        http_error,
    )


def image_scan_cancelled() -> None:
    """用户取消图片检测。"""
    _logger.info("[图片检测] 用户取消")
