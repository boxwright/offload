"""LiteLLM proxy hook: move system messages that appear mid-conversation into the leading system prompt.

Claude Code sends its environment block as a `system` role message after the first user message.
Many open-model chat templates (Qwen among them) raise an error for a system message that is not first.
This hook keeps the text and changes only its position. It runs before every request.
"""
from litellm.integrations.custom_logger import CustomLogger


def _text_blocks(content):
    if content is None:
        return []
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    return [b if isinstance(b, dict) else {"type": "text", "text": str(b)} for b in content]


class HoistSystem(CustomLogger):
    async def async_pre_call_hook(self, user_api_key_dict, cache, data, call_type):
        messages = data.get("messages") or []
        hoisted, kept = [], []
        for m in messages:
            (hoisted if m.get("role") == "system" else kept).append(m)
        if not hoisted:
            return data
        blocks = _text_blocks(data.get("system"))
        for m in hoisted:
            blocks.extend(_text_blocks(m.get("content")))
        data["system"] = blocks
        data["messages"] = kept
        return data


proxy_handler_instance = HoistSystem()
