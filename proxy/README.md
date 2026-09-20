# Translation proxy

Claude Code speaks Anthropic's Messages API. Local model servers speak the OpenAI API. This container is
LiteLLM between the two, plus one hook, `hoist_system.py`.

The hook exists because Claude Code sends its environment notes as a `system` message in the middle of the
conversation, and many open-model chat templates (Qwen's among them) raise an error for a system message that
is not first. The hook moves that text into the leading system prompt. It changes position, not content.

Environment: `LOCAL_MODEL_BASE` (for example `http://model:8080/v1`) and `LOCAL_MODEL_ID`
(`openai/<the model name your server reports>`). It works with llama.cpp, vLLM, LM Studio and Ollama.
