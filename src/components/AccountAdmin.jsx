import { useMemo, useState } from 'react';
import { G } from '../styles/theme';

const PW_KEY = 'lmd_admin_pw';

/**
 * アカウント管理画面。UTAGE全アカウント（collectorが自動検出）を一覧し、
 * 追跡(tracked)ON/OFF と 分類(self/student) を変更する。
 * 書込は /api/admin-accounts（パスワード検証＋service_key）経由。anonには書込権限を持たせない。
 */
export default function AccountAdmin({ accounts, onSaved }) {
  const [password, setPassword] = useState(() => sessionStorage.getItem(PW_KEY) || '');
  const [rows, setRows] = useState(() => accounts.map((a) => ({ ...a })));
  const [q, setQ] = useState('');
  const [savingId, setSavingId] = useState(null);
  const [msg, setMsg] = useState(null); // {type:'ok'|'err', text}

  const filtered = useMemo(() => {
    const sorted = [...rows].sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0));
    if (!q.trim()) return sorted;
    const k = q.trim().toLowerCase();
    return sorted.filter((r) => (r.name || '').toLowerCase().includes(k) || (r.account_id || '').toLowerCase().includes(k));
  }, [rows, q]);

  const trackedCount = rows.filter((r) => r.tracked).length;

  async function save(accountId, patch) {
    if (!password) {
      setMsg({ type: 'err', text: '管理パスワードを入力してください' });
      return;
    }
    setSavingId(accountId);
    setMsg(null);
    try {
      const res = await fetch('/api/admin-accounts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password, account_id: accountId, ...patch }),
      });
      if (res.status === 401) {
        setMsg({ type: 'err', text: 'パスワードが違います' });
        return;
      }
      if (!res.ok) {
        const j = await res.json().catch(() => ({}));
        setMsg({ type: 'err', text: `保存失敗: ${j.error || res.status}` });
        return;
      }
      sessionStorage.setItem(PW_KEY, password);
      // ローカル反映
      setRows((prev) => prev.map((r) => (r.account_id === accountId ? { ...r, ...patch } : r)));
      setMsg({ type: 'ok', text: '保存しました' });
      if (onSaved) onSaved();
    } catch (e) {
      setMsg({ type: 'err', text: `通信エラー: ${e.message}` });
    } finally {
      setSavingId(null);
    }
  }

  return (
    <div>
      <h2 style={{ fontSize: 18, fontWeight: 700, color: G.text1, marginBottom: 6 }}>アカウント管理</h2>
      <p style={{ fontSize: 13, color: G.text2, marginBottom: 16 }}>
        UTAGEの全アカウントを自動検出。<b>追跡ON</b>にしたものだけがダッシュボードで集計されます。新しいLINEは自動でここに出ます。
      </p>

      <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 16, flexWrap: 'wrap' }}>
        <input
          type="password"
          placeholder="管理パスワード"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          style={{
            padding: '8px 12px', borderRadius: G.radius, border: `1px solid ${G.border}`,
            fontSize: 13, minWidth: 200,
          }}
        />
        <input
          type="text"
          placeholder="名前 / IDで絞り込み"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          style={{
            padding: '8px 12px', borderRadius: G.radius, border: `1px solid ${G.border}`,
            fontSize: 13, minWidth: 200,
          }}
        />
        <span style={{ fontSize: 12.5, color: G.text2 }}>
          全 {rows.length} / 追跡 {trackedCount}
        </span>
        {msg && (
          <span style={{ fontSize: 12.5, color: msg.type === 'ok' ? G.success : G.error, fontWeight: 600 }}>
            {msg.text}
          </span>
        )}
      </div>

      <div style={{ overflowX: 'auto', background: G.surface, borderRadius: G.radiusMd, border: `1px solid ${G.border}` }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ background: G.surfaceVariant }}>
              <Th>追跡</Th>
              <Th>アカウント名</Th>
              <Th>グループ</Th>
              <Th>分類</Th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((r) => (
              <tr key={r.account_id} style={{ borderTop: `1px solid ${G.border}`, opacity: savingId === r.account_id ? 0.5 : 1 }}>
                <Td>
                  <input
                    type="checkbox"
                    checked={!!r.tracked}
                    disabled={savingId === r.account_id}
                    onChange={(e) => save(r.account_id, { tracked: e.target.checked })}
                    style={{ width: 18, height: 18, cursor: 'pointer' }}
                  />
                </Td>
                <Td>
                  <span style={{ color: r.tracked ? G.text1 : G.text3 }}>{r.name}</span>
                </Td>
                <Td muted>{r.group_name || '—'}</Td>
                <Td>
                  <select
                    value={r.category}
                    disabled={savingId === r.account_id}
                    onChange={(e) => save(r.account_id, { category: e.target.value })}
                    style={{
                      padding: '5px 10px', borderRadius: G.radius, border: `1px solid ${G.border}`,
                      fontSize: 12.5, background: G.surface, color: G.text1,
                    }}
                  >
                    <option value="self">自社集客</option>
                    <option value="student">講座生</option>
                  </select>
                </Td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p style={{ fontSize: 11.5, color: G.text3, marginTop: 10 }}>
        ※ 変更は即保存されます。新規アカウントを追跡したら、次回の日次収集（または手動収集）で数字が入ります。
      </p>
    </div>
  );
}

function Th({ children }) {
  return <th style={{ padding: '10px 14px', textAlign: 'left', fontWeight: 600, color: G.text2, whiteSpace: 'nowrap' }}>{children}</th>;
}
function Td({ children, muted }) {
  return <td style={{ padding: '8px 14px', color: muted ? G.text3 : G.text1 }}>{children}</td>;
}
