"""集計完了後に Discord へ日次レポートを送る.

self(自社)アカウント合計の「当日の友だち追加数」「今月の累計追加数」を
グロス新規(各 reader の created_at ベース)で算出し、Discord webhook へ送信する。
ブロック・退会で減らない「その日/その月に新しく登録した人数」を見る。
集計が失敗した時はエラー通知を送る(collect_line_metrics.py から呼ばれる)。

単体実行:
    cd apps/line_metrics_dashboard/collector
    python discord_report.py --test        # ダミー数値で1通(API/DB不要・webhook疎通確認)
    python discord_report.py --send         # 実集計して送信
    python discord_report.py --error-test   # エラーembedの見た目確認

環境変数:
    DISCORD_WEBHOOK_URL  通知先 webhook
    UTAGE_API_KEY        UTAGE REST API キー(--send 時)
    SUPABASE_URL / SUPABASE_SERVICE_KEY  self/tracked 判定の読込(--send 時)
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import date, datetime, timezone

import requests
from dotenv import load_dotenv

from utage_client import PROJECT_ROOT, UtageClient
import funnel

# 単体実行(--test/--send)でも collector/.env を読む（本番は UtageClient 生成時に読まれる）
_ENV_PATH = PROJECT_ROOT / ".env"
if _ENV_PATH.exists():
    load_dotenv(_ENV_PATH)


def parse_created_date(value) -> date | None:
    """created_at 文字列から date を取り出す（複数フォーマット耐性）."""
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


# LINE専用チャンネルを優先し、無ければ汎用 webhook にフォールバック
WEBHOOK_ENVS = ("DISCORD_WEBHOOK_URL_LINE", "DISCORD_WEBHOOK_URL")
# Discord 前段の Cloudflare は User-Agent 無しを 429/1015 で弾くため固定で付ける
HEADERS = {
    "User-Agent": "DiscordBot (line-metrics-dashboard, 1.0)",
    "Content-Type": "application/json",
}
TIMEOUT = 15
COLOR_OK = 0x2ECC71
COLOR_ERR = 0xE74C3C


def _webhook_url() -> str | None:
    for key in WEBHOOK_ENVS:
        url = os.environ.get(key)
        if url:
            return url
    return None


def _post_discord(payload: dict) -> None:
    """webhook へ POST。URL 未設定なら警告のみで送信しない(本処理を巻き込まない)."""
    url = _webhook_url()
    if not url:
        print(f"⚠️ {' / '.join(WEBHOOK_ENVS)} 未設定 → Discord通知スキップ", file=sys.stderr)
        return
    resp = requests.post(url, json=payload, headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()


def _get_supabase():
    from supabase import create_client

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL / SUPABASE_SERVICE_KEY が未設定です。")
    return create_client(url, key)


def _self_accounts(sb) -> list[dict]:
    """line_accounts から category='self' かつ tracked=true のアカウント(id,name)を返す."""
    res = (
        sb.table("line_accounts")
        .select("account_id,name,sort_order")
        .eq("category", "self")
        .eq("tracked", True)
        .order("sort_order")
        .execute()
    )
    return res.data or []


def compute_self_new_friends(client: UtageClient, sb, today: date) -> dict:
    """self アカウント別のグロス新規(当日/今月)を created_at から算出する.

    UTAGE /readers は1人が複数シナリオ行を持つため、common_reader_id で
    アカウント内名寄せし、各人の最古 created_at を「友だち登録日」とみなす。
    """
    accounts = _self_accounts(sb)
    month_start = today.replace(day=1)
    per_account: list[dict] = []
    total_daily = 0
    total_month = 0
    for a in accounts:
        first_seen: dict[str, date] = {}
        for rd in funnel.fetch_all_readers(client, a["account_id"]):
            crid = rd.get("common_reader_id") or rd.get("id")
            d = parse_created_date(rd.get("created_at"))
            if not crid or not d:
                continue
            if crid not in first_seen or d < first_seen[crid]:
                first_seen[crid] = d
        daily = sum(1 for d in first_seen.values() if d == today)
        month = sum(1 for d in first_seen.values() if month_start <= d <= today)
        per_account.append(
            {"name": a.get("name") or a["account_id"], "daily": daily, "month": month}
        )
        total_daily += daily
        total_month += month
    return {
        "per_account": per_account,
        "total_daily": total_daily,
        "total_month": total_month,
        "self_account_count": len(accounts),
    }


def build_report_embed(today: date, m: dict) -> dict:
    fields = [
        {
            "name": a["name"],
            "value": f"当日 {a['daily']:+,} / 今月 {a['month']:+,}",
            "inline": True,
        }
        for a in m["per_account"]
    ]
    fields.append(
        {
            "name": "🔢 合計",
            "value": f"当日 {m['total_daily']:+,} 人 / 今月 {m['total_month']:+,} 人",
            "inline": False,
        }
    )
    return {
        "title": "📊 LINE 友だち日次レポート",
        "description": f"自社アカウント別 友だち追加数（当日 / 今月）※{today.isoformat()} 時点",
        "color": COLOR_OK,
        "fields": fields,
        "footer": {"text": f"対象 {m['self_account_count']} アカウント / line_metrics_dashboard"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def build_error_embed(today: date, error: Exception) -> dict:
    return {
        "title": "⚠️ LINE 集計失敗",
        "description": f"日次集計でエラーが発生しました（{today.isoformat()}）",
        "color": COLOR_ERR,
        "fields": [
            {"name": "エラー種別", "value": type(error).__name__, "inline": True},
            # Discord のフィールド値上限は 1024 文字
            {"name": "メッセージ", "value": (str(error) or "(詳細なし)")[:1000], "inline": False},
        ],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def send_daily_report(client: UtageClient | None = None, sb=None, today: date | None = None) -> None:
    """集計→レポート送信。送信/集計の例外は警告printで握り、collector本体を落とさない."""
    today = today or date.today()
    try:
        client = client or UtageClient()
        sb = sb or _get_supabase()
        m = compute_self_new_friends(client, sb, today)
        _post_discord({"embeds": [build_report_embed(today, m)]})
        print(
            f"📨 Discordレポート送信: 当日+{m['total_daily']} / 今月+{m['total_month']}"
            f"（self {m['self_account_count']}件・アカウント別）"
        )
    except Exception as e:
        print(f"⚠️ Discordレポート送信失敗: {e}", file=sys.stderr)


def send_error_report(error: Exception, today: date | None = None) -> None:
    """集計失敗をDiscordへ通知。通知自体の失敗は stderr のみ."""
    today = today or date.today()
    try:
        _post_discord({"embeds": [build_error_embed(today, error)]})
        print("📨 Discordエラー通知を送信", file=sys.stderr)
    except Exception as e:
        print(f"⚠️ Discordエラー通知も失敗: {e}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description="Discord 日次レポート送信")
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--test", action="store_true", help="ダミー数値で1通(API/DB不要)")
    g.add_argument("--send", action="store_true", help="実集計して送信")
    g.add_argument("--error-test", action="store_true", help="エラーembedの見た目確認")
    args = parser.parse_args()

    today = date.today()
    if args.test:
        dummy = {
            "per_account": [
                {"name": "個別サポートLINE_Buzz Lab", "daily": 4, "month": 120},
                {"name": "Bazz Lab講座生サポート用", "daily": 0, "month": 8},
                {"name": "イチ🐰LINE", "daily": 2, "month": 41},
            ],
            "total_daily": 6,
            "total_month": 169,
            "self_account_count": 15,
        }
        _post_discord({"embeds": [build_report_embed(today, dummy)]})
        print("📨 テスト送信完了")
    elif args.error_test:
        _post_discord({"embeds": [build_error_embed(today, RuntimeError("これはテスト用のエラーです"))]})
        print("📨 エラーテスト送信完了")
    elif args.send:
        send_daily_report(today=today)
    return 0


if __name__ == "__main__":
    sys.exit(main())
