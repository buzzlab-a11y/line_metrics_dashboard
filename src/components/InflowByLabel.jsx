import { useMemo } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts';
import { G } from '../styles/theme';
import { latestDate } from '../hooks/useLineMetrics';
import { Card, Empty } from './FriendsTrend';

const TOP_N = 15;

/**
 * 流入経路別（ラベル別登録者数）。最新スナップショット日のラベルを
 * subscriber_count 降順の横棒で表示。アカウント絞り込みは App のグローバル選択に従う。
 */
export default function InflowByLabel({ labels, accounts }) {
  const last = latestDate(labels);

  const accountName = useMemo(() => {
    const m = {};
    for (const a of accounts) m[a.account_id] = a.name;
    return m;
  }, [accounts]);

  const rows = useMemo(() => {
    return labels
      .filter((r) => r.snapshot_date === last)
      .map((r) => ({
        name: r.label_name,
        sub: accountName[r.account_id] || '',
        value: r.subscriber_count || 0,
      }))
      .sort((a, b) => b.value - a.value)
      .slice(0, TOP_N);
  }, [labels, last, accountName]);

  if (labels.length === 0) return <Empty />;

  return (
    <div>
      <div style={{ display: 'flex', marginBottom: 12 }}>
        <span style={{ fontSize: 12, color: G.text3, marginLeft: 'auto' }}>最新: {last}</span>
      </div>

      <Card title={`📊 ラベル別 登録者数（上位${TOP_N}）`}>
        {rows.length === 0 ? (
          <p style={{ color: G.text3, fontSize: 13 }}>ラベルがありません。</p>
        ) : (
          <ResponsiveContainer width="100%" height={Math.max(260, rows.length * 34)}>
            <BarChart data={rows} layout="vertical" margin={{ left: 20, right: 30 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={G.border} horizontal={false} />
              <XAxis type="number" tick={{ fontSize: 12, fill: G.text2 }} />
              <YAxis type="category" dataKey="name" width={180} tick={{ fontSize: 11, fill: G.text1 }} />
              <Tooltip
                formatter={(v) => [`${v} 人`, '登録者']}
                labelFormatter={(label, payload) =>
                  payload?.[0]?.payload?.sub ? `${label}（${payload[0].payload.sub}）` : label
                }
              />
              <Bar dataKey="value" fill={G.primary} radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        )}
      </Card>
    </div>
  );
}
