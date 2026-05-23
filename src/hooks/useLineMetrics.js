import { useEffect, useState } from 'react';
import { supabase } from '../lib/supabase';

// Supabase はデフォルトで 1000 行返す。多めに取りたいテーブルは range で広げる。
const PAGE_LIMIT = 5000;

async function fetchAll(table, order) {
  const q = supabase.from(table).select('*').range(0, PAGE_LIMIT - 1);
  if (order) q.order(order.col, { ascending: order.asc ?? true });
  const { data, error } = await q;
  if (error) throw error;
  return data ?? [];
}

/**
 * LINE計測スナップショットをまとめて読み込むフック。
 * 返り値: { loading, error, accounts, daily, labels, messages, funnel, reload }
 */
export function useLineMetrics() {
  const [state, setState] = useState({
    loading: true,
    error: null,
    accounts: [],
    daily: [],
    labels: [],
    messages: [],
    funnel: [],
    inflow: [],
  });

  async function load() {
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const [accounts, daily, labels, messages, funnel, inflow] = await Promise.all([
        fetchAll('line_accounts', { col: 'sort_order' }),
        fetchAll('line_daily_snapshots', { col: 'snapshot_date' }),
        fetchAll('line_label_snapshots', { col: 'snapshot_date' }),
        fetchAll('line_message_stats', { col: 'snapshot_date' }),
        fetchAll('line_funnel_snapshots', { col: 'snapshot_date' }),
        fetchAll('line_inflow_snapshots', { col: 'snapshot_date' }),
      ]);
      setState({ loading: false, error: null, accounts, daily, labels, messages, funnel, inflow });
    } catch (e) {
      setState((s) => ({ ...s, loading: false, error: e.message || String(e) }));
    }
  }

  useEffect(() => {
    load();
  }, []);

  return { ...state, reload: load };
}

/** スナップショットの最新日付を返す（YYYY-MM-DD）。なければ null。 */
export function latestDate(rows) {
  let max = null;
  for (const r of rows) {
    if (!max || r.snapshot_date > max) max = r.snapshot_date;
  }
  return max;
}
