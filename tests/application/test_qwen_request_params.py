"""qwen_extra_body_params helper 测试。

覆盖：
- 阿里云百炼 + qwen3.7-flash -> enable_thinking=False, enable_search=False
- 阿里云百炼 + qwen3.7-flash-2026-07-15 -> 同上
- 阿里云百炼 + qwen3.8-max -> 同上
- 阿里云百炼 + qwen3.8-max-preview -> 只有 enable_search=False
- 阿里云百炼 + qwen-plus -> 同上（其他 Qwen 系列也生效）
- DeepSeek/GLM/OpenAI/自定义 -> 空 dict
- 阿里云百炼 + 非 Qwen 模型 -> 空 dict
"""
from __future__ import annotations

from profit_accounting_26.application.qwen_request_params import (
    _QWEN_THINKING_ONLY_MODELS,
    qwen_extra_body_params,
)


class TestQwenExtraBodyParams:
    """测试千问请求参数 helper。"""

    def test_dashscope_qwen37_flash(self):
        result = qwen_extra_body_params("阿里云百炼", "qwen3.7-flash")
        assert result == {"enable_thinking": False, "enable_search": False}

    def test_dashscope_qwen37_flash_snapshot(self):
        result = qwen_extra_body_params("阿里云百炼", "qwen3.7-flash-2026-07-15")
        assert result == {"enable_thinking": False, "enable_search": False}

    def test_dashscope_qwen38_max(self):
        result = qwen_extra_body_params("阿里云百炼", "qwen3.8-max")
        assert result == {"enable_thinking": False, "enable_search": False}

    def test_dashscope_qwen38_max_preview_no_thinking(self):
        """仅思考型号：不发送 enable_thinking，但发送 enable_search。"""
        result = qwen_extra_body_params("阿里云百炼", "qwen3.8-max-preview")
        assert "enable_thinking" not in result
        assert result.get("enable_search") is False

    def test_dashscope_qwen_plus(self):
        """其他 Qwen 系列也生效。"""
        result = qwen_extra_body_params("阿里云百炼", "qwen-plus")
        assert result == {"enable_thinking": False, "enable_search": False}

    def test_deepseek_empty(self):
        assert qwen_extra_body_params("DeepSeek", "deepseek-chat") == {}

    def test_glm_empty(self):
        assert qwen_extra_body_params("GLM", "glm-4v") == {}

    def test_openai_empty(self):
        assert qwen_extra_body_params("OpenAI", "gpt-4o") == {}

    def test_custom_empty(self):
        assert qwen_extra_body_params("自定义", "my-model") == {}

    def test_dashscope_non_qwen_empty(self):
        """阿里云百炼 + 非 Qwen 模型 -> 空 dict。"""
        assert qwen_extra_body_params("阿里云百炼", "deepseek-chat") == {}

    def test_dashscope_non_qwen_model(self):
        """阿里云百炼 + 非 Qwen 系列模型 -> 空 dict。"""
        assert qwen_extra_body_params("阿里云百炼", "gemini-pro") == {}

    def test_thinking_only_models_in_exclusion_set(self):
        """确认排除集合中包含 qwen3.8-max-preview。"""
        assert "qwen3.8-max-preview" in _QWEN_THINKING_ONLY_MODELS

    def test_whitespace_stripped(self):
        """前后空格被正确处理。"""
        result = qwen_extra_body_params("  阿里云百炼  ", "  qwen3.7-flash  ")
        assert result == {"enable_thinking": False, "enable_search": False}

    def test_case_insensitive_qwen_prefix(self):
        """Qwen 前缀不区分大小写。"""
        result = qwen_extra_body_params("阿里云百炼", "Qwen3.7-Flash")
        assert result == {"enable_thinking": False, "enable_search": False}

    def test_empty_provider_empty(self):
        assert qwen_extra_body_params("", "qwen3.7-flash") == {}

    def test_empty_model_empty(self):
        assert qwen_extra_body_params("阿里云百炼", "") == {}
