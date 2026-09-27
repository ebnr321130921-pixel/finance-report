#!/usr/bin/env python3
"""One-click publication of the local Rakuten folder to GitHub."""
import argparse
from datetime import datetime
import fcntl
import os
import subprocess
import sys

import publish_rakuten_to_github as publisher


def run(dry_run=False, refresh=False):
    base = publisher.BASE
    with (base / ".rakuten-update.lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("別の楽天更新が実行中です。その画面で完了を待ってください。")
        args = argparse.Namespace(
            repo=publisher.DEFAULT_REPO, branch=publisher.DEFAULT_BRANCH,
            repo_dir=publisher.DEFAULT_REPO_DIR, folder=True,
            include_generated=True, files=None,
            message=f"Update Rakuten folder ({datetime.now():%Y-%m-%d %H:%M})",
        )
        publisher.validate_holdings()
        print(f"更新先: https://github.com/{args.repo}/tree/{args.branch}/{args.repo_dir}", flush=True)
        if dry_run:
            print("動作確認：価格取得・GitHub送信・認証登録は行いません。")
            for name in publisher.collect_files(args):
                print(f"  {name}")
            return
        print("[1/2] GitHub認証を確認", flush=True)
        token = publisher.resolve_token(args.repo, interactive=True)
        api = publisher.GitHubApi(args.repo, token)
        api.request("GET", f"/git/ref/heads/{args.branch}")
        if refresh:
            print("最新価格を取得してダッシュボードを再生成（数分かかります）", flush=True)
            env = os.environ.copy()
            env.pop("RAKUTEN_HOLDINGS_JSON", None)
            subprocess.run([sys.executable, "-u", str(base / "rakuten_update.py")],
                           cwd=base, env=env, check=True, timeout=1800)
        publisher.validate_holdings()
        print("[2/2] 楽天フォルダをGitHubへ反映", flush=True)
        sha = publisher.create_commit(api, args, publisher.collect_files(args))
        print(f"\n完了しました。\nhttps://github.com/{args.repo}/commit/{sha}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--refresh", action="store_true", help="Optionally fetch prices and rebuild before uploading.")
    args = parser.parse_args()
    try:
        run(args.dry_run, args.refresh)
    except KeyboardInterrupt:
        raise SystemExit("中断しました。")
    except (OSError, subprocess.SubprocessError) as exc:
        raise SystemExit(f"更新に失敗しました：{exc}\nネット接続と認証設定を確認し、もう一度実行してください。") from exc


if __name__ == "__main__":
    main()
