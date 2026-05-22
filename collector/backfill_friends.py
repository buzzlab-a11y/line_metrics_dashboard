"""友だち数カーブの過去復元（バックフィル）.

UTAGE API は過去の時系列を返さないが、読者一人ひとりの created_at は取得できる。
これを日付集計して「その日までに何人登録したか（累積）」を再構築し、
line_daily_snapshots に過去日のスナップショットとして投入する。

復元できるのは friends（累積友だち数）と、その差分から得られる新規登録数のみ。
ブロック数は過去の状態が取れないため 0（active=readers_total）として記録する。
当日分は collect_line_metrics.py の実データを優先するため、本日より前の日付のみ書き込む。

実行:
    cd apps/line_metrics_dashboard/collector
    python backfill_friends.py            # 全アカウントを復元してSupabaseへ
    python backfill_friends.py --dry-run  # 集計結果を表示するだけ
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from collections import Counter
from datetime import date, datetime

from utage_client import UtageClient, load_groups_config
import funnel
import collect_line_metrics as clm


def parse_created_date(value) -> date | None:
    """created_at 文字列から date を取り出す（複数フォーマットに耐性）."""
    if not value:
        return None
    s = str(value)
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    try:
        return datetime.fromisoformat(s).date()
    except ValueError:
        return None


def build_daily_rows(account_id: str, readers: list[dict], today: date) -> list[dict]:
    """読者の created_at を集計し、変化のあった日ごとに累積スナップショット行を作る."""
    per_day = Counter()
    for r in readers:
        d = parse_created_date(r.get("created_at"))
        if d and d < today:  # 当日は実データを優先するため除外
            per_day[d] += 1

    rows: list[dict] = []
    cumulative = 0
    for d in sorted(per_day):
        cumulative += per_day[d]
        rows.append(
            {
                "account_id": account_id,
                "snapshot_date": d.isoformat(),
                "readers_total": cumulative,
                "blocked_count": 0,        # 過去のブロック状態は取得不可
                "active_count": cumulative,
            }
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="友だち数カーブの過去復元")
    parser.add_argument("--dry-run", action="store_true", help="Supabaseへ書かず集計表示")
    args = parser.parse_args()

    today = date.today()
    try:
        client = UtageClient()
    except RuntimeError as e:
        print(f"設定エラー: {e}", file=sys.stderr)
        return 2

    account_ids = load_groups_config()["groups"]
    all_ids = [aid for g in account_ids.values() for aid in g.get("account_ids", [])]

    all_rows: list[dict] = []
    for aid in all_ids:
        print(f"▶ {aid} の readers を取得中...", flush=True)
        readers = funnel.fetch_all_readers(client, aid)
        rows = build_daily_rows(aid, readers, today)
        if rows:
            print(f"  {len(readers)}人 → 過去 {len(rows)} 日分のスナップショット "
                  f"({rows[0]['snapshot_date']} 〜 {rows[-1]['snapshot_date']}, 現在累積 {rows[-1]['readers_total']})")
        else:
            print(f"  {len(readers)}人 → 復元対象なし（created_atが当日のみ/取得不可）")
        all_rows.extend(rows)

    print(f"\n合計 {len(all_rows)} 行")

    if args.dry_run:
        print("=== DRY RUN（Supabaseへは書込みません）===")
        for r in all_rows[:20]:
            print(" ", r)
        return 0

    print("=== Supabase へ upsert ===")
    # collect_line_metrics の upsert を再利用（line_daily_snapshots のみ投入）
    from supabase import create_client
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL / SUPABASE_SERVICE_KEY が未設定です。")
    sb = create_client(url, key)
    for i in range(0, len(all_rows), 500):
        sb.table("line_daily_snapshots").upsert(all_rows[i : i + 500]).execute()
    print(f"✅ line_daily_snapshots: {len(all_rows)} 行 upsert（過去分）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
