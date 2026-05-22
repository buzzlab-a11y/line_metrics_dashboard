import { useMemo } from 'react';
import { G } from '../styles/theme';
import { latestDate } from '../hooks/useLineMetrics';
import { Card } from './FriendsTrend';

// ステージ表示順とラベル（collector funnel.py の stage キーと一致）
const STAGE_LABELS = {
  own_line: '自LINE登録',
  parent_inflow: '親LINE流入',
  interview_inflow: '面談LINE流入',
  interview_reserved: '面談予約済',
  contracted: '成約',
};
const STAGE_ORDER = ['own_line', 'parent_inflow', 'interview_inflow', 'interview_reserved', 'contracted'];

/**
 * 講座生別ファネル。各講座生の最新スナップショットを
 * ステージ順に並べ、人数と前ステージからの遷移率を表示。
 * ファネルは kouzasei.yaml ベースで講座生固有のため、自社集客カテゴリでは案内のみ表示。
 */
export default function FunnelView({ funnel, category }) {
  const last = latestDate(funnel);

  const byKouzasei = useMemo(() => {
    const recent = funnel.filter((r) => r.snapshot_date === last);
    const map = new Map();
    for (const r of recent) {
      if (!map.has(r.kouzasei_id)) {
        map.set(r.kouzasei_id, { id: r.kouzasei_id, name: r.display_name, stages: {} });
      }
      map.get(r.kouzasei_id).stages[r.stage] = r.count;
    }
    return [...map.values()];
  }, [funnel, last]);

  if (category === 'self') {
    return (
      <Card>
        <p style={{ color: G.text2, fontSize: 14, lineHeight: 1.7 }}>
          ファネル成約は <b>講座生（kouzasei.yaml で定義したアフィリエイト動線）</b> 専用の指標です。<br />
          上部の <b>「講座生」</b> タブに切り替えると、自LINE登録 → 面談 → 成約 の遷移を確認できます。
        </p>
      </Card>
    );
  }

  if (byKouzasei.length === 0) {
    return (
      <Card>
        <p style={{ color: G.text3, fontSize: 14 }}>
          ファネルデータがまだありません（collector の実行待ち、または kouzasei.yaml に講座生が未定義）。
        </p>
      </Card>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
      <span style={{ fontSize: 12, color: G.text3 }}>最新: {last}</span>
      {byKouzasei.map((k) => {
        const stages = STAGE_ORDER.filter((s) => k.stages[s] !== undefined).map((s) => ({
          key: s,
          label: STAGE_LABELS[s],
          count: k.stages[s] ?? 0,
        }));
        const head = stages[0]?.count || 0;
        return (
          <Card key={k.id} title={`🎯 ${k.name} のファネル`}>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'stretch' }}>
              {stages.map((st, i) => {
                const prev = i > 0 ? stages[i - 1].count : null;
                const conv = prev ? ((st.count / prev) * 100).toFixed(0) : null;
                // バーの相対幅（先頭ステージ基準）
                const widthPct = head ? Math.max((st.count / head) * 100, 4) : 4;
                return (
                  <div key={st.key} style={{ flex: 1, minWidth: 130 }}>
                    {i > 0 && (
                      <div style={{ fontSize: 11, color: G.text3, textAlign: 'center', marginBottom: 4 }}>
                        ↓ {conv ?? '—'}%
                      </div>
                    )}
                    <div
                      style={{
                        background: stageColor(i, stages.length),
                        color: '#fff',
                        borderRadius: G.radius,
                        padding: '14px 10px',
                        textAlign: 'center',
                      }}
                    >
                      <div style={{ fontSize: 11, opacity: 0.9 }}>{st.label}</div>
                      <div style={{ fontSize: 26, fontWeight: 700 }}>{st.count}</div>
                    </div>
                    <div style={{ height: 4, background: G.border, borderRadius: 2, marginTop: 6 }}>
                      <div style={{ width: `${widthPct}%`, height: '100%', background: G.primary, borderRadius: 2 }} />
                    </div>
                  </div>
                );
              })}
            </div>
            {head > 0 && stages.length > 1 && (
              <p style={{ fontSize: 12, color: G.text2, marginTop: 12 }}>
                登録→成約 全体転換率:{' '}
                <b style={{ color: G.success }}>
                  {((stages[stages.length - 1].count / head) * 100).toFixed(1)}%
                </b>
              </p>
            )}
          </Card>
        );
      })}
    </div>
  );
}

function stageColor(i, n) {
  // 先頭(青) → 末尾(緑) のグラデーション風
  const palette = ['#1a73e8', '#1e88c7', '#1f9d8f', '#2aa765', '#34a853'];
  if (n <= palette.length) return palette[Math.min(i, palette.length - 1)];
  return palette[Math.round((i / (n - 1)) * (palette.length - 1))];
}
