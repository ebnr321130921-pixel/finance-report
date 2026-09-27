#!/usr/bin/env python3
"""Mirror this US Index folder to its existing GitHub repository directory."""

from __future__ import annotations

import argparse
import base64
from datetime import datetime
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
DEFAULT_REPO_DIR = "3_US_Index"
ROOT_MAPPED_FILES = {
    "requirements.txt": "github_root/requirements.txt",
    ".github/workflows/daily_update.yml": "github_root/daily_update.yml",
}
KEYCHAIN_SERVICE = "us-index-github-publisher"
EXCLUDED_DIRS = {
    ".git", ".venv", ".logs", ".agents", ".codex", ".cache",
    ".pytest_cache", "__pycache__", "node_modules", "venv",
}
EXCLUDED_FILES = {".DS_Store", ".us-index-publish.lock"}
SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())


class GitHubApi:
    def __init__(self, repo: str, token: str):
        self.repo = repo
        self.token = token

    def request(self, method: str, path: str, payload: dict | None = None) -> dict:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        request = Request(
            f"https://api.github.com/repos/{self.repo}{path}",
            data=body,
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "us-index-local-publisher",
            },
        )
        try:
            with urlopen(request, timeout=30, context=SSL_CONTEXT) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            accepted = exc.headers.get("X-Accepted-GitHub-Permissions", "")
            permission_hint = (
                f"\nGitHub要求権限: {accepted}" if accepted else ""
            )
            raise SystemExit(
                f"GitHub API error {exc.code}: {detail}{permission_hint}\n"
                "Fine-grained tokenにはRepository permissionsの "
                "Contents = Read and write と Workflows = Read and writeが必要です。"
            ) from exc
        return json.loads(raw) if raw else {}


def collect_files() -> list[str]:
    result = []
    for root, dirs, files in os.walk(BASE):
        dirs[:] = sorted(
            name for name in dirs
            if name not in EXCLUDED_DIRS and not (Path(root) / name).is_symlink()
        )
        for name in sorted(files):
            path = Path(root) / name
            lower = name.lower()
            if (
                name in EXCLUDED_FILES
                or name.startswith(".env")
                or path.is_symlink()
                or path.suffix.lower() in {".pyc", ".pyo", ".log", ".pem", ".key"}
                or ".legacy_pre_walk_forward." in lower
                or any(word in lower for word in (".private.", "credential", "secret", "token"))
            ):
                continue
            result.append(path.relative_to(BASE).as_posix())
    return result


