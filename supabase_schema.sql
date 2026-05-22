-- ============================================================
-- LINE数字計測ダッシュボード — スキーマ
-- UTAGE REST API から日次収集したスナップショットを時系列で保持
-- Supabase SQL Editor で一括実行（冪等・再実行可）
-- 書込は service_role キー（collector）、フロントは anon で read のみ
-- ============================================================

-- 既存テーブル削除（再セットアップ用）
drop table if exists line_funnel_snapshots cascade;
drop table if exists line_message_stats    cascade;
drop table if exists line_label_snapshots  cascade;
drop table if exists line_daily_snapshots  cascade;
drop table if exists line_accounts         cascade;

-- ============================================================
-- 1. アカウントマスタ（groups.yaml + line_categories.yaml から投入）
-- ============================================================
create table line_accounts (
  account_id text primary key,
  name       text    not null,
  category   text    not null,           -- 'self'（自社集客）| 'student'（講座生）
  group_name text    not null,           -- 'bazz_lab' | 'buzz_lab_kouzasei' | 'kindle_kouza'
  sort_order integer not null default 0,
  updated_at timestamptz not null default now()
);

-- ============================================================
-- 2. 友だち数の日次スナップショット → 推移・新規(日差)・ブロック
-- ============================================================
create table line_daily_snapshots (
  account_id    text not null references line_accounts(account_id) on delete cascade,
  snapshot_date date not null,
  readers_total integer not null default 0,  -- 友だち総数（readers の meta.total）
  blocked_count integer not null default 0,  -- is_blocked=1 の数
  active_count  integer not null default 0,  -- total - blocked
  primary key (account_id, snapshot_date)
);
create index on line_daily_snapshots (snapshot_date);

-- ============================================================
-- 3. 流入経路別（ラベル別登録者数）
-- ============================================================
create table line_label_snapshots (
  account_id       text not null references line_accounts(account_id) on delete cascade,
  snapshot_date    date not null,
  label_id         text not null,
  label_name       text not null default '',
  subscriber_count integer not null default 0,
  primary key (account_id, snapshot_date, label_id)
);
create index on line_label_snapshots (snapshot_date);

-- ============================================================
-- 4. 配信パフォーマンス（メッセージ別統計）
-- ============================================================
create table line_message_stats (
  account_id     text not null references line_accounts(account_id) on delete cascade,
  snapshot_date  date not null,
  message_id     text not null,
  scenario_id    text,
  scenario_title text,
  message_title  text,
  channel        text,
  send_count     integer not null default 0,
  click_count    integer not null default 0,
  click_rate     numeric not null default 0,
  primary key (account_id, snapshot_date, message_id)
);
create index on line_message_stats (snapshot_date);

-- ============================================================
-- 5. ファネル成約（講座生別ステージ人数）
-- ============================================================
create table line_funnel_snapshots (
  kouzasei_id   text not null,
  display_name  text not null,
  snapshot_date date not null,
  stage         text not null,  -- 'own_line'|'parent_inflow'|'interview_inflow'|'interview_reserved'|'contracted'
  count         integer not null default 0,
  primary key (kouzasei_id, snapshot_date, stage)
);
create index on line_funnel_snapshots (snapshot_date);

-- ============================================================
-- 6. アクセス権限
--   フロント（anon）: RLS 有効 + read 専用ポリシー（推奨パターン）
--   collector（service_role）: RLS をバイパスして書込
--   ※ このプロジェクトは新規テーブルに RLS が効くため、
--     grant だけでなく anon SELECT ポリシーが必須。
-- ============================================================
grant usage on schema public to anon;

do $$
declare t text;
begin
  foreach t in array array[
    'line_accounts','line_daily_snapshots','line_label_snapshots',
    'line_message_stats','line_funnel_snapshots'
  ] loop
    execute format('alter table public.%I enable row level security;', t);
    execute format('drop policy if exists anon_read on public.%I;', t);
    execute format('create policy anon_read on public.%I for select to anon using (true);', t);
    execute format('grant select on public.%I to anon;', t);
  end loop;
end $$;
