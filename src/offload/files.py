"""Small file helpers: every open is closed, JSON writes are atomic."""
import contextlib
import json
import os


def read_text(path):
    with open(path) as f:
        return f.read()


def write_text(path, text):
    with open(path, "w") as f:
        f.write(text)


def read_json(path):
    with open(path) as f:
        return json.load(f)


def write_json(path, obj):
    """Write through a temporary file, so a crash never leaves a half-written file behind."""
    tmp = f"{path}.tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f)
    os.replace(tmp, path)


def read_jsonl(path, strict=True):
    """Yield one record per line. A missing file yields nothing.

    With strict=False a line that is not valid JSON is skipped instead of raising.
    """
    if not os.path.exists(path):
        return
    with open(path) as f:
        for line in f:
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                if strict:
                    raise


def append_jsonl(path, record):
    with open(path, "a") as f:
        f.write(json.dumps(record) + "\n")


def remove_if_exists(path):
    with contextlib.suppress(FileNotFoundError):
        os.remove(path)
