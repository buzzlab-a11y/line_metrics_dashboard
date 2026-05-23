import { useMemo, useState } from 'react';
import {
  ComposedChart, Bar, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from 'recharts';
import { G } from '../styles/theme';
import { latestDate } from '../hooks/useLineMetrics';

const GRANULARITIES = [
  { id: 'day', label: '日次' },
  { id: 'week', label: '週次' },
  { id: 'month', label: '月次' },
];

// ── 日付ユーティリティ ─────────────────────────────
function mondayOf(dateStr) {
  const d = new Date(dateStr + 'T00:00:00');
  const day = (d.getDay() + 6) % 7; // 月曜=0
  d.setDate(d.getDate() - day);
  return d.toISOString().slice(0, 10);
}
function bucketKey(dateStr, gran) {
  if (gran === 'month') return dateStr.slice(0, 7);      // YYYY-MM
  if (gran === 'week') return mondayOf(dateStr);          // 週初(月)
  return dateStr;                                         // 日次
}
function bucketLabel(key, gran) {
  if (gran === 'month') return key;                       // YYYY-MM
  return key.slice(5);                                    // MM-DD
}

/**
 * スコープ内アカウントについて、各日の「友だち数（累積）」をキャリーフォワード合算した
 * 日次系列を返す。過去復元データはアカウントごとに登録日しか点が無いため、
 * 直近値を持ち越して合算する必要がある。
 */
function dailyStockSeries(daily, accounts) {
  const ids = accounts.map((a) => a.account_id);
  const byAcct = {};
  ids.forEach((id) => (byAcct[id] = []));
  for (const r of daily) {
    if (byAcct[r.account_id]) byAcct[r.account_id].push({ date: r.snapshot_date, total: r.readers_total || 0 });
  }
  ids.forEach((id) => byAcct[id].sort((a, b) => (a.date < b.date ? -1 : 1)));

  const allDates = [...new Set(daily.map((r) => r.snapshot_date))].sort();
  const ptr = {}; ids.forEach((id) => (ptr[id] = -1));
  const last = {}; ids.forEach((id) => (last[id] = 0));

  return allDates.map((date) => {
    let total = 0;
    for (const id of ids) {
      const pts = byAcct[id];
      while (ptr[id] + 1 < pts.length && pts[ptr[id] + 1].date <= date) {
        ptr[id]++;
        last[id] = pts[ptr[id]].total;
      }
      total += last[id];
    }
    return { date, friends: total };
  });
}

export default function FriendsTrend({ daily, accounts }) {
  const [gran, setGran] = useState('week');

  // 日次の累積友だち数 + 日次新規
  const dailySeries = useMemo(() => dailyStockSeries(daily, accounts), [daily, accounts]);

  // 期間バケットへ集計（友だち数=期末値、新規=期間内の増分合計）
  const series = useMemo(() => {
    const dailyNew = dailySeries.map((p, i) => ({
      date: p.date,
      friends: p.friends,
      neu: i === 0 ? p.friends : p.friends - dailySeries[i - 1].friends,
    }));
    const buckets = new Map();
    for (const p of dailyNew) {
      const key = bucketKey(p.date, gran);
      if (!buckets.has(key)) buckets.set(key, { key, friends: 0, 新規: 0 });
      const b = buckets.get(key);
      b.friends = p.friends; // 最後の日付の値が残る（期末ストック）
      b.新規 += p.neu;
    }
    return [...buckets.values()]
      .sort((a, b) => (a.key < b.key ? -1 : 1))
      .map((b) => ({ name: bucketLabel(b.key, gran), 友だち数: b.friends, 新規: b.新規 }));
  }, [dailySeries, gran]);

  // 最新日サマリー（前日比含む）
  const dates = useMemo(() => [...new Set(daily.map((r) => r.snapshot_date))].sort(), [daily]);
  const last = latestDate(daily);
  const prev = dates.length >= 2 ? dates[dates.length - 2] : null;
  const cards = useMemo(() => {
    return accounts.map((a) => {
      const cur = daily.find((r) => r.snapshot_date === last && r.account_id === a.account_id);
      const pre = prev ? daily.find((r) => r.snapshot_date === prev && r.account_id === a.account_id) : null;
      const total = cur?.readers_total ?? 0;
      const newCount = pre ? total - (pre.readers_total ?? 0) : null;
      return { name: a.name, total, newCount };
    });
  }, [accounts, daily, last, prev]);

  if (daily.length === 0) return <Empty />;

  return (
    <div>
      <Toggle options={GRANULARITIES} value={gran} onChange={setGran} />

      <Card title="📈 友だち数（累積・期末）と 新規登録">
        <ResponsiveContainer width="100%" height={360}>
          <ComposedChart data={series}>
            <CartesianGrid strokeDasharray="3 3" stroke={G.border} />
            <XAxis dataKey="name" tick={{ fontSize: 11, fill: G.text2 }} />
            <YAxis yAxisId="left" tick={{ fontSize: 12, fill: G.text2 }} />
            <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 12, fill: G.text3 }} />
            <Tooltip />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Bar yAxisId="right" dataKey="新規" fill={G.successContainer} stroke={G.success} radius={[4, 4, 0, 0]} />
            <Line yAxisId="left" type="monotone" dataKey="友だち数" stroke={G.primary} strokeWidth={2.5} dot={false} />
          </ComposedChart>
        </ResponsiveContainer>
        <p style={{ fontSize: 11.5, color: G.text3, marginTop: 8 }}>
          ※ 友だち数（累積）と新規は読者の登録日から過去復元。
        </p>
      </Card>

      <h3 style={{ fontSize: 14, color: G.text2, margin: '20px 0 10px', fontWeight: 700 }}>
        最新（{last}）アカウント別サマリー
      </h3>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(220px,1fr))', gap: 12 }}>
        {cards.map((c) => (
          <div
            key={c.name}
            style={{
              background: G.surface, border: `1px solid ${G.border}`,
              borderRadius: G.radiusMd, padding: 16, boxShadow: G.shadow1,
            }}
          >
            <div style={{ fontSize: 13, color: G.text2, fontWeight: 600, marginBottom: 8, minHeight: 34 }}>
              {c.name}
            </div>
            <div style={{ fontSize: 28, fontWeight: 700, color: G.primary }}>
              {c.total.toLocaleString()}
              <span style={{ fontSize: 12, color: G.text3, fontWeight: 400 }}> 友だち</span>
            </div>
            <div style={{ display: 'flex', gap: 14, marginTop: 8, fontSize: 12 }}>
              <span style={{ color: G.success }}>
                新規 {c.newCount === null ? '—' : c.newCount >= 0 ? `+${c.newCount}` : c.newCount}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function Toggle({ options, value, onChange }) {
  return (
    <div style={{ display: 'flex', gap: 6, marginBottom: 14 }}>
      {options.map((o) => (
        <button
          key={o.id}
          onClick={() => onChange(o.id)}
          style={{
            padding: '6px 16px',
            borderRadius: G.radiusPill,
            border: `1px solid ${value === o.id ? G.primary : G.border}`,
            background: value === o.id ? G.primaryContainer : G.surface,
            color: value === o.id ? G.primary : G.text2,
            fontSize: 12.5,
            fontWeight: 600,
          }}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Card({ title, children }) {
  return (
    <div
      style={{
        background: G.surface, border: `1px solid ${G.border}`,
        borderRadius: G.radiusMd, padding: 18, boxShadow: G.shadow1,
      }}
    >
      {title && <h3 style={{ fontSize: 14, color: G.text2, marginBottom: 12, fontWeight: 700 }}>{title}</h3>}
      {children}
    </div>
  );
}

export function Empty() {
  return (
    <div style={{ background: G.surfaceVariant, borderRadius: G.radiusMd, padding: 32, textAlign: 'center', color: G.text3 }}>
      このカテゴリのデータがまだありません（collector の実行待ち）。
    </div>
  );
}
