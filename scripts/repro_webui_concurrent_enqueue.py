#!/usr/bin/env python3
"""
WebUIジョブキューの「ダウンロード中に2件目投入」再現スクリプト(tc-ops #440是正2)。

ユーザー実機テストで再現した「2件目追加したら1件目が消える」現象を、機械的・再現可能な形で
自動操作する。1件目投入(URL)直後、ダウンロード中とみられる短い待機の後に2件目を投入し、
サーバー側の診断ログ(`webui.py`/`core/webui_workflow.py`の`logger.info(...)`、token/item_id付き)
と突き合わせて原因を追跡するための道具。

前提: 別プロセスでStreamlit実サーバーを起動しておくこと
    uv run streamlit run webui.py --server.headless true --server.port 8501
実行にはシステムのPlaywright(chromium)が必要。本プロジェクトの依存関係(pyproject.toml)には
追加していない(`scripts/e2e_local.sh`と同じ「手動実行可能な検証ツール」という位置づけ)。

使い方:
    python3 scripts/repro_webui_concurrent_enqueue.py \\
        --url1 "https://www.youtube.com/watch?v=dQw4w9WgXcQ" \\
        --url2 "https://www.youtube.com/watch?v=dQw4w9WgXcQ" \\
        --gap-ms 500

このスクリプトは文字起こし完了(≒Google Driveアップロード)までは待たない。enqueue段階の
挙動(1件目が消えるか否か)を確認したら終了する。原因追跡はサーバー側の診断ログを目視/grepで
確認すること(このスクリプトはブラウザ操作のみ行う)。
"""

import argparse
import sys

from playwright.sync_api import sync_playwright


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server-url", default="http://localhost:8501")
    parser.add_argument("--url1", default="https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    parser.add_argument("--url2", default="https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    parser.add_argument(
        "--gap-ms",
        type=int,
        default=500,
        help="1件目投入から2件目投入までの待機ミリ秒(ダウンロード中を狙う)",
    )
    parser.add_argument(
        "--settle-ms",
        type=int,
        default=3000,
        help="2件目投入後、UI状態を観察するまでの待機ミリ秒",
    )
    args = parser.parse_args()

    def log(msg: str) -> None:
        print(f"[repro] {msg}", flush=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        page.goto(args.server_url)
        page.wait_for_selector("text=Transcribe Audio WebUI", timeout=30000)
        log("app loaded")

        url_input = page.get_by_label("YouTube / Google Drive URL")

        url_input.fill(args.url1)
        page.get_by_role("button", name="キューに追加").click()
        log(f"1件目投入 url={args.url1}")

        page.wait_for_timeout(args.gap_ms)

        url_input.fill(args.url2)
        page.get_by_role("button", name="キューに追加").click()
        log(f"2件目投入 url={args.url2} (1件目投入から{args.gap_ms}ms後)")

        page.wait_for_timeout(args.settle_ms)

        body_text = page.inner_text("body")
        relevant_lines = [
            l
            for l in body_text.splitlines()
            if l.strip() and ("待機件数" in l or "処理中" in l or "完了済み" in l or "[完了]" in l or "[失敗]" in l)
        ]
        log("UI状態(該当行): " + " | ".join(relevant_lines) if relevant_lines else "UI状態: 該当行なし")
        log("原因追跡はサーバー側の診断ログ(token/item_id)を確認すること。ブラウザは終了する。")

        browser.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
