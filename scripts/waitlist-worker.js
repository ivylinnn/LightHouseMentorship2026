/**
 * 领航 waitlist —— Cloudflare Worker
 *
 * 网站是静态托管在 GitHub Pages 上的,不能把 Airtable 的 API key 放进前端,
 * 所以表单 POST 到这个 Worker,由它代为写入 Airtable。key 只存在 Worker 的
 * 环境变量里,浏览器看不到。
 *
 * 部署:
 *   1. npm i -g wrangler && wrangler login
 *   2. wrangler deploy scripts/waitlist-worker.js --name linghang-waitlist
 *   3. wrangler secret put AIRTABLE_TOKEN     # 只给 data.records:write 权限的 PAT
 *      wrangler secret put AIRTABLE_BASE      # waitlist 表所在 base 的 app... id
 *   4. 把部署后给出的 URL 填进 index.html 的 WAITLIST_ENDPOINT
 */

const TABLE = "Waitlist";
const ALLOWED = [
  "https://ivylinnn.github.io",
  "https://www.linghangmentorship.com",
  "https://linghangmentorship.com",
];

const cors = (origin) => ({
  "Access-Control-Allow-Origin": ALLOWED.includes(origin) ? origin : ALLOWED[0],
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
  "Access-Control-Max-Age": "86400",
});

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

export default {
  async fetch(request, env) {
    const origin = request.headers.get("Origin") || "";
    if (request.method === "OPTIONS") return new Response(null, { headers: cors(origin) });
    if (request.method !== "POST")
      return new Response("Method not allowed", { status: 405, headers: cors(origin) });
    if (!ALLOWED.includes(origin))
      return new Response("Forbidden", { status: 403, headers: cors(origin) });

    let body;
    try { body = await request.json(); }
    catch { return json({ error: "bad json" }, 400, origin); }

    const email  = String(body.email  || "").trim().toLowerCase();
    const name   = String(body.name   || "").trim().slice(0, 120);
    const region = ["west", "east", "other"].includes(body.region) ? body.region : "other";

    if (!EMAIL.test(email) || email.length > 254) return json({ error: "bad email" }, 400, origin);
    if (!name) return json({ error: "name required" }, 400, origin);

    const api = `https://api.airtable.com/v0/${env.AIRTABLE_BASE}/${encodeURIComponent(TABLE)}`;
    const auth = { Authorization: `Bearer ${env.AIRTABLE_TOKEN}`, "Content-Type": "application/json" };

    // 同一个邮箱重复提交就更新原记录,不再新建一行
    const find = await fetch(
      `${api}?filterByFormula=${encodeURIComponent(`LOWER({Email})='${email.replace(/'/g, "\\'")}'`)}&maxRecords=1`,
      { headers: auth });
    const existing = find.ok ? (await find.json()).records?.[0] : null;

    const fields = {
      Email: email, Name: name, Region: region,
      Language: body.lang === "en" ? "EN" : "ZH",
      Source: String(body.source || "website").slice(0, 60),
    };

    const res = existing
      ? await fetch(`${api}/${existing.id}`, {
          method: "PATCH", headers: auth,
          body: JSON.stringify({ fields, typecast: true }) })
      : await fetch(api, {
          method: "POST", headers: auth,
          body: JSON.stringify({ records: [{ fields }], typecast: true }) });

    if (!res.ok) {
      console.log("airtable error", res.status, (await res.text()).slice(0, 300));
      return json({ error: "upstream" }, 502, origin);
    }
    return json({ ok: true, updated: Boolean(existing) }, 200, origin);
  },
};

function json(obj, status, origin) {
  return new Response(JSON.stringify(obj), {
    status, headers: { ...cors(origin), "Content-Type": "application/json" },
  });
}
