# -*- coding: utf-8 -*-
"""商品风险检测独立日志测试。

覆盖 R 项：
- 16. 风险日志写到正确数据目录
- 17. 风险日志不含 API Key / Authorization / base64
- 18. 日志 handler 不重复
"""

from __future__ import annotations

import logging
import logging.handlers
import shutil
import tempfile
import unittest
from pathlib import Path

from profit_accounting_26.product_collector import product_risk_log as prl


class TestProductRiskLog(unittest.TestCase):
    """风险日志：路径、轮转、幂等与敏感信息防护。

    Windows 下 RotatingFileHandler 会持有日志文件句柄，因此临时目录用
    mkdtemp 创建，并在 tearDown 中先关闭 handler 再删除目录，避免文件锁。
    """

    def setUp(self):
        for handler in list(prl._logger.handlers):
            prl._logger.removeHandler(handler)
            handler.close()
        self._tmp = tempfile.mkdtemp(prefix="pa26_risklog_")

    def tearDown(self):
        for handler in list(prl._logger.handlers):
            prl._logger.removeHandler(handler)
            handler.close()
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_log_written_to_correct_data_dir(self):
        """configure 后日志写到 <data_dir>/logs/product_risk/product_risk.log。"""
        path = prl.configure(self._tmp)
        self.assertIsNotNone(path)
        self.assertEqual(
            path,
            Path(self._tmp) / "logs" / "product_risk" / "product_risk.log",
        )
        self.assertTrue(path.parent.is_dir())
        # 触发一条日志，文件应真实存在
        prl.title_scan_start("VISUAL_AI", "qwen", "qwen-vl-max", 3)
        self.assertTrue(path.exists())
        content = path.read_text(encoding="utf-8")
        self.assertIn("标题检测", content)

    def test_configure_is_idempotent(self):
        """同一路径重复 configure 不重复注册 handler。"""
        prl.configure(self._tmp)
        first = list(prl._logger.handlers)
        prl.configure(self._tmp)
        second = list(prl._logger.handlers)
        self.assertEqual(len(second), 1)
        self.assertIs(first[0], second[0])

    def test_configure_switches_path_replaces_handler(self):
        """换路径时替换旧 handler，不叠加。"""
        tmp2 = tempfile.mkdtemp(prefix="pa26_risklog2_")
        try:
            prl.configure(self._tmp)
            prl.configure(tmp2)
            handlers = list(prl._logger.handlers)
            self.assertEqual(len(handlers), 1)
            self.assertTrue(
                isinstance(handlers[0], logging.handlers.RotatingFileHandler)
            )
            self.assertIn("pa26_risklog2_", handlers[0].baseFilename)
        finally:
            shutil.rmtree(tmp2, ignore_errors=True)

    def test_rotating_handler_limits(self):
        """RotatingFileHandler：约 2MB 上限 + 3 个备份 + UTF-8。"""
        prl.configure(self._tmp)
        handlers = list(prl._logger.handlers)
        self.assertEqual(len(handlers), 1)
        handler = handlers[0]
        self.assertEqual(handler.maxBytes, 2 * 1024 * 1024)
        self.assertEqual(handler.backupCount, 3)
        self.assertEqual(handler.encoding, "utf-8")

    def test_log_content_has_required_fields(self):
        """标题/图片检测各阶段必要字段写入日志。"""
        path = prl.configure(self._tmp)
        prl.title_scan_start("VISUAL_AI", "qwen", "qwen-vl-max", 10)
        prl.title_request_started(2048)
        prl.title_request_finished(
            duration_ms=1234, success=9, missing=1, status="ok",
            timeout=False, http_error="",
        )
        prl.title_batch_started(1, 20)
        prl.title_batch_finished(
            batch_index=1, duration_ms=1500, success=20, failed=0,
            status="完成", timeout=False, http_error="",
        )
        prl.title_scan_finished(
            total=90, batches=5, checked=90, failed=0, status="完成",
        )
        prl.image_scan_start(10)
        prl.image_batch_started(1, 10)
        prl.image_batch_finished(
            batch_index=1, download_ms=800, download_failed=1,
            payload_bytes=4096, api_ms=6000, success=9, failed=1,
            status="ok", timeout=False, http_error="",
        )
        prl.image_scan_finished(
            total=10, batches=1, checked=9, failed=1, status="ok",
        )
        content = path.read_text(encoding="utf-8")
        self.assertIn("[标题检测] 开始 profile=VISUAL_AI", content)
        self.assertIn("provider=qwen", content)
        self.assertIn("model=qwen-vl-max", content)
        self.assertIn("payload_bytes=2048", content)
        self.assertIn("duration_ms=1234", content)
        self.assertIn("missing=1", content)
        self.assertIn("[标题检测] 批次1开始 本批数量=20", content)
        self.assertIn("批次1结束 duration_ms=1500 success=20 failed=0 status=完成", content)
        self.assertIn("结束 总商品数=90 批次数=5 checked=90 failed=0 status=完成", content)
        self.assertIn("[图片检测] 批次1开始 本批数量=10", content)
        self.assertIn("download_ms=800", content)
        self.assertIn("download_failed=1", content)
        self.assertIn("api_ms=6000", content)
        self.assertIn("结束 总商品数=10 批次数=1", content)

    def test_log_excludes_sensitive_fields(self):
        """日志内容不得包含 API Key / Authorization / base64 等敏感信息。"""
        path = prl.configure(self._tmp)
        prl.title_scan_start("VISUAL_AI", "qwen", "qwen-vl-max", 2)
        prl.title_request_started(1024)
        prl.title_request_finished(
            duration_ms=500, success=2, missing=0, status="ok",
        )
        prl.image_scan_start(2)
        prl.image_batch_started(1, 2)
        prl.image_batch_finished(
            batch_index=1, download_ms=100, download_failed=0,
            payload_bytes=2048, api_ms=900, success=2, failed=0,
            status="ok",
        )
        content = path.read_text(encoding="utf-8").lower()
        for forbidden in ("api_key", "authorization", "bearer ", "base64"):
            self.assertNotIn(forbidden, content)

    def test_public_helpers_receive_no_sensitive_payload(self):
        """公共日志钩子不接收完整 Prompt / base64 / 密钥文件内容。"""
        import inspect

        for fn in (
            prl.title_request_started,
            prl.title_request_finished,
            prl.title_batch_started,
            prl.title_batch_finished,
            prl.title_scan_finished,
            prl.image_batch_finished,
            prl.image_scan_finished,
        ):
            sig = inspect.signature(fn)
            params = set(sig.parameters)
            for forbidden in ("api_key", "authorization", "prompt", "image_b64", "payload"):
                self.assertNotIn(forbidden, params, f"{fn.__name__} 不应接收 {forbidden}")


if __name__ == "__main__":
    unittest.main()
