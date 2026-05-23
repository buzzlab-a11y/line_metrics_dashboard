"""LINE数字計測ダッシュボード — 日次収集スクリプト.

UTAGE REST API から以下を収集し、Supabase に当日スナップショットとして upsert する:
  1. 友だち数・ブロック数   → line_daily_snapshots
  2. 流入経路別（ラベル別）  → line_label_snapshots
  3. 配信パフォーマンス      → line_message_stats
  4. 講座生ファネル成約      → line_funnel_snapshots
  + アカウントマスタ        → line_accounts（毎回 upsert）

アカウントの分類（self / student）は groups.yaml + line_categories.yaml に従う。

実行:
    cd apps/line_metrics_dashboard/collector
    python collect_line_metrics.py            # 本番（Supabase へ書込）
    python collect_line_metrics.py --dry-run  # Supabase へ書かず JSON を標準出力
    python collect_line_metrics.py --skip-blocked  # 重いブロック数集計をスキップ

環境変数:
    UTAGE_API_KEY        UTAGE REST API キー（collector/.env でも可）
    SUPABASE_URL         Supabase プロジェクト URL
    SUPABASE_SERVICE_KEY service_role キー（書込用）
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

from utage_client import (
    PROJECT_ROOT,
    UtageAPIError,
    UtageClient,
    load_groups_config,
)
import funnel

CATEGORIES_PATH = PROJECT_ROOT / "line_categories.yaml"
READER_PER_PAGE = 100


# ---------- 設定読み込み ----------


def load_categories() -> tuple[dict[str, str], dict[str, str]]:
    """line_categories.yaml を読み (group→category, account_id→category上書き) を返す.

    categories:        グループ単位の分類
    account_overrides: 個別アカウントの上書き（グループ分類より優先）
    """
    group_cats: dict[str, str] = {}
    overrides: dict[str, str] = {}
    if not CATEGORIES_PATH.exists():
        return group_cats, overrides
    block: str | None = None
    for raw in CATEGORIES_PATH.read_text(encoding="utf-8").splitlines():
        line = re.sub(r"\s+#.*$", "", raw).rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if re.match(r"^categories:\s*$", line):
            block = "categories"
            continue
        if re.match(r"^account_overrides:\s*$", line):
            block = "overrides"
            continue
        m = re.match(r"^\s+([A-Za-z0-9_]+):\s*(\w+)\s*$", line)
        if not m:
            continue
        if block == "categories":
            group_cats[m.group(1)] = m.group(2)
        elif block == "overrides":
            overrides[m.group(1)] = m.group(2)
    return group_cats, overrides


def build_account_index(
    groups: dict, categories: dict[str, str], overrides: dict[str, str] | None = None
) -> list[dict]:
    """各アカウントに group_name / category / sort_order を付与したリストを返す.

    category は account_overrides（個別指定）> グループ分類 > 'self' の優先順。
    """
    overrides = overrides or {}
    accounts: list[dict] = []
    order = 0
    for group_name, g in groups.items():
        for account_id in g.get("account_ids", []):
            category = overrides.get(account_id, categories.get(group_name, "self"))
            accounts.append(
                {
                    "account_id": account_id,
                    "group_name": group_name,
                    "category": category,
                    "sort_order": order,
                }
            )
            order += 1
    return accounts


def fetch_account_names(client: UtageClient) -> dict[str, str]:
    """GET /accounts で account_id -> name のマッピングを取得."""
    names: dict[str, str] = {}
    try:
        for page in range(1, 50):
            r = client.get("/accounts", params={"per_page": READER_PER_PAGE, "page": page})
            data = r.get("data", []) or []
            for a in data:
                if a.get("id"):
                    names[a["id"]] = a.get("name") or a["id"]
            if len(data) < READER_PER_PAGE:
                break
    except UtageAPIError as e:
        print(f"⚠️ /accounts 取得エラー（名前は account_id で代替）: {e}", file=sys.stderr)
    return names


# ---------- 指標収集 ----------


def collect_friends(client: UtageClient, account_id: str, skip_blocked: bool) -> dict:
    """友だち数(meta.total)・ブロック数・流入経路(message_tracking_name別人数)を返す.

    ブロック数と流入経路は全 readers のページ取得が必要なため同じプルで両方算出する。
    skip_blocked 時はこのプルを省略（ブロック数・流入経路は空）。
    """
    readers_total = 0
    try:
        r = client.get(f"/accounts/{account_id}/readers", params={"per_page": 1})
        readers_total = r.get("meta", {}).get("total", 0) or 0
    except UtageAPIError as e:
        print(f"  ⚠️ readers total error ({account_id}): {e}", file=sys.stderr)

    blocked_count = 0
    inflow: dict[str, set] = {}
    if not skip_blocked and readers_total > 0:
        all_readers = funnel.fetch_all_readers(client, account_id)
        blocked_count = sum(1 for r in all_readers if r.get("is_blocked"))
        # 流入経路: message_tracking_name 別に common_reader_id で名寄せ
        for rd in all_readers:
            crid = rd.get("common_reader_id")
            if not crid:
                continue
            name = (rd.get("message_tracking_name") or "").strip() or "直接/不明"
            inflow.setdefault(name, set()).add(crid)

    active_count = max(readers_total - blocked_count, 0)
    return {
        "readers_total": readers_total,
        "blocked_count": blocked_count,
        "active_count": active_count,
        "inflow": {name: len(ids) for name, ids in inflow.items()},
    }


def collect_labels(client: UtageClient, account_id: str, snapshot_date: str) -> list[dict]:
    """ラベル別登録者数（line_label_snapshots 用レコード）を返す."""
    out: list[dict] = []
    try:
        r = client.get(f"/accounts/{account_id}/labels", params={"per_page": 200})
    except UtageAPIError as e:
        print(f"  ⚠️ labels error ({account_id}): {e}", file=sys.stderr)
        return out
    for lab in r.get("data", []) or []:
        if not lab.get("id"):
            continue
        out.append(
            {
                "account_id": account_id,
                "snapshot_date": snapshot_date,
                "label_id": lab["id"],
                "label_name": lab.get("name") or "",
                "subscriber_count": lab.get("subscriber_count") or 0,
            }
        )
    return out


def collect_message_stats(client: UtageClient, account_id: str, snapshot_date: str) -> list[dict]:
    """シナリオ→メッセージ→stats を辿り、配信パフォーマンスレコードを返す."""
    out: list[dict] = []
    try:
        scenarios = client.get(
            f"/accounts/{account_id}/scenarios", params={"per_page": 200}
        ).get("data", []) or []
    except UtageAPIError as e:
        print(f"  ⚠️ scenarios error ({account_id}): {e}", file=sys.stderr)
        return out

    for sc in scenarios:
        sid = sc.get("id")
        if not sid:
            continue
        scenario_title = sc.get("title") or ""
        try:
            messages = client.get(
                f"/accounts/{account_id}/scenarios/{sid}/messages",
                params={"per_page": 200},
            ).get("data", []) or []
        except UtageAPIError:
            continue
        for msg in messages:
            mid = msg.get("id")
            if not mid:
                continue
            try:
                stats = client.get(
                    f"/accounts/{account_id}/scenarios/{sid}/messages/{mid}/stats"
                ) or {}
            except UtageAPIError:
                continue
            out.append(
                {
                    "account_id": account_id,
                    "snapshot_date": snapshot_date,
                    "message_id": mid,
                    "scenario_id": sid,
                    "scenario_title": scenario_title,
                    "message_title": msg.get("title") or "",
                    "channel": stats.get("channel") or msg.get("channel") or "",
                    "send_count": stats.get("send_count") or 0,
                    "click_count": stats.get("click_count") or 0,
                    "click_rate": stats.get("click_rate") or 0,
                }
            )
    return out


# ---------- Supabase 投入 ----------


def upsert_to_supabase(payload: dict) -> None:
    """各テーブルへ upsert。supabase-py を遅延 import（dry-run 時は不要）."""
    from supabase import create_client

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL / SUPABASE_SERVICE_KEY が未設定です。")

    sb = create_client(url, key)

    def _upsert(table: str, rows: list[dict]):
        if not rows:
            return
        # 大量行は分割して送信
        for i in range(0, len(rows), 500):
            sb.table(table).upsert(rows[i : i + 500]).execute()
        print(f"  ✅ {table}: {len(rows)} 行 upsert")

    _upsert("line_accounts", payload["line_accounts"])
    _upsert("line_daily_snapshots", payload["line_daily_snapshots"])
    _upsert("line_label_snapshots", payload["line_label_snapshots"])
    _upsert("line_message_stats", payload["line_message_stats"])
    _upsert("line_funnel_snapshots", payload["line_funnel_snapshots"])
    _upsert("line_inflow_snapshots", payload["line_inflow_snapshots"])


# ---------- main ----------


def main() -> int:
    parser = argparse.ArgumentParser(description="LINE数字計測 日次収集")
    parser.add_argument("--dry-run", action="store_true", help="Supabaseへ書かずJSON出力")
    parser.add_argument("--skip-blocked", action="store_true", help="重いブロック数集計をスキップ")
    parser.add_argument("--skip-messages", action="store_true", help="配信統計収集をスキップ")
    args = parser.parse_args()

    snapshot_date = date.today().isoformat()

    try:
        client = UtageClient()
    except RuntimeError as e:
        print(f"設定エラー: {e}", file=sys.stderr)
        return 2

    groups = load_groups_config()["groups"]
    categories, overrides = load_categories()
    accounts = build_account_index(groups, categories, overrides)
    names = fetch_account_names(client)

    self_n = sum(1 for a in accounts if a["category"] == "self")
    student_n = sum(1 for a in accounts if a["category"] == "student")
    print(f"対象アカウント: {len(accounts)} 件（self={self_n} / student={student_n}）\n")

    line_accounts: list[dict] = []
    daily: list[dict] = []
    label_rows: list[dict] = []
    message_rows: list[dict] = []
    inflow_rows: list[dict] = []

    for a in accounts:
        aid = a["account_id"]
        name = names.get(aid, aid)
        print(f"▶ {name} ({aid}) [{a['category']}]", flush=True)

        line_accounts.append(
            {
                "account_id": aid,
                "name": name,
                "category": a["category"],
                "group_name": a["group_name"],
                "sort_order": a["sort_order"],
            }
        )

        friends = collect_friends(client, aid, args.skip_blocked)
        daily.append(
            {
                "account_id": aid,
                "snapshot_date": snapshot_date,
                "readers_total": friends["readers_total"],
                "blocked_count": friends["blocked_count"],
                "active_count": friends["active_count"],
            }
        )
        for tracking_name, cnt in friends["inflow"].items():
            inflow_rows.append(
                {
                    "account_id": aid,
                    "snapshot_date": snapshot_date,
                    "tracking_name": tracking_name,
                    "count": cnt,
                }
            )
        print(f"  友だち {friends['readers_total']} / ブロック {friends['blocked_count']} / 流入経路 {len(friends['inflow'])}種")

        label_rows.extend(collect_labels(client, aid, snapshot_date))

        if not args.skip_messages:
            stats = collect_message_stats(client, aid, snapshot_date)
            message_rows.extend(stats)
            print(f"  ラベル / 配信メッセージ {len(stats)} 件")

    # 講座生ファネル（kouzasei.yaml ベース・共通インフラを1回だけ集計）
    print("\n=== 講座生ファネル集計 ===")
    funnel_config = funnel.load_config()
    funnel_rows = funnel.compute_funnel_records(client, funnel_config, snapshot_date)

    payload = {
        "snapshot_date": snapshot_date,
        "line_accounts": line_accounts,
        "line_daily_snapshots": daily,
        "line_label_snapshots": label_rows,
        "line_message_stats": message_rows,
        "line_funnel_snapshots": funnel_rows,
        "line_inflow_snapshots": inflow_rows,
    }

    if args.dry_run:
        print("\n=== DRY RUN（Supabaseへは書込みません） ===")
        json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
        print()
        return 0

    print("\n=== Supabase へ upsert ===")
    upsert_to_supabase(payload)
    print("✅ 完了")
    return 0


if __name__ == "__main__":
    sys.exit(main())
