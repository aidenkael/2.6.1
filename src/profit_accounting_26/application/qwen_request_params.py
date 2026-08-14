# -*- coding: utf-8 -*-
"""阿里云百炼 Qwen 系列请求参数 helper。

仅当 provider == "阿里云百炼" 且模型名以 "qwen" 开头时，附加关闭联网搜索
和关闭思考的参数。不限制用户选择任何模型，不建立白名单。

不支持关闭思考的型号只追加进 _QWEN_THINKING_ONLY_MODELS 排除集合；
不建立模型能力系统，不采用请求失败后自动重试。
"""
from __future__ import annotations

from typing import Any


# 不支持关闭思考的 Qwen 型号（仅思考/特殊型号）。
# 未来经真实 API 确认不支持 enable_thinking=false 的型号追加到此集合。
_QWEN_THINKING_ONLY_MODELS: frozenset[str] = frozenset({
    "qwen3.8-max-preview",
})

_PROVIDER_DASHSCOPE = "阿里云百炼"


def qwen_extra_body_params(provider: str, model: str) -> dict[str, Any]:
    """返回阿里云百炼 Qwen 系列模型的额外请求参数。

    - 阿里云百炼 + Qwen 系列：默认 enable_search=False；
      支持关闭思考的型号同时 enable_thinking=False。
    - 非阿里云百炼 / 非 Qwen 模型：返回空 dict，请求体保持不变。
    """
    if provider.strip() != _PROVIDER_DASHSCOPE:
        return {}
    m = model.strip()
    if not m.lower().startswith("qwen"):
        return {}
    params: dict[str, Any] = {"enable_search": False}
    # 不支持关闭思考的型号：不发送 enable_thinking 字段
    if m.lower() not in {x.lower() for x in _QWEN_THINKING_ONLY_MODELS}:
        params["enable_thinking"] = False
    return params
