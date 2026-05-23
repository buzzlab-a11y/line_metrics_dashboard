import { useMemo } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts';
import { G } from '../styles/theme';
import { latestDate } from '../hooks/useLineMetrics';
import { Card, Empty } from './FriendsTrend';

/**
 * 流入経路（message_tracking_name 別の登録者数）。
 * どの投稿/媒体から登録したか。最新スナップショットを tracking_name で集計して横棒表示。
 * 対象アカウントは App のグローバル選択（カテゴリ/個別）に従う。
 */
export default function InflowBySource({ inflow }) {
  const last = latestDate(inflow);

  // 最新日・対象アカウントを tracking_name で合算
  const rows = useMemo(() => {
    const agg = {};
    for (const r of inflow) {
      if (r.snapshot_date !== last) continue;
      agg[r.tracking_name] = (agg[r.tracking_name] || 0) + (r.count || 0);
    }
    return Object.entries(agg)
      .map(([name, value]) => ({ name, value }))
      .sort((a, b) => b.value - a.value);
  }, [inflow, last]);

  const total = useMemo(() => rows.reduce((s, r) => s + r.value, 0), [rows]);

  if (inflow.length === 0) return <Empty />;

  return (
    <div>
      <div style={{ display: 'flex', marginBottom: 12, alignItems: 'center' }}>
        <span style={{ fontSize: 13, color: G.text2 }}>
          登録者の流入経路（合計 {total.toLocaleString()}人）
        </span>
        <span style={{ fontSize: 12, color: G.text3, marginLeft: 'auto' }}>最新: {last}</span>
      </div>

      <Card title="📊 流入経路別 登録者数">
        {rows.length === 0 ? (
          <p style={{ color: G.text3, fontSize: 13 }}>流入経路データがありません。</p>
        ) : (
          <ResponsiveContainer width="100%" height={Math.max(220, rows.length * 44)}>
            <BarChart data={rows} layout="vertical" margin={{ left: 20, right: 40 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={G.border} horizontal={false} />
              <XAxis type="number" tick={{ fontSize: 12, fill: G.text2 }} />
              <YAxis type="category" dataKey="name" width={150} tick={{ fontSize: 12, fill: G.text1 }} />
              <Tooltip
                formatter={(v) => [
                  `${v}人${total ? `（${((v / total) * 100).toFixed(1)}%）` : ''}`,
                  '登録者',
                ]}
              />
              <Bar dataKey="value" fill={G.primary} radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        )}
      </Card>

      {/* 内訳テーブル */}
      <div style={{ marginTop: 16, background: G.surface, borderRadius: G.radiusMd, border: `1px solid ${G.border}`, overflow: 'hidden' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ background: G.surfaceVariant }}>
              <th style={{ padding: '10px 14px', textAlign: 'left', color: G.text2, fontWeight: 600 }}>流入経路</th>
              <th style={{ padding: '10px 14px', textAlign: 'right', color: G.text2, fontWeight: 600 }}>人数</th>
              <th style={{ padding: '10px 14px', textAlign: 'right', color: G.text2, fontWeight: 600 }}>割合</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.name} style={{ borderTop: `1px solid ${G.border}` }}>
                <td style={{ padding: '8px 14px', color: G.text1 }}>{r.name}</td>
                <td style={{ padding: '8px 14px', textAlign: 'right', fontWeight: 600, color: G.primary, fontVariantNumeric: 'tabular-nums' }}>
                  {r.value.toLocaleString()}
                </td>
                <td style={{ padding: '8px 14px', textAlign: 'right', color: G.text2, fontVariantNumeric: 'tabular-nums' }}>
                  {total ? ((r.value / total) * 100).toFixed(1) : '0.0'}%
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
