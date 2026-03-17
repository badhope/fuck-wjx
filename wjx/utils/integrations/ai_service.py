# -*- coding: utf-8 -*-
"""AI 服务模块 - 支持多种 AI API 调用"""
from typing import Optional, Dict, Any, Iterable
from urllib.parse import urlsplit, urlunsplit
import wjx.network.http_client as http_client

# AI 服务提供商配置
# 注意: recommended_models 仅作为 UI 快捷选择建议,用户可以自由输入任意模型名
AI_PROVIDERS = {
    "deepseek": {
        "label": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "recommended_models": ["deepseek-chat", "deepseek-reasoner"],
        "default_model": "deepseek-chat",
    },
    "qwen": {
        "label": "通义千问",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "recommended_models": ["qwen-max", "qwen-plus", "qwen-turbo", "qwen-long", "qwen-flash"],
        "default_model": "qwen-turbo",
    },
    "siliconflow": {
        "label": "硅基流动",
        "base_url": "https://api.siliconflow.cn/v1",
        "recommended_models": ["deepseek-ai/DeepSeek-V3.2", "Qwen/Qwen3-VL-8B-Instruct", "PaddlePaddle/PaddleOCR-VL-1.5"],
        "default_model": "deepseek-ai/DeepSeek-V3.2",
    },
    "volces": {
        "label": "火山引擎",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "recommended_models": ["doubao-seed-1-8-251228", "glm-4-7-251222", "doubao-seed-1-6-251015", "doubao-seed-1-6-lite-251015", "doubao-seed-1-6-flash-250828", "doubao-seed-1-6-250615"],
        "default_model": "doubao-seed-1-8-251228",
    },
    "custom": {
        "label": "自定义 (OpenAI 兼容)",
        "base_url": "",
        "recommended_models": [],
        "default_model": "",
    },
}

CUSTOM_API_PROTOCOLS = {
    "auto": {
        "label": "自动识别（推荐）",
        "description": "自动识别完整端点；只填 /v1 时自动尝试兼容协议",
    },
    "chat_completions": {
        "label": "Chat Completions",
        "description": "兼容 /chat/completions 协议",
    },
    "responses": {
        "label": "Responses",
        "description": "兼容 /responses 协议",
    },
}

DEFAULT_SYSTEM_PROMPT = "你现在不是AI助手，而是一名有实际使用经验但不专业的普通用户。请按照“填写问卷/填空题”的方式作答，而不是进行解释或对话。回答规则：1. 只给出答案本身，不要解释原因，不要分析，不要教学 2. 以个人体验和模糊印象为主，可以不确定、可以用“大概、感觉、差不多”等表达 3. 回答尽量简短，避免长句 4. 不要使用专业术语或严谨表述 5. 如果不确定，可以直接说“不太清楚/没太注意” 严格禁止：- 不要像AI助手一样分点说明 - 不要补充背景知识 - 不要解释题目 - 不要自称“作为AI” 如果你的回答开始变得专业、详细或像在解释，请立即改回普通用户的随意回答风格。"

_DEFAULT_AI_SETTINGS: Dict[str, Any] = {
    "enabled": False,
    "provider": "deepseek",
    "api_key": "",
    "base_url": "",
    "api_protocol": "auto",
    "model": "",
    "system_prompt": DEFAULT_SYSTEM_PROMPT,
}
_RUNTIME_AI_SETTINGS: Optional[Dict[str, Any]] = None

_CHAT_COMPLETIONS_SUFFIX = "/chat/completions"
_RESPONSES_SUFFIX = "/responses"
_LEGACY_COMPLETIONS_SUFFIX = "/completions"


def _ensure_runtime_settings() -> Dict[str, Any]:
    global _RUNTIME_AI_SETTINGS
    if _RUNTIME_AI_SETTINGS is None:
        _RUNTIME_AI_SETTINGS = dict(_DEFAULT_AI_SETTINGS)
    return _RUNTIME_AI_SETTINGS


