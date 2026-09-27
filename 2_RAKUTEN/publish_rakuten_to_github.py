#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import ssl
import subprocess
import sys
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

import certifi


BASE = Path(__file__).resolve().parent
DEFAULT_REPO = "ebnr321130921-pixel/finance-report"
DEFAULT_BRANCH = "main"
DEFAULT_REPO_DIR = "2_RAKUTEN"
DEFAULT_FILES = [
    "holdings_input.csv",
    "fund_master.json",
    "rakuten_update.py",
    "README.md",
    "publish_rakuten_to_github.py",
]
GENERATED_FILES = [
    "daily_records.json",
    "dashboard.html",
]
KEYCHAIN_SERVICE = "rakuten-github-publisher"
SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
EXCLUDED_DIRS = {".git", ".venv", ".logs", ".agents", ".codex", ".cache", ".pytest_cache", "__pycache__", "node_modules", "venv"}
EXCLUDED_FILES = {".DS_Store", ".rakuten-update.lock", "holdings_reconciliation.json", "holdings.private.json"}
REQUIRED_HOLDINGS_COLUMNS = [
    "product",
    "account",
    "units",
    "status",
    "planned_value",
    "change_date",
    "change_value",
    "Zero_date",
    "settlement_date",
    "start",
    "start_value",
]


class GitHubApi:
    def __init__(self, repo: str, token: str):
        self.repo = repo
        self.token = token

    def request(self, method: str, path: str, payload: dict | None = None) -> dict:
        body = None
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")

        req = Request(
            f"https://api.github.com/repos/{self.repo}{path}",
            data=body,
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "rakuten-local-publisher",
            },
        )
        try:
            with urlopen(req, timeout=30, context=SSL_CONTEXT) as res:
                raw = res.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise SystemExit(f"GitHub API error {exc.code}: {detail}") from exc

        return json.loads(raw) if raw else {}


def repo_path(repo_dir: str, local_name: str) -> str:
    return f"{repo_dir.strip('/')}/{local_name}"


def resolve_token(repo: str, interactive: bool = False) -> str:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        return token
    gh = shutil.which("gh")
    if gh:
        result = subprocess.run([gh, "auth", "token", "--hostname", "github.com"], capture_output=True, text=True)
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    if sys.platform == "darwin":
        command = ["/usr/bin/security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-a", repo, "-w"]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        if interactive and sys.stdin.isatty():
            print("\n初回のみ：GitHubのトークンをMacのキーチェーンに登録します。", flush=True)
            print(f"https://github.com/settings/personal-access-tokens/new\n対象: {repo}\nRepository permissions: Contents = Read and write", flush=True)
            print("作成したトークンを、この後のpassword欄へ貼り付けてください（入力は表示されません）。", flush=True)
            # security prompts directly: the token is never placed in argv or logs.
            subprocess.run(["/usr/bin/security", "add-generic-password", "-U", "-s", KEYCHAIN_SERVICE, "-a", repo, "-w"], check=True)
            result = subprocess.run(command, capture_output=True, text=True)
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
    raise SystemExit("GitHub認証がありません。起動用.commandから初回設定するか、GITHUB_TOKEN / GH_TOKENを設定してください。")


def validate_holdings() -> None:
    path = BASE / "holdings_input.csv"
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != REQUIRED_HOLDINGS_COLUMNS:
            raise SystemExit(
                "holdings_input.csv columns do not match the expected format:\n"
                f"expected: {REQUIRED_HOLDINGS_COLUMNS}\n"
                f"actual:   {reader.fieldnames}"
            )

        rows = list(reader)

    if not rows:
        raise SystemExit("holdings_input.csv has no data rows")

    for line_no, row in enumerate(rows, start=2):
        product = row.get("product", "").strip()
        status = row.get("status", "").strip()
        if not product:
            raise SystemExit(f"holdings_input.csv line {line_no}: product is empty")
        if status not in {"active", "planned", "watch"}:
            raise SystemExit(
                f"holdings_input.csv line {line_no}: unsupported status {status!r}"
            )


