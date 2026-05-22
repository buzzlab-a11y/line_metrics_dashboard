"""UTAGE REST API 共通クライアント.

使い方:
    from utage_client import UtageClient, load_allowed_account_ids

    client = UtageClient()  # .env の UTAGE_API_KEY を自動読込
    allowed = load_allowed_account_ids()  # groups.yaml からスコープ取得
    for account_id in allowed:
        client.get(f"/accounts/{account_id}/scenarios")

事業別アカウントを切り替える場合:
    client = UtageClient(account="afiniki")  # .env の UTAGE_API_KEY_AFINIKI
"""
from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

BASE_URL = "https://api.utage-system.com/v1"
RATE_LIMIT_SAFETY_THRESHOLD = 10  # X-RateLimit-Remaining がこの値を下回ったら sleep
DEFAULT_TIMEOUT = 30
PROJECT_ROOT = Path(__file__).resolve().parent  # collector/（.env・groups.yaml・kouzasei.yaml をここに置く）


class UtageAPIError(Exception):
    """UTAGE API 呼び出しの汎用エラー."""

    def __init__(self, status_code: int, message: str, body: Any = None):
        super().__init__(f"[{status_code}] {message}")
        self.status_code = status_code
        self.body = body


class UtageClient:
    def __init__(self, account: str | None = None, base_url: str = BASE_URL):
        env_path = PROJECT_ROOT / ".env"
        if env_path.exists():
            load_dotenv(env_path)

        env_key = "UTAGE_API_KEY"
        if account:
            env_key = f"UTAGE_API_KEY_{account.upper()}"
        api_key = os.environ.get(env_key)
        if not api_key:
            raise RuntimeError(
                f"{env_key} が未設定です。marketing/utage/.env を確認してください。"
            )

        self._base_url = base_url.rstrip("/")
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
            }
        )

    # --- public methods ---------------------------------------------------

    def get(self, path: str, params: dict | None = None) -> Any:
        return self._request("GET", path, params=params)

    def post(self, path: str, json: dict | None = None) -> Any:
        return self._request("POST", path, json=json)

    def put(self, path: str, json: dict | None = None) -> Any:
        return self._request("PUT", path, json=json)

    def patch(self, path: str, json: dict | None = None) -> Any:
        return self._request("PATCH", path, json=json)

    # --- internal ---------------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        json: dict | None = None,
    ) -> Any:
        url = f"{self._base_url}/{path.lstrip('/')}"
        for attempt in range(3):
            resp = self._session.request(
                method, url, params=params, json=json, timeout=DEFAULT_TIMEOUT
            )

            remaining = resp.headers.get("X-RateLimit-Remaining")
            if remaining is not None and remaining.isdigit():
                if int(remaining) <= RATE_LIMIT_SAFETY_THRESHOLD:
                    time.sleep(1.0)

            if resp.status_code == 429:
                reset = resp.headers.get("X-RateLimit-Reset")
                wait = self._wait_seconds(reset)
                print(f"[utage] 429 Rate Limit. {wait:.1f}s 待機して再試行")
                time.sleep(wait)
                continue

            if not resp.ok:
                try:
                    body = resp.json()
                except ValueError:
                    body = resp.text
                raise UtageAPIError(resp.status_code, resp.reason, body)

            if resp.status_code == 204 or not resp.content:
                return None
            return resp.json()

        raise UtageAPIError(429, "Rate limit retries exhausted")

    @staticmethod
    def _wait_seconds(reset_header: str | None) -> float:
        if not reset_header or not reset_header.isdigit():
            return 5.0
        delta = int(reset_header) - int(time.time())
        return max(delta, 1.0)


# --- groups.yaml 読み込み ----------------------------------------------------
# 簡易 YAML パーサ（pyyaml を依存に追加しない方針）。
# groups.yaml はネスト2階層・コメント許容・リスト要素のみという限定スキーマで扱う。


def load_groups_config(path: Path | None = None) -> dict:
    """groups.yaml を簡易パースして dict で返す.

    Returns:
        {"scope": "kindle", "groups": {"buzz_lab": {"account_ids": [...], "description": "..."}, ...}}
    """
    yaml_path = path or (PROJECT_ROOT / "groups.yaml")
    if not yaml_path.exists():
        raise RuntimeError(f"groups.yaml が見つかりません: {yaml_path}")

    scope: str | None = None
    groups: dict[str, dict] = {}
    current_group: str | None = None
    current_field: str | None = None
    in_groups_block = False

    for raw_line in yaml_path.read_text(encoding="utf-8").splitlines():
        # コメント除去
        line = re.sub(r"\s+#.*$", "", raw_line)
        line = line.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue

        # トップレベル: scope: kindle
        m = re.match(r"^scope:\s*(.+)$", line)
        if m:
            scope = m.group(1).strip()
            in_groups_block = False
            continue

        # トップレベル: groups:
        if re.match(r"^groups:\s*$", line):
            in_groups_block = True
            current_group = None
            continue

        if not in_groups_block:
            continue

        # 2スペースインデント: グループ名
        m = re.match(r"^  ([A-Za-z_][A-Za-z0-9_]*):\s*$", line)
        if m:
            current_group = m.group(1)
            groups[current_group] = {"description": "", "account_ids": []}
            current_field = None
            continue

        # 4スペースインデント: フィールド
        m = re.match(r"^    (description|account_ids):\s*(.*)$", line)
        if m and current_group:
            current_field = m.group(1)
            rest = m.group(2).strip()
            if current_field == "description":
                groups[current_group]["description"] = rest
            continue

        # 6スペースインデント: リスト要素
        m = re.match(r"^      -\s*(\S+)\s*$", line)
        if m and current_group and current_field == "account_ids":
            groups[current_group]["account_ids"].append(m.group(1))
            continue

    return {"scope": scope, "groups": groups}


def load_allowed_account_ids(group: str | None = None) -> list[str]:
    """groups.yaml で許可されたアカウントIDのリストを返す.

    Args:
        group: グループ名を指定するとそのグループのみ。None なら全グループ統合。
    """
    config = load_groups_config()
    if group:
        if group not in config["groups"]:
            raise ValueError(f"未定義のグループ: {group}")
        return list(config["groups"][group]["account_ids"])
    ids: list[str] = []
    for g in config["groups"].values():
        ids.extend(g["account_ids"])
    return ids
