"""講座生ファネルのステージ計算.

marketing/utage/scripts/build_affiliate_center.py のステージ計算ロジックを
HTML描画から切り離し、Supabase 投入用のフラットなレコードを返す形に抽出したもの。

kouzasei.yaml で定義した講座生について、
自LINE → (親LINE) → 面談LINE → 面談予約 → 成約 の各ステージ人数を算出する。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from utage_client import PROJECT_ROOT, UtageAPIError, UtageClient

CONFIG_PATH = PROJECT_ROOT / "kouzasei.yaml"

# 動線ルート別のステージ定義（build_affiliate_center.py と同一）
ROUTE_STAGES: dict[str, list[dict]] = {
    "direct_to_interview": [
        {"key": "own_line", "label": "① 自LINE登録"},
        {"key": "interview_inflow", "label": "② 共通面談LINE流入"},
        {"key": "interview_reserved", "label": "③ 面談予約済"},
        {"key": "contracted", "label": "④ 成約"},
    ],
    "via_parent_line": [
        {"key": "own_line", "label": "① 自LINE登録"},
        {"key": "parent_inflow", "label": "② 親LINE流入"},
        {"key": "interview_inflow", "label": "③ 共通面談LINE流入"},
        {"key": "interview_reserved", "label": "④ 面談予約済"},
        {"key": "contracted", "label": "⑤ 成約"},
    ],
    # 自LINE一本で計測。面談予約LINE側のアクションで自LINEのラベルを同期する運用。
    "own_line_labels": [
        {"key": "own_line", "label": "① 自LINE登録"},
        {"key": "interview_inflow", "label": "② 面談LINE流入"},
        {"key": "interview_reserved", "label": "③ 面談予約済"},
        {"key": "contracted", "label": "④ 成約"},
    ],
}

PAYMENT_KEYWORDS = ("決済", "成約", "購入", "purchase")


# ---------- kouzasei.yaml パーサ（build_affiliate_center.py の手書きパーサを流用） ----------


def load_config(path: Path | None = None) -> dict:
    """kouzasei.yaml をインデントベースで確実に読む."""
    yaml_path = path or CONFIG_PATH
    text = yaml_path.read_text(encoding="utf-8")
    infra: dict = {}
    kouzasei: list[dict] = []

    section = None
    current_infra_key = None
    current_kouzasei: dict | None = None
    current_kouzasei_sub: str | None = None

    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        line = re.sub(r"\s+#.*$", "", raw).rstrip()
        if not line.strip():
            continue

        if re.match(r"^infra:\s*$", line):
            section = "infra"
            continue
        if re.match(r"^kouzasei:\s*$", line):
            section = "kouzasei"
            continue

        if section == "infra":
            m1 = re.match(r"^  ([a-z_]+):\s*$", line)
            if m1:
                current_infra_key = m1.group(1)
                infra[current_infra_key] = {}
                continue
            m2 = re.match(r"^    ([a-z_]+):\s*(.+)$", line)
            if m2 and current_infra_key:
                infra[current_infra_key][m2.group(1)] = m2.group(2).strip()
                continue

        if section == "kouzasei":
            m = re.match(r"^  - id:\s*(.+)$", line)
            if m:
                current_kouzasei = {"id": m.group(1).strip()}
                kouzasei.append(current_kouzasei)
                current_kouzasei_sub = None
                continue
            if current_kouzasei is None:
                continue
            m = re.match(r"^    ([a-z_]+):\s*$", line)
            if m:
                current_kouzasei_sub = m.group(1)
                current_kouzasei[current_kouzasei_sub] = {}
                continue
            m = re.match(r"^    ([a-z_]+):\s*(.+)$", line)
            if m:
                current_kouzasei[m.group(1)] = m.group(2).strip()
                current_kouzasei_sub = None
                continue
            # サブセクション配下のリスト要素（例: contracted_scenario_ids: - xxx）
            m = re.match(r"^      -\s*(\S+)\s*$", line)
            if m and current_kouzasei_sub:
                cur = current_kouzasei.get(current_kouzasei_sub)
                if not isinstance(cur, list):
                    current_kouzasei[current_kouzasei_sub] = []
                current_kouzasei[current_kouzasei_sub].append(m.group(1))
                continue
            m = re.match(r"^      ([a-z_]+):\s*(.+)$", line)
            if m and current_kouzasei_sub:
                if isinstance(current_kouzasei.get(current_kouzasei_sub), dict):
                    current_kouzasei[current_kouzasei_sub][m.group(1)] = m.group(2).strip()
                continue

    return {"infra": infra, "kouzasei": kouzasei}


# ---------- API データ取得 ----------


def fetch_all_readers(client: UtageClient, account_id: str) -> list[dict]:
    """指定アカウントの全 readers をページングで取得."""
    out: list[dict] = []
    per_page = 100
    total: int | None = None
    for page in range(1, 200):
        try:
            r = client.get(
                f"/accounts/{account_id}/readers",
                params={"per_page": per_page, "page": page},
            )
        except UtageAPIError as e:
            print(f"  ⚠️ readers page {page} fetch error: {e}", file=sys.stderr)
            break
        data = r.get("data", []) or []
        out.extend(data)
        meta = r.get("meta", {}) or {}
        if total is None and meta.get("total") is not None:
            total = meta["total"]
        if not data:
            break
        if total is not None and len(out) >= total:
            break
        if len(data) < per_page:
            break
    return out


def has_label(reader: dict, label_name: str) -> bool:
    return any(
        (l.get("name") or "").strip() == label_name.strip()
        for l in reader.get("labels", []) or []
    )


def has_tracking(reader: dict, tracking_name: str) -> bool:
    return (reader.get("message_tracking_name") or "").strip() == tracking_name.strip()


def count_by(readers: list[dict], pred) -> int:
    return sum(1 for r in readers if pred(r))


def detect_payment_scenario_ids(client: UtageClient, account_id: str) -> set[str]:
    """シナリオ名に決済/成約/購入キーワードを含むものの ID セットを返す."""
    try:
        scs = client.get(
            f"/accounts/{account_id}/scenarios", params={"per_page": 200}
        ).get("data", [])
    except UtageAPIError:
        return set()
    out: set[str] = set()
    for sc in scs:
        title = sc.get("title") or ""
        if any(k in title for k in PAYMENT_KEYWORDS):
            out.add(sc["id"])
    return out


def _has_funnel_tracking_in_payment(
    reader: dict, payment_scenario_ids: set[str], funnel_tracking_name: str
) -> bool:
    if not funnel_tracking_name:
        return False
    sid = reader.get("scenario_id")
    if sid not in payment_scenario_ids:
        return False
    return (reader.get("funnel_tracking_name") or "").strip() == funnel_tracking_name.strip()


def _stage_value(
    stage_key: str,
    labels: dict,
    tracking: dict,
    own_total: int,
    own_open: bool,
    parent_readers: list[dict],
    interview_readers: list[dict],
    funnel_tracking_name: str,
    payment_sc_parent: set[str],
    payment_sc_interview: set[str],
) -> int:
    """各ステージの代表人数（value）を返す.

    build_affiliate_center.py の compute_stage_value から value のみを取り出した版。
    """
    if stage_key == "own_line":
        return own_total if own_open else 0

    if stage_key == "parent_inflow":
        lab = labels.get("parent_inflow", "")
        trk = tracking.get("parent_inflow", "")
        by_label = count_by(parent_readers, lambda r: has_label(r, lab)) if lab else 0
        by_tracking = count_by(parent_readers, lambda r: has_tracking(r, trk)) if trk else 0
        return max(by_label, by_tracking)

    if stage_key == "interview_inflow":
        lab = labels.get("interview_inflow", "")
        return count_by(interview_readers, lambda r: has_label(r, lab)) if lab else 0

    if stage_key == "interview_reserved":
        lab = labels.get("interview_reserved", "")
        return count_by(interview_readers, lambda r: has_label(r, lab)) if lab else 0

    if stage_key == "contracted":
        lab = labels.get("contracted", "")
        by_parent = count_by(parent_readers, lambda r: has_label(r, lab)) if lab else 0
        by_interview = count_by(interview_readers, lambda r: has_label(r, lab)) if lab else 0
        by_label = max(by_parent, by_interview)

        by_funnel = 0
        if funnel_tracking_name:
            by_funnel = count_by(
                parent_readers,
                lambda r: _has_funnel_tracking_in_payment(
                    r, payment_sc_parent, funnel_tracking_name
                ),
            ) + count_by(
                interview_readers,
                lambda r: _has_funnel_tracking_in_payment(
                    r, payment_sc_interview, funnel_tracking_name
                ),
            )
        return max(by_label, by_funnel)

    return 0


def compute_funnel_records(client: UtageClient, config: dict, snapshot_date: str) -> list[dict]:
    """講座生別・ステージ別のフラットなレコード（line_funnel_snapshots 投入用）を返す.

    Returns:
        [{"kouzasei_id", "display_name", "snapshot_date", "stage", "count"}, ...]
    """
    infra = config["infra"]
    parent_id = infra["parent_line"]["account_id"]
    interview_id = infra["interview_line"]["account_id"]

    # 共通インフラ(親LINE/面談LINE)は own_line_labels 以外のルートがある時だけ取得
    needs_infra = any(k.get("route") != "own_line_labels" for k in config["kouzasei"])
    parent_readers: list[dict] = []
    interview_readers: list[dict] = []
    payment_sc_parent: set[str] = set()
    payment_sc_interview: set[str] = set()
    if needs_infra:
        print(f"親LINE ({infra['parent_line']['name']}) 全 readers を取得中...", flush=True)
        parent_readers = fetch_all_readers(client, parent_id)
        print(f"  取得: {len(parent_readers)} 人")

        print(f"面談LINE ({infra['interview_line']['name']}) 全 readers を取得中...", flush=True)
        interview_readers = fetch_all_readers(client, interview_id)
        print(f"  取得: {len(interview_readers)} 人")

        payment_sc_parent = detect_payment_scenario_ids(client, parent_id)
        payment_sc_interview = detect_payment_scenario_ids(client, interview_id)

    records: list[dict] = []
    for k in config["kouzasei"]:
        route = k.get("route") or "via_parent_line"
        if route not in ROUTE_STAGES:
            route = "via_parent_line"

        own_line = k.get("own_line") or {}
        own_id = own_line.get("account_id")
        own_open = bool(own_id)
        own_total = 0
        if own_open:
            try:
                own = client.get(f"/accounts/{own_id}/readers", params={"per_page": 1})
                own_total = own.get("meta", {}).get("total", 0)
            except UtageAPIError as e:
                print(f"  ⚠️ own_line fetch error: {e}", file=sys.stderr)

        labels = k.get("labels") or {}
        tracking = k.get("tracking") or {}
        funnel_tracking_name = (k.get("funnel_tracking_name") or "").strip()

        # own_line_labels: 自LINE(own_line)で全ステージを計測。
        #   流入・予約 = 同期ラベル / 成約 = 決済時シナリオ登録（決済完了シグナル）
        #   readers は1人が複数シナリオ行を持つため common_reader_id で名寄せして人数化。
        if route == "own_line_labels":
            own_readers = fetch_all_readers(client, own_id) if own_open else []

            def _people_with_label(lab: str) -> int:
                if not lab:
                    return 0
                return len({
                    r.get("common_reader_id")
                    for r in own_readers
                    if r.get("common_reader_id") and has_label(r, lab)
                })

            contracted_scenarios = set(k.get("contracted_scenario_ids") or [])
            if contracted_scenarios:
                contracted_val = len({
                    r.get("common_reader_id")
                    for r in own_readers
                    if r.get("common_reader_id") and r.get("scenario_id") in contracted_scenarios
                })
            else:
                contracted_val = _people_with_label(labels.get("contracted", ""))

            counts = {
                "own_line": own_total,
                "interview_inflow": _people_with_label(labels.get("interview_inflow", "")),
                "interview_reserved": _people_with_label(labels.get("interview_reserved", "")),
                "contracted": contracted_val,
            }
            for stage_def in ROUTE_STAGES[route]:
                sk = stage_def["key"]
                records.append(
                    {
                        "kouzasei_id": k.get("id"),
                        "display_name": k.get("display_name"),
                        "snapshot_date": snapshot_date,
                        "stage": sk,
                        "count": counts.get(sk, 0),
                    }
                )
                print(f"  [{k.get('display_name')}] {stage_def['label']}: {counts.get(sk, 0)}")
            continue

        for stage_def in ROUTE_STAGES[route]:
            sk = stage_def["key"]
            value = _stage_value(
                sk,
                labels,
                tracking,
                own_total,
                own_open,
                parent_readers,
                interview_readers,
                funnel_tracking_name,
                payment_sc_parent,
                payment_sc_interview,
            )
            records.append(
                {
                    "kouzasei_id": k.get("id"),
                    "display_name": k.get("display_name"),
                    "snapshot_date": snapshot_date,
                    "stage": sk,
                    "count": value,
                }
            )
            print(f"  [{k.get('display_name')}] {stage_def['label']}: {value}")

    return records
