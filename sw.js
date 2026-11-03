// 홈 화면 앱용 서비스 워커: 페이지·공고 목록은 항상 최신(네트워크 우선), 이미지는 캐시 우선
const VERSION = "careerpick-v3";
const STATIC = "careerpick-static-" + VERSION;
const PAGES = "careerpick-pages-v3";
self.addEventListener("install", e => self.skipWaiting());
self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k.startsWith("careerpick-") && k !== STATIC && k !== PAGES).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener("fetch", e => {
  const req = e.request;
  const url = new URL(req.url);
  if (req.method !== "GET" || url.origin !== location.origin) return;
  if (/\.(png|webp|jpg|svg)$/.test(url.pathname)) {
    e.respondWith(caches.open(STATIC).then(c => c.match(req).then(hit => hit || fetch(req).then(res => { if (res.ok) e.waitUntil(c.put(req, res.clone()).catch(() => {})); return res; }))));
    return;
  }
  // HTML·JSON: 네트워크 우선, 오프라인일 때만 마지막 버전
  e.respondWith(fetch(req).then(res => {
    if (res.ok) { const copy = res.clone(); e.waitUntil(caches.open(PAGES).then(c => c.put(url.pathname, copy)).catch(() => {})); }
    return res;
  }).catch(async () => {
    try { const cached=await (await caches.open(PAGES)).match(url.pathname); if(cached)return cached; } catch(error) {}
    // respondWith must always resolve to a Response, including an uncached offline URL.
    return new Response("오프라인에서 이 자료를 찾을 수 없습니다. 연결 후 다시 확인해 주세요.", {
      status:503,headers:{"Content-Type":"text/plain; charset=utf-8"}
    });
  }));
});

