// Network-first pages/data; cache completion is tracked across worker replacement.
const VERSION="careerpick-v3",STATIC="careerpick-static-"+VERSION,PAGES="careerpick-pages-v3";
self.addEventListener('install',()=>self.skipWaiting());
self.addEventListener('activate',e=>e.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k.startsWith('careerpick-')&&k!==STATIC&&k!==PAGES).map(k=>caches.delete(k)))).then(()=>self.clients.claim())));
async function cpCachePut(name,key,response){
 const headers=new Headers(response.headers);headers.delete('Content-Encoding');headers.delete('Content-Length');headers.set('X-CareerPick-Cached-At',new Date().toISOString());
 const saved=new Response(response.body,{status:response.status,statusText:response.statusText,headers});
 await (await caches.open(name)).put(key,saved);
}
async function cpCacheFallback(name,key){
 try{const cached=await (await caches.open(name)).match(key);if(!cached)return null;
  const headers=new Headers(cached.headers);headers.delete('Content-Encoding');headers.delete('Content-Length');headers.set('X-CareerPick-Cache','fallback');
  return new Response(cached.body,{status:cached.status,statusText:cached.statusText,headers});
 }catch(_){return null;}
}
self.addEventListener('fetch',e=>{
 const req=e.request,url=new URL(req.url);if(req.method!=='GET'||url.origin!==location.origin)return;
 const image=/\.(png|webp|jpg|svg)$/.test(url.pathname),code=/\.(js|css)$/.test(url.pathname)||req.mode==='navigate'||url.pathname.endsWith('/')||url.pathname.endsWith('.html');
 // Code query versions remain distinct; timestamped JSON requests share their data path.
 const key=/\.(js|css)$/.test(url.pathname)?url.href:url.pathname;
 const name=image?STATIC:PAGES;
 if(image){const result=(async()=>{try{const hit=await (await caches.open(STATIC)).match(key);if(hit)return hit;}catch(_){}try{const res=await fetch(req);if(res.ok)await cpCachePut(STATIC,key,res.clone()).catch(()=>{});return res;}catch(_){return new Response('',{status:503});}})();e.waitUntil(result.then(()=>{}));e.respondWith(result);return;}
 const network=fetch(req);
 const stored=network.then(res=>res.ok?cpCachePut(name,key,res.clone()):undefined).catch(()=>{});
 e.waitUntil(stored);
 e.respondWith((async()=>{
  try{const res=await network;if(res.ok){if(code)await stored;return res;}return await cpCacheFallback(name,key)||res;}
  catch(_){return await cpCacheFallback(name,key)||new Response('오프라인에서 이 자료를 찾을 수 없습니다. 연결 후 다시 확인해 주세요.',{status:503,headers:{'Content-Type':'text/plain; charset=utf-8'}});}
 })());
});
