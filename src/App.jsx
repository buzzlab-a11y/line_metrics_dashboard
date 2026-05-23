import { useMemo, useState } from 'react';
import { Users, Filter, Send, GitBranch, RefreshCw, Settings, ArrowLeft } from 'lucide-react';
import { G } from './styles/theme';
import { useLineMetrics } from './hooks/useLineMetrics';
import FriendsTrend from './components/FriendsTrend';
import InflowBySource from './components/InflowBySource';
import MessagePerformance from './components/MessagePerformance';
import FunnelView from './components/FunnelView';
import AccountAdmin from './components/AccountAdmin';

const CATEGORIES = [
  { id: 'self', label: '自社集客' },
  { id: 'student', label: '講座生' },
];

const METRICS = [
  { id: 'friends', label: '友だち数・推移', icon: Users },
  { id: 'inflow', label: '流入経路', icon: Filter },
  { id: 'messages', label: '配信パフォーマンス', icon: Send },
  { id: 'funnel', label: 'ファネル成約', icon: GitBranch },
];

export default function App() {
  const data = useLineMetrics();
  const [category, setCategory] = useState('self');
  const [metric, setMetric] = useState('friends');
  const [accountId, setAccountId] = useState('all'); // 'all' | 個別 account_id
  const [view, setView] = useState('dashboard'); // 'dashboard' | 'admin'

  // メイン表示は tracked=true のアカウントのみ
  const accountsInCat = useMemo(
    () => data.accounts.filter((a) => a.category === category && a.tracked),
    [data.accounts, category]
  );

  // カテゴリを変えたらアカウント選択をリセット
  const onCategory = (c) => {
    setCategory(c);
    setAccountId('all');
  };

  // 表示対象の account_id 集合（全体 or 個別）
  const accountIds = useMemo(() => {
    if (accountId !== 'all') return new Set([accountId]);
    return new Set(accountsInCat.map((a) => a.account_id));
  }, [accountsInCat, accountId]);

  // 個別選択時は対象アカウントだけに絞ったマスタを渡す
  const scopedAccounts = useMemo(
    () => (accountId === 'all' ? accountsInCat : accountsInCat.filter((a) => a.account_id === accountId)),
    [accountsInCat, accountId]
  );

  const filtered = useMemo(
    () => ({
      accounts: scopedAccounts,
      daily: data.daily.filter((r) => accountIds.has(r.account_id)),
      inflow: data.inflow.filter((r) => accountIds.has(r.account_id)),
      messages: data.messages.filter((r) => accountIds.has(r.account_id)),
      funnel: data.funnel, // ファネルは講座生固定（kouzasei.yaml ベース）
    }),
    [scopedAccounts, accountIds, data]
  );

  return (
    <div style={{ maxWidth: 1180, margin: '0 auto', padding: '24px 20px 80px' }}>
      <header
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: 20,
          flexWrap: 'wrap',
          gap: 12,
        }}
      >
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 700, color: G.text1 }}>
            📊 LINE数字計測ダッシュボード
          </h1>
          <p style={{ color: G.text2, fontSize: 13, marginTop: 4 }}>
            UTAGE 連携・日次スナップショット
          </p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button
            onClick={data.reload}
            style={{
              display: 'flex', alignItems: 'center', gap: 6,
              background: G.surface, border: `1px solid ${G.border}`,
              borderRadius: G.radiusPill, padding: '8px 16px',
              color: G.text2, fontSize: 13, boxShadow: G.shadow1,
            }}
          >
            <RefreshCw size={15} /> 更新
          </button>
          <button
            onClick={() => setView(view === 'admin' ? 'dashboard' : 'admin')}
            style={{
              display: 'flex', alignItems: 'center', gap: 6,
              background: view === 'admin' ? G.primaryContainer : G.surface,
              border: `1px solid ${view === 'admin' ? G.primary : G.border}`,
              borderRadius: G.radiusPill, padding: '8px 16px',
              color: view === 'admin' ? G.primary : G.text2, fontSize: 13, boxShadow: G.shadow1,
            }}
          >
            {view === 'admin' ? <ArrowLeft size={15} /> : <Settings size={15} />}
            {view === 'admin' ? 'ダッシュへ戻る' : 'アカウント管理'}
          </button>
        </div>
      </header>

      {view === 'admin' && <AccountAdmin accounts={data.accounts} onSaved={data.reload} />}
      {view === 'dashboard' && (
      <>
      {/* === dashboard body === */}

      {/* カテゴリ切替（自社集客 / 講座生） */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        {CATEGORIES.map((c) => {
          const active = category === c.id;
          const count = data.accounts.filter((a) => a.category === c.id && a.tracked).length;
          return (
            <button
              key={c.id}
              onClick={() => onCategory(c.id)}
              style={{
                flex: '0 0 auto',
                padding: '10px 22px',
                borderRadius: G.radiusMd,
                border: `1px solid ${active ? G.primary : G.border}`,
                background: active ? G.primary : G.surface,
                color: active ? G.onPrimary : G.text2,
                fontWeight: 600,
                fontSize: 14,
                boxShadow: active ? G.shadow1 : 'none',
              }}
            >
              {c.label}
              <span style={{ marginLeft: 8, opacity: 0.8, fontSize: 12 }}>{count}</span>
            </button>
          );
        })}
      </div>

      {/* アカウント切替（全体 / 個別） */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16, flexWrap: 'wrap' }}>
        <span style={{ fontSize: 12.5, color: G.text2 }}>アカウント:</span>
        <select
          value={accountId}
          onChange={(e) => setAccountId(e.target.value)}
          style={{
            padding: '7px 14px',
            borderRadius: G.radius,
            border: `1px solid ${G.border}`,
            background: G.surface,
            color: G.text1,
            fontSize: 13,
            fontWeight: 600,
            maxWidth: 320,
          }}
        >
          <option value="all">全体（{accountsInCat.length}アカウント合計）</option>
          {accountsInCat.map((a) => (
            <option key={a.account_id} value={a.account_id}>
              {a.name}
            </option>
          ))}
        </select>
      </div>

      {/* 指標タブ */}
      <div
        style={{
          display: 'flex',
          gap: 2,
          borderBottom: `2px solid ${G.border}`,
          marginBottom: 20,
          flexWrap: 'wrap',
        }}
      >
        {METRICS.map((m) => {
          const active = metric === m.id;
          const Icon = m.icon;
          return (
            <button
              key={m.id}
              onClick={() => setMetric(m.id)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                padding: '10px 16px',
                background: 'none',
                border: 'none',
                borderBottom: `3px solid ${active ? G.primary : 'transparent'}`,
                color: active ? G.primary : G.text2,
                fontWeight: 600,
                fontSize: 13.5,
                marginBottom: -2,
              }}
            >
              <Icon size={16} /> {m.label}
            </button>
          );
        })}
      </div>

      {data.loading && <Notice>読み込み中…</Notice>}
      {data.error && (
        <Notice error>
          データ取得エラー: {data.error}
          <div style={{ fontSize: 12, marginTop: 6, color: G.text3 }}>
            .env の VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY と、スキーマ適用を確認してください。
          </div>
        </Notice>
      )}

      {!data.loading && !data.error && (
        <>
          {metric === 'friends' && <FriendsTrend daily={filtered.daily} accounts={filtered.accounts} />}
          {metric === 'inflow' && <InflowBySource inflow={filtered.inflow} accounts={filtered.accounts} />}
          {metric === 'messages' && <MessagePerformance messages={filtered.messages} accounts={filtered.accounts} />}
          {metric === 'funnel' && (
            <FunnelView funnel={filtered.funnel} category={category} />
          )}
        </>
      )}
      </>
      )}
    </div>
  );
}

function Notice({ children, error }) {
  return (
    <div
      style={{
        background: error ? G.errorContainer : G.surfaceVariant,
        color: error ? G.error : G.text2,
        borderRadius: G.radiusMd,
        padding: '16px 20px',
        fontSize: 14,
      }}
    >
      {children}
    </div>
  );
}
