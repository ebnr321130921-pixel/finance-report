"""Relaunch common entry points with a Python that has project dependencies."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import subprocess
import sys


BASE = Path(__file__).resolve().parent


def ensure_runtime(modules: tuple[str, ...]) -> None:
    missing = [name for name in modules if importlib.util.find_spec(name) is None]
    if not missing:
        return

    if os.environ.get("US_INDEX_RUNTIME_RELAUNCHED") == "1":
        raise SystemExit(
            "必要なPythonライブラリがありません: " + ", ".join(missing)
            + "\nUS指数を更新.command を実行して初回セットアップしてください。"
        )

    home = Path.home()
    candidates = [
        BASE / ".venv/bin/python",
        home / ".pyenv/versions/3.10.6/bin/python3",
        home / ".pyenv/versions/3.14.4/bin/python3",
        Path("/opt/homebrew/bin/python3"),
    ]
    check = "import " + ", ".join(modules)

    for candidate in candidates:
        if not candidate.is_file() or candidate.resolve() == Path(sys.executable).resolve():
            continue
        result = subprocess.run(
            [str(candidate), "-c", check],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if result.returncode == 0:
            print(
                f"[INFO] {sys.executable} に依存ライブラリがないため "
                f"{candidate} で再起動します。",
                flush=True,
            )
            env = os.environ.copy()
            env["US_INDEX_RUNTIME_RELAUNCHED"] = "1"
            os.execve(str(candidate), [str(candidate), *sys.argv], env)

    raise SystemExit(
        "必要なPythonライブラリがありません: " + ", ".join(missing)
        + "\nFinderから US指数を更新.command を実行するか、次を実行してください:"
        + "\n/usr/local/bin/python3 -m venv .venv"
        + "\n.venv/bin/python -m pip install -r requirements.txt"
    )
