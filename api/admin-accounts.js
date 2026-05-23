// アカウント管理画面の書込API（POST /api/admin-accounts）。
// 管理者パスワード検証 → service_key で line_accounts の category / tracked を更新。
// Vercel サーバーレス関数。service_key はサーバー側に留まり、ブラウザには出さない。
//
// 必要な環境変数（Vercel）:
//   ADMIN_PASSWORD        管理画面のパスワード
//   SUPABASE_URL          Supabase プロジェクトURL
//   SUPABASE_SERVICE_KEY  service_role キー
//
// リクエスト: POST { password, account_id, category?, tracked? }
import { createClient } from '@supabase/supabase-js';

function parseBody(req) {
  let body = req.body;
  if (body == null) return {};
  if (typeof body === 'string') {
    try {
      return JSON.parse(body);
    } catch {
      return {};
    }
  }
  return body;
}

export default async function handler(req, res) {
  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'POST only' });
  }
  const body = parseBody(req);

  const password = process.env.ADMIN_PASSWORD;
  if (!password || body.password !== password) {
    return res.status(401).json({ error: 'unauthorized' });
  }

  const accountId = body.account_id;
  if (!accountId) {
    return res.status(400).json({ error: 'account_id required' });
  }

  // 更新するフィールドだけ組み立て（不正値ガード）
  const patch = {};
  if (body.category !== undefined) {
    if (!['self', 'student'].includes(body.category)) {
      return res.status(400).json({ error: 'category must be self|student' });
    }
    patch.category = body.category;
  }
  if (body.tracked !== undefined) {
    patch.tracked = Boolean(body.tracked);
  }
  if (Object.keys(patch).length === 0) {
    return res.status(400).json({ error: 'nothing to update' });
  }
  patch.updated_at = new Date().toISOString();

  const url = process.env.SUPABASE_URL;
  const key = process.env.SUPABASE_SERVICE_KEY;
  if (!url || !key) {
    return res.status(500).json({ error: 'server not configured' });
  }
  const sb = createClient(url, key);
  const { data, error } = await sb
    .from('line_accounts')
    .update(patch)
    .eq('account_id', accountId)
    .select('account_id,category,tracked');
  if (error) {
    return res.status(500).json({ error: error.message });
  }
  if (!data || data.length === 0) {
    return res.status(404).json({ error: 'account not found' });
  }
  return res.status(200).json({ ok: true, account: data[0] });
}