def keychain_token(service: str, repo: str) -> str:
    command = [
        "/usr/bin/security", "find-generic-password",
        "-s", service, "-a", repo, "-w",
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else ""


def resolve_token(repo: str) -> str:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        return token

    gh = shutil.which("gh")
    if gh:
        result = subprocess.run(
            [gh, "auth", "token", "--hostname", "github.com"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()

    if sys.platform == "darwin":
        # This publisher also updates .github/workflows.  Do not silently reuse
        # the older Rakuten token because it commonly has Contents permission
        # only and fails after uploading blobs.
        token = keychain_token(KEYCHAIN_SERVICE, repo)
        if token:
            return token

        if sys.stdin.isatty():
            print("\n初回のみ：GitHubトークンをMacのキーチェーンへ登録します。")
            print("https://github.com/settings/personal-access-tokens/new")
            print(f"対象: {repo}")
            print("Repository permissions: Contents = Read and write")
            print("Repository permissions: Workflows = Read and write")
            print("作成したトークンをpassword欄へ貼り付けてください。入力は表示されません。")
            subprocess.run(
                [
                    "/usr/bin/security", "add-generic-password", "-U",
                    "-s", KEYCHAIN_SERVICE, "-a", repo, "-w",
                ],
                check=True,
            )
            token = keychain_token(KEYCHAIN_SERVICE, repo)
            if token:
                return token

    raise SystemExit(
        "GitHub認証がありません。GITHUB_TOKEN / GH_TOKEN、GitHub CLI、"
        "または起動時のキーチェーン登録を利用してください。"
    )


def remote_path(local_name: str) -> str:
    return f"{DEFAULT_REPO_DIR}/{local_name}"


def publish(api: GitHubApi, files: list[str]) -> str:
    branch = quote(DEFAULT_BRANCH, safe="/")
    ref = api.request("GET", f"/git/ref/heads/{branch}")
    parent_sha = ref["object"]["sha"]
    parent = api.request("GET", f"/git/commits/{parent_sha}")
    base_tree = parent["tree"]["sha"]
    tree = api.request("GET", f"/git/trees/{base_tree}?recursive=1")
    if tree.get("truncated"):
        raise SystemExit("GitHubのファイル一覧が大きすぎるため安全に同期できません。")

    remote = {entry["path"]: entry for entry in tree.get("tree", [])}
    desired = {remote_path(name) for name in files}
    entries = []

    publish_items = [(remote_path(name), BASE / name, name) for name in files]
    publish_items.extend(
        (remote_name, BASE / local_name, local_name)
        for remote_name, local_name in ROOT_MAPPED_FILES.items()
    )

    for path, local_path, display_name in publish_items:
        content = local_path.read_bytes()
        mode = "100755" if display_name.endswith(".command") else "100644"
        digest = hashlib.sha1(
            f"blob {len(content)}\0".encode() + content
        ).hexdigest()
        previous = remote.get(path, {})
        if previous.get("sha") == digest and previous.get("mode") == mode:
            continue
        print(f"更新: {path}", flush=True)
        blob = api.request(
            "POST",
            "/git/blobs",
            {
                "content": base64.b64encode(content).decode("ascii"),
                "encoding": "base64",
            },
        )
        entries.append(
            {"path": path, "mode": mode, "type": "blob", "sha": blob["sha"]}
        )

    prefix = DEFAULT_REPO_DIR + "/"
    for path, item in sorted(remote.items()):
        if (
            path.startswith(prefix)
            and item.get("type") == "blob"
            and path not in desired
        ):
            print(f"削除: {path}", flush=True)
            entries.append(
                {"path": path, "mode": item.get("mode", "100644"),
                 "type": "blob", "sha": None}
            )

    if not entries:
        print("変更なし：GitHubはすでに同じ内容です。")
        return parent_sha

    new_tree = api.request(
        "POST", "/git/trees", {"base_tree": base_tree, "tree": entries}
    )
    commit = api.request(
        "POST",
        "/git/commits",
        {
            "message": f"Update US Index ({datetime.now():%Y-%m-%d %H:%M})",
            "tree": new_tree["sha"],
            "parents": [parent_sha],
        },
    )
    api.request(
        "PATCH",
        f"/git/refs/heads/{branch}",
        {"sha": commit["sha"], "force": False},
    )
    return commit["sha"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--refresh", action="store_true",
        help="Update market data and Viewer before publishing.",
    )
    args = parser.parse_args()
    files = collect_files()

    print(f"更新先: https://github.com/{DEFAULT_REPO}/tree/{DEFAULT_BRANCH}/{DEFAULT_REPO_DIR}")
    if args.dry_run:
        print("\n送信対象:")
        for name in files:
            print(f"  {name}")
        print("\nルート更新:")
        for remote_name, local_name in ROOT_MAPPED_FILES.items():
            print(f"  {local_name} -> {remote_name}")
        print("\nGitHub側だけに残るキャッシュ等は本番同期時に削除されます。")
        return

    if args.refresh:
        subprocess.run(
            [sys.executable, "-u", str(BASE / "run_all.py")],
            cwd=BASE,
            check=True,
            timeout=3600,
        )

    token = resolve_token(DEFAULT_REPO)
    api = GitHubApi(DEFAULT_REPO, token)
    api.request("GET", f"/git/ref/heads/{DEFAULT_BRANCH}")
    sha = publish(api, files)
    print(f"\nGitHub更新完了:\nhttps://github.com/{DEFAULT_REPO}/commit/{sha}")


if __name__ == "__main__":
    main()