def get_ai_settings() -> Dict[str, Any]:
    """获取 AI 配置"""
    return dict(_ensure_runtime_settings())


def save_ai_settings(
    enabled: Optional[bool] = None,
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    api_protocol: Optional[str] = None,
    model: Optional[str] = None,
    system_prompt: Optional[str] = None,
):
    """保存 AI 配置"""
    settings = _ensure_runtime_settings()
    if enabled is not None:
        settings["enabled"] = bool(enabled)
    if provider is not None:
        settings["provider"] = str(provider)
    if api_key is not None:
        settings["api_key"] = str(api_key)
    if base_url is not None:
        settings["base_url"] = str(base_url)
    if api_protocol is not None:
        settings["api_protocol"] = _normalize_custom_api_protocol(api_protocol)
    if model is not None:
        settings["model"] = str(model)
    if system_prompt is not None:
        settings["system_prompt"] = str(system_prompt)


def _normalize_custom_api_protocol(value: Any) -> str:
    protocol = str(value or "auto").strip().lower()
    if protocol in CUSTOM_API_PROTOCOLS:
        return protocol
    return "auto"


def _normalize_endpoint_url(raw_url: str) -> str:
    return str(raw_url or "").strip().rstrip("/")


def _path_endswith(path: str, suffix: str) -> bool:
    normalized_path = (path or "").rstrip("/").lower()
    return normalized_path.endswith(suffix)


def _replace_path_suffix(parts, suffix: str) -> str:
    normalized_path = (parts.path or "").rstrip("/")
    return urlunsplit((parts.scheme, parts.netloc, normalized_path + suffix, parts.query, parts.fragment))


def _resolve_custom_endpoint(base_url: str, api_protocol: str) -> tuple[str, str, bool]:
    normalized_base_url = _normalize_endpoint_url(base_url)
    if not normalized_base_url:
        raise RuntimeError("自定义模式需要配置 Base URL")

    parts = urlsplit(normalized_base_url)
    path = parts.path or ""

    if _path_endswith(path, _CHAT_COMPLETIONS_SUFFIX):
        return "chat_completions", normalized_base_url, True
    if _path_endswith(path, _RESPONSES_SUFFIX):
        return "responses", normalized_base_url, True
    if _path_endswith(path, _LEGACY_COMPLETIONS_SUFFIX):
        raise RuntimeError("暂不支持旧版 /completions 协议，请改用 /chat/completions 或 /responses")

    normalized_protocol = _normalize_custom_api_protocol(api_protocol)
    if normalized_protocol == "responses":
        return "responses", _replace_path_suffix(parts, _RESPONSES_SUFFIX), False
    return "chat_completions", _replace_path_suffix(parts, _CHAT_COMPLETIONS_SUFFIX), False


def _is_endpoint_mismatch_error(exc: Exception) -> bool:
    message = str(exc or "").lower()
    mismatch_markers = (
        "404",
        "405",
        "410",
        "not found",
        "no route",
        "no handler",
        "unsupported path",
        "invalid url",
        "method not allowed",
    )
    return any(marker in message for marker in mismatch_markers)


def _extract_text_parts(content: Any) -> Iterable[str]:
    if isinstance(content, str):
        text = content.strip()
        if text:
            yield text
        return

    if not isinstance(content, list):
        return

    for item in content:
        if isinstance(item, str):
            text = item.strip()
            if text:
                yield text
            continue
        if not isinstance(item, dict):
            continue
        item_type = str(item.get("type") or "").strip().lower()
        text = str(item.get("text") or item.get("content") or "").strip()
        if item_type in {"text", "output_text", "input_text"} and text:
            yield text


def _extract_chat_completion_text(data: Dict[str, Any]) -> str:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError("API 返回中缺少 choices")

    message = choices[0].get("message", {}) if isinstance(choices[0], dict) else {}
    content = message.get("content")
    parts = list(_extract_text_parts(content))
    if parts:
        return "\n".join(parts).strip()
    raise RuntimeError("API 返回内容为空")