def collect_files(args: argparse.Namespace) -> list[str]:
    names = list(DEFAULT_FILES)
    if getattr(args, "folder", False):
        names = []
        for root, dirs, files in os.walk(BASE):
            dirs[:] = sorted(d for d in dirs if d not in EXCLUDED_DIRS and not (Path(root) / d).is_symlink())
            for name in sorted(files):
                path = Path(root) / name
                if (name.startswith(".env") or name in EXCLUDED_FILES or path.is_symlink()
                        or path.suffix.lower() in {".pyc", ".pyo", ".log", ".pem", ".key"}
                        or any(part in name.lower() for part in (".private.", "credential", "secret", "token"))):
                    continue
                names.append(path.relative_to(BASE).as_posix())
    if args.include_generated:
        names.extend(GENERATED_FILES)
    if args.files:
        names = args.files

    seen = set()
    result = []
    for name in names:
        clean = name.strip().lstrip("/")
        if clean in seen:
            continue
        seen.add(clean)
        path = BASE / clean
        if path.is_symlink() or not path.resolve().is_relative_to(BASE.resolve()):
            raise SystemExit(f"Publish target must be inside {BASE}: {clean}")
        if not path.is_file():
            raise SystemExit(f"Missing publish target: {path}")
        result.append(clean)
    return result


def create_commit(api: GitHubApi, args: argparse.Namespace, files: list[str]) -> str:
    branch = quote(args.branch, safe="/")
    ref = api.request("GET", f"/git/ref/heads/{branch}")
    parent_sha = ref["object"]["sha"]
    parent_commit = api.request("GET", f"/git/commits/{parent_sha}")
    base_tree = parent_commit["tree"]["sha"]
    remote_tree = api.request("GET", f"/git/trees/{base_tree}?recursive=1")
    if remote_tree.get("truncated"):
        raise SystemExit("GitHubのファイル一覧が大きすぎるため、安全に比較できません。")
    remote = {entry["path"]: entry for entry in remote_tree["tree"]}

    tree_entries = []
    for name in files:
        content = (BASE / name).read_bytes()
        mode = "100755" if name.endswith(".command") else "100644"
        digest = hashlib.sha1(f"blob {len(content)}\0".encode() + content).hexdigest()
        previous = remote.get(repo_path(args.repo_dir, name), {})
        if previous.get("sha") == digest and previous.get("mode") == mode:
            continue
        print(f"Uploading: {name}", flush=True)
        blob = api.request(
            "POST",
            "/git/blobs",
            {
                "content": base64.b64encode(content).decode("ascii"),
                "encoding": "base64",
            },
        )
        tree_entries.append(
            {
                "path": repo_path(args.repo_dir, name),
                "mode": mode,
                "type": "blob",
                "sha": blob["sha"],
            }
        )

    if not tree_entries:
        print("変更なし：GitHubはすでに同じ内容です。", flush=True)
        return parent_sha

    tree = api.request(
        "POST",
        "/git/trees",
        {
            "base_tree": base_tree,
            "tree": tree_entries,
        },
    )
    commit = api.request(
        "POST",
        "/git/commits",
        {
            "message": args.message,
            "tree": tree["sha"],
            "parents": [parent_sha],
        },
    )
    api.request(
        "PATCH",
        f"/git/refs/heads/{branch}",
        {
            "sha": commit["sha"],
            "force": False,
        },
    )
    return commit["sha"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Publish selected 2_RAKUTEN files to GitHub only when explicitly run."
    )
    parser.add_argument(
        "--push",
        action="store_true",
        help="Actually create a GitHub commit. Without this, only prints the target files.",
    )
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", DEFAULT_REPO))
    parser.add_argument("--branch", default=os.environ.get("GITHUB_BRANCH", DEFAULT_BRANCH))
    parser.add_argument("--repo-dir", default=DEFAULT_REPO_DIR)
    parser.add_argument("--folder", action="store_true", help="Upload the project folder, including generated output; excludes local-only files, secrets and caches.")
    parser.add_argument(
        "--message",
        default="Update Rakuten local holdings",
        help="Git commit message used when --push is set.",
    )
    parser.add_argument(
        "--include-generated",
        action="store_true",
        help="Also upload daily_records.json and dashboard.html. Normally leave this off.",
    )
    parser.add_argument(
        "--files",
        nargs="+",
        help="Override the default publish file list with explicit local filenames.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    validate_holdings()
    files = collect_files(args)

    print(f"Repository: {args.repo}")
    print(f"Branch:     {args.branch}")
    print("Files:")
    for name in files:
        print(f"  {name} -> {repo_path(args.repo_dir, name)}")

    if not args.push:
        print("\nDry run only. Add --push to publish these files to GitHub.")
        return

    token = resolve_token(args.repo)

    api = GitHubApi(args.repo, token)
    commit_sha = create_commit(api, args, files)
    print(f"\nPublished commit: {commit_sha}")


if __name__ == "__main__":
    main()
