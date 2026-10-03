import { getStore } from "@edgeone/pages-blob";
import { gunzipSync } from "node:zlib";

const allowed = new Set(["items","status","chains","runtime"]);
const keyOf = (k) => `radar/${k}.json`;

export async function onRequestPost(context) {
  const url = new URL(context.request.url);
  const kind = url.searchParams.get("kind") || "";
  if (!allowed.has(kind)) return new Response("bad kind", {status:400});
  const expected = context.env?.RADAR_INTERNAL_TOKEN || process.env.RADAR_INTERNAL_TOKEN || "teacher-radar-internal-v1";
  const got = context.request.headers.get("X-Radar-Token") || "";
  if (got !== expected) return new Response("forbidden", {status:403});
  try {
    let buf = Buffer.from(await context.request.arrayBuffer());
    if ((context.request.headers.get("Content-Encoding") || "").toLowerCase().includes("gzip")) buf = gunzipSync(buf);
    const obj = JSON.parse(buf.toString("utf8"));
    const store = getStore({name:"teacher-exam-radar", consistency:"strong"});
    await store.setJSON(keyOf(kind), obj);
    return new Response(JSON.stringify({ok:true, kind}), {status:200, headers:{"Content-Type":"application/json"}});
  } catch (err) {
    return new Response(JSON.stringify({ok:false,error:String(err?.message || err)}), {status:500, headers:{"Content-Type":"application/json"}});
  }
}
