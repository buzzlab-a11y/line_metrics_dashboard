# LINE数字計測ダッシュボード（UTAGE連携）

UTAGE REST API から LINE の数字を **日次スナップショット** で収集し、Supabase に時系列で蓄積。
React フロントで **自社集客 / 講座生** を分けて可視化する。

UTAGE API は実行時点の値しか返さず期間絞り込みが効かないため、推移を見るには日次でスナップショットを溜める設計。

## 構成

```
[GitHub Actions cron 日次] → collector(Python) → Supabase ← React(Vite) → Vercel
```

| 指標 | テーブル | データ元 |
|------|----------|----------|
| 友だち数・新規・ブロック推移 | `line_daily_snapshots` | `GET /accounts/{id}/readers` |
| 流入経路別 | `line_label_snapshots` | `GET /accounts/{id}/labels` |
| 配信パフォーマンス | `line_message_stats` | `.../scenarios/{sid}/messages/{mid}/stats` |
| 講座生ファネル成約 | `line_funnel_snapshots` | `kouzasei.yaml` ベースのステージ集計 |
| アカウント分類 | `line_accounts` | `groups.yaml` + `line_categories.yaml` |

## アカウント分類（self / student）
`collector/line_categories.yaml` で groups.yaml のグループ → カテゴリを対応付け:
- `bazz_lab` → `self`（自社集客）
- `buzz_lab_kouzasei` / `kindle_kouza` → `student`（講座生）

## セットアップ

### 1. Supabase
1. プロジェクトの SQL Editor で `supabase_schema.sql` を実行。
2. URL / anon key / service_role key を控える。

### 2. collector（ローカル実行）
```bash
cd collector
cp .env.example .env   # UTAGE_API_KEY / SUPABASE_URL / SUPABASE_SERVICE_KEY を記入
pip install -r requirements.txt

python collect_line_metrics.py --dry-run        # 書込まず確認
python collect_line_metrics.py                  # 本番（Supabaseへupsert）
python collect_line_metrics.py --skip-blocked   # 重いブロック数集計を省略
python collect_line_metrics.py --skip-messages  # 配信統計を省略

# 過去データの復元（初回のみ・任意）。読者の created_at から友だち数カーブを再構築
python backfill_friends.py --dry-run            # 集計確認
python backfill_friends.py                      # line_daily_snapshots に過去日を投入
```

`backfill_friends.py` で復元できるのは **友だち数の累積推移** と、その差分から得られる
**日/週/月別の新規登録数** のみ（ブロック・流入・配信・ファネルは本日以降の蓄積）。
「今も残っている読者」ベースのため、遠い過去ほど概算（解除済みは含まれない）。

### 3. フロント
```bash
cp .env.example .env   # VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY
npm install
npm run dev
```

### 4. GitHub Actions cron
`.github/workflows/collect.yml` が毎日 09:00 JST に collector を実行。
リポジトリ Secrets に `UTAGE_API_KEY` / `SUPABASE_URL` / `SUPABASE_SERVICE_KEY` を設定。
`workflow_dispatch` で手動実行も可能。

### 5. デプロイ
フロントを Vercel に接続し、環境変数に anon key を設定。

## 既知の制約
- UTAGE API は LINE公式の「友だち数」総数を直接返さないため、`readers` の `meta.total`（UTAGE登録者ベース）で代替。
- ブロック数は全 readers をページ取得して集計するため重い。負荷が問題なら `--skip-blocked`。
- 本ツールは **参照（GET）のみ**。UTAGE 側の作成/更新/削除は行わない。

## vendoring（重要）
`collector/` 内の以下は `marketing/utage/` からのコピー。**本家更新時は手動同期** が必要:
- `utage_client.py`（PROJECT_ROOT を collector/ に変更済み）
- `groups.yaml`
- `kouzasei.yaml`

ファネル計算ロジック（`funnel.py`）は `marketing/utage/scripts/build_affiliate_center.py` のステージ計算を抽出したもの。