def _extract_responses_text(data: Dict[str, Any]) -> str:
    top_level_text = str(data.get("output_text") or "").strip()
    if top_level_text:
        return top_level_text

    output = data.get("output")
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, dict):
                continue
            parts = list(_extract_text_parts(item.get("content")))
            if parts:
                return "\n".join(parts).strip()

    raise RuntimeError("Responses API 返回内容为空")


def _call_chat_completions(
    url: str,
    api_key: str,
    model: str,
    question: str,
    system_prompt: str,
    timeout: int = 30,
) -> str:
    """调用 Chat Completions 兼容接口。"""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"请简短回答这个问卷问题：{question}"},
        ],
        "max_tokens": 200,
        "temperature": 0.7,
    }
    try:
        resp = http_client.post(url, headers=headers, json=payload, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        return _extract_chat_completion_text(data)
    except Exception as e:
        raise RuntimeError(f"API 调用失败: {e}")


def _call_responses_api(
    url: str,
    api_key: str,
    model: str,
    question: str,
    system_prompt: str,
    timeout: int = 30,
) -> str:
    """调用 Responses 兼容接口。"""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    payload = {
        "model": model,
        "instructions": system_prompt,
        "input": f"请简短回答这个问卷问题：{question}",
        "max_output_tokens": 200,
        "temperature": 0.7,
    }
    try:
        resp = http_client.post(url, headers=headers, json=payload, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        return _extract_responses_text(data)
    except Exception as e:
        raise RuntimeError(f"API 调用失败: {e}")


def generate_answer(question_title: str) -> str:
    """根据问题标题生成答案"""
    config = get_ai_settings()
    if not config["enabled"]:
        raise RuntimeError("AI 功能未启用")
    if not config["api_key"]:
        raise RuntimeError("请先配置 API Key")

    provider = config["provider"]
    api_key = config["api_key"]
    system_prompt = config["system_prompt"] or DEFAULT_SYSTEM_PROMPT

    # 确定 base_url 和 model
    if provider == "custom":
        base_url = config["base_url"]
        api_protocol = _normalize_custom_api_protocol(config.get("api_protocol"))
        model = config["model"]
        if not base_url:
            raise RuntimeError("自定义模式需要配置 Base URL")
        if not model:
            raise RuntimeError("自定义模式需要配置模型名称")
        resolved_protocol, request_url, has_explicit_endpoint = _resolve_custom_endpoint(base_url, api_protocol)
        if resolved_protocol == "responses":
            return _call_responses_api(request_url, api_key, model, question_title, system_prompt)
        try:
            return _call_chat_completions(request_url, api_key, model, question_title, system_prompt)
        except Exception as exc:
            if has_explicit_endpoint or api_protocol != "auto" or not _is_endpoint_mismatch_error(exc):
                raise
            fallback_url = f"{_normalize_endpoint_url(base_url)}{_RESPONSES_SUFFIX}"
            return _call_responses_api(fallback_url, api_key, model, question_title, system_prompt)
    else:
        provider_config = AI_PROVIDERS.get(provider)
        if not provider_config:
            raise RuntimeError(f"不支持的 AI 服务提供商: {provider}")
        base_url = provider_config["base_url"]
        model = config["model"] or provider_config["default_model"]
        if provider == "siliconflow" and not model:
            raise RuntimeError("硅基流动需要先配置模型名称")

    request_url = f"{_normalize_endpoint_url(base_url)}{_CHAT_COMPLETIONS_SUFFIX}"
    return _call_chat_completions(request_url, api_key, model, question_title, system_prompt)


def test_connection() -> str:
    """测试 AI 连接"""
    try:
        result = generate_answer("这是一个测试问题，请回复'连接成功'")
        return f"连接成功！AI 回复: {result[:50]}..."
    except Exception as e:
        return f"连接失败: {e}"

