# Calibration

Five small, test-scored coding tasks (`tasks/`), a runner, and a scorer. They answer one narrow question:
can a model do clean, well-specified coding with tools? They say nothing about vague specs or big codebases.

Run them against Claude, or against your local model through the proxy:

```bash
./run_claude.sh /tmp/cal-sonnet sonnet
ANTHROPIC_BASE_URL=http://127.0.0.1:4000 ANTHROPIC_AUTH_TOKEN=local ./run_claude.sh /tmp/cal-local local-model
```

`RESULTS.md` has our runs. Open a hardware report issue with yours.
