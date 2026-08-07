#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import base64
import csv
import json
import os
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


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
            with urlopen(req, timeout=30) as res:
                raw = res.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise SystemExit(f"GitHub API error {exc.code}: {detail}") from exc

        return json.loads(raw) if raw else {}


def repo_path(repo_dir: str, local_name: str) -> str:
    return f"{repo_dir.strip('/')}/{local_name}"


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
        if not path.is_file():
            raise SystemExit(f"Missing publish target: {path}")
        result.append(clean)
    return result


def create_commit(api: GitHubApi, args: argparse.Namespace, files: list[str]) -> str:
    ref = api.request("GET", f"/git/ref/heads/{args.branch}")
    parent_sha = ref["object"]["sha"]
    parent_commit = api.request("GET", f"/git/commits/{parent_sha}")
    base_tree = parent_commit["tree"]["sha"]

    tree_entries = []
    for name in files:
        content = (BASE / name).read_bytes()
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
                "mode": "100644",
                "type": "blob",
                "sha": blob["sha"],
            }
        )

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
        f"/git/refs/heads/{args.branch}",
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

    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        raise SystemExit("Set GITHUB_TOKEN or GH_TOKEN before running with --push.")

    api = GitHubApi(args.repo, token)
    commit_sha = create_commit(api, args, files)
    print(f"\nPublished commit: {commit_sha}")


if __name__ == "__main__":
    main()
