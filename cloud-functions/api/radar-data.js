import { getStore } from "@edgeone/pages-blob";

const allowed = new Set(["items","status","chains","runtime"]);
const keyOf = (k) => `radar/${k}.json`;

export async function onRequestGet(context) {
  const url = new URL(context.request.url);
  const kind = url.searchParams.get("kind") || "items";
  if (!allowed.has(kind)) return new Response(JSON.stringify({error:"bad kind"}), {status:400, headers:{"Content-Type":"application/json"}});
  try {
    const store = getStore({name:"teacher-exam-radar", consistency:"strong"});
    const data = await store.get(keyOf(kind), {type:"json", consistency:"strong"});
    if (data == null) return new Response(JSON.stringify({error:"not initialized"}), {status:404, headers:{"Content-Type":"application/json","Cache-Control":"no-store"}});
    return new Response(JSON.stringify(data), {status:200, headers:{"Content-Type":"application/json; charset=utf-8","Cache-Control":"no-store"}});
  } catch (err) {
    return new Response(JSON.stringify({error:String(err?.message || err)}), {status:500, headers:{"Content-Type":"application/json"}});
  }
}
