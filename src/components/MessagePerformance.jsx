import { useMemo } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts';
import { G } from '../styles/theme';
import { latestDate } from '../hooks/useLineMetrics';
import { Card, Empty } from './FriendsTrend';

const TOP_N = 12;

/**
 * 配信パフォーマンス。最新スナップショットのメッセージ統計を
 * クリック率降順で表示（上位を棒グラフ＋全件テーブル）。
 */
export default function MessagePerformance({ messages, accounts }) {
  const last = latestDate(messages);

  const accountName = useMemo(() => {
    const m = {};
    for (const a of accounts) m[a.account_id] = a.name;
    return m;
  }, [accounts]);

  const rows = useMemo(() => {
    return messages
      .filter((r) => r.snapshot_date === last && (r.send_count || 0) > 0)
      .map((r) => ({
        account: accountName[r.account_id] || r.account_id,
        scenario: r.scenario_title || '',
        title: r.message_title || r.message_id,
        send: r.send_count || 0,
        click: r.click_count || 0,
        rate: Number(r.click_rate || 0),
      }))
      .sort((a, b) => b.rate - a.rate);
  }, [messages, last, accountName]);

  const chartData = useMemo(
    () =>
      rows.slice(0, TOP_N).map((r) => ({
        name: r.title.length > 16 ? r.title.slice(0, 16) + '…' : r.title,
        クリック率: Number(r.rate.toFixed(1)),
      })),
    [rows]
  );

  const totals = useMemo(() => {
    const send = rows.reduce((s, r) => s + r.send, 0);
    const click = rows.reduce((s, r) => s + r.click, 0);
    return { send, click, rate: send ? ((click / send) * 100).toFixed(1) : '0.0' };
  }, [rows]);

  if (messages.length === 0) return <Empty />;

  return (
    <div>
      <div style={{ display: 'flex', gap: 12, marginBottom: 16, flexWrap: 'wrap' }}>
        <Kpi label="総配信数" value={totals.send.toLocaleString()} />
        <Kpi label="総クリック数" value={totals.click.toLocaleString()} />
        <Kpi label="平均クリック率" value={`${totals.rate}%`} color={G.success} />
        <span style={{ fontSize: 12, color: G.text3, marginLeft: 'auto', alignSelf: 'center' }}>
          最新: {last}
        </span>
      </div>

      <Card title={`📊 クリック率 上位${TOP_N}メッセージ`}>
        {chartData.length === 0 ? (
          <p style={{ color: G.text3, fontSize: 13 }}>配信実績のあるメッセージがありません。</p>
        ) : (
          <ResponsiveContainer width="100%" height={Math.max(240, chartData.length * 32)}>
            <BarChart data={chartData} layout="vertical" margin={{ left: 20, right: 40 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={G.border} horizontal={false} />
              <XAxis type="number" unit="%" tick={{ fontSize: 12, fill: G.text2 }} />
              <YAxis type="category" dataKey="name" width={150} tick={{ fontSize: 11, fill: G.text1 }} />
              <Tooltip formatter={(v) => [`${v}%`, 'クリック率']} />
              <Bar dataKey="クリック率" fill={G.success} radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        )}
      </Card>

      <h3 style={{ fontSize: 14, color: G.text2, margin: '20px 0 10px', fontWeight: 700 }}>
        全メッセージ統計
      </h3>
      <div style={{ overflowX: 'auto', background: G.surface, borderRadius: G.radiusMd, border: `1px solid ${G.border}` }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
          <thead>
            <tr style={{ background: G.surfaceVariant }}>
              <Th>アカウント</Th>
              <Th>シナリオ</Th>
              <Th>メッセージ</Th>
              <Th right>配信</Th>
              <Th right>クリック</Th>
              <Th right>クリック率</Th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i} style={{ borderTop: `1px solid ${G.border}` }}>
                <Td>{r.account}</Td>
                <Td muted>{r.scenario}</Td>
                <Td>{r.title}</Td>
                <Td right>{r.send.toLocaleString()}</Td>
                <Td right>{r.click.toLocaleString()}</Td>
                <Td right strong>{r.rate.toFixed(1)}%</Td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Kpi({ label, value, color }) {
  return (
    <div
      style={{
        background: G.surface,
        border: `1px solid ${G.border}`,
        borderRadius: G.radiusMd,
        padding: '12px 20px',
        boxShadow: G.shadow1,
        minWidth: 130,
      }}
    >
      <div style={{ fontSize: 12, color: G.text3 }}>{label}</div>
      <div style={{ fontSize: 22, fontWeight: 700, color: color || G.primary }}>{value}</div>
    </div>
  );
}

function Th({ children, right }) {
  return (
    <th style={{ padding: '10px 12px', textAlign: right ? 'right' : 'left', fontWeight: 600, color: G.text2, whiteSpace: 'nowrap' }}>
      {children}
    </th>
  );
}

function Td({ children, right, muted, strong }) {
  return (
    <td
      style={{
        padding: '8px 12px',
        textAlign: right ? 'right' : 'left',
        color: strong ? G.primary : muted ? G.text3 : G.text1,
        fontWeight: strong ? 700 : 400,
        fontVariantNumeric: right ? 'tabular-nums' : 'normal',
        maxWidth: 240,
        overflow: 'hidden',
        textOverflow: 'ellipsis',
        whiteSpace: 'nowrap',
      }}
    >
      {children}
    </td>
  );
}
