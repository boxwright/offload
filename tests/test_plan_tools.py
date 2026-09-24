"""Tests for the planner's tool set: `plan_tools` and the `tools` fallback in the paid worker.

`plan_tools` hands the planner the paid worker's tools in full mode, and the same list without
`Read` and `Bash(cat *)` in index mode (the planner is given a file tree instead of file contents).
The paid worker falls back to the config's `claude_tools` when no `tools` is passed.
"""
import dataclasses

from offload import config as config_module
from offload import workers
from offload.jobs import Job


# ---------------------------------------------------------------- plan_tools
def test_plan_tools_full_mode_returns_claude_tools(settings):
    """In full mode the planner gets exactly the paid worker's tools."""
    assert config_module.plan_tools(settings) == settings.claude_tools


def test_plan_tools_index_mode_strips_read_and_cat(settings):
    """In index mode the planner keeps every tool except Read and Bash(cat *)."""
    index = dataclasses.replace(settings, plan_reads="index")
    parts = config_module.plan_tools(index).split(",")
    assert "Read" not in parts
    assert "Bash(cat *)" not in parts
    # everything else from claude_tools is still there, in order
    kept = [t for t in settings.claude_tools.split(",") if t not in ("Read", "Bash(cat *)")]
    assert parts == kept
    # the tree is explored with Glob and Grep, not Read
    assert "Glob" in parts and "Grep" in parts


# ---------------------------------------------------------------- the fallback
def _capture_cmdline(monkeypatch):
    """Point workers.claude_cmdline at a recorder and stub out the sandbox and the token."""
    captured = {}

    def fake_cmdline(prompt, model, tools, max_turns, resume=None):
        captured["tools"] = tools
        return "claude -p"
    monkeypatch.setattr(workers, "claude_cmdline", fake_cmdline)
    monkeypatch.setattr(workers, "run_sandbox", lambda *args, **kwargs: ({"result": "ok"}, 0, "", 0.0))
    monkeypatch.setattr(workers, "claude_secret", lambda: {"CLAUDE_CODE_OAUTH_TOKEN": "token"})
    return captured


def test_call_claude_without_tools_falls_back_to_config(settings, job_factory, monkeypatch):
    """A _call_claude with no tools uses the config's claude_tools."""
    captured = _capture_cmdline(monkeypatch)
    workers._call_claude(Job(job_factory()), "prompt", "model", 5)
    assert captured["tools"] == settings.claude_tools


def test_call_claude_with_tools_uses_them(settings, job_factory, monkeypatch):
    """An explicit tools argument wins over the config's claude_tools."""
    captured = _capture_cmdline(monkeypatch)
    workers._call_claude(Job(job_factory()), "prompt", "model", 5, tools="Glob,Grep")
    assert captured["tools"] == "Glob,Grep"


def test_claude_forwards_its_tools_to_the_call(settings, job_factory, monkeypatch):
    """The public claude() passes its tools argument through to the underlying call."""
    captured = _capture_cmdline(monkeypatch)
    monkeypatch.setattr(workers, "budget_wait", lambda job, purpose: None)
    monkeypatch.setattr(workers, "ledger_add", lambda *args, **kwargs: None)
    workers.claude(Job(job_factory()), "prompt", "model", 5, "review", tools="Glob,Grep")
    assert captured["tools"] == "Glob,Grep"
