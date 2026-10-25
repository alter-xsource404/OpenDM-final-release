// Runs the real extension/background.js against stubbed browser APIs
const assert = require("assert");
let resumed = 0;
const mem = {}, listeners = {}, badge = {}, sent = [];
const store = () => ({ get: async (k) => (typeof k === "string" ? { [k]: mem[k] } : Object.fromEntries(Object.entries(k).map(([a, d]) => [a, mem[a] ?? d]))),
                       set: async (o) => Object.assign(mem, o), remove: async (k) => { delete mem[k]; } });
const ev = (n) => ({ addListener: (f) => (listeners[n] = f) });
globalThis.chrome = {
  storage: { local: store(), session: store(), onChanged: ev("sc") },
  webRequest: { onHeadersReceived: ev("hdr") }, downloads: { onCreated: ev("dl"), cancel: async () => {}, erase: async () => {}, pause: async () => {}, resume: async () => { resumed++; } },
  cookies: { getAll: async () => [{ name: "sid", value: "abc" }] },
  action: { setBadgeText: (o) => (badge[o.tabId] = o.text), setBadgeBackgroundColor() {} },
  tabs: { get: async () => ({ url: "https://site.test/watch", title: "My Clip" }), onUpdated: ev("upd"), onRemoved: ev("rem"),
          sendMessage: async (id, m) => { sent.push([id, m.cmd]); } },
  windows: { getLastFocused: async () => ({ focused: globalThis.__focused !== false }) },
  runtime: { onMessage: ev("msg"), onInstalled: ev("inst"), getURL: (p) => p },
  contextMenus: { create() {}, onClicked: ev("ctx") },
};
const MASTER = `#EXTM3U
#EXT-X-STREAM-INF:BANDWIDTH=900000,RESOLUTION=640x360,FRAME-RATE=30.000
low/index.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=2800000,RESOLUTION=1280x720,FRAME-RATE=60.000
mid/index.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=2800000,RESOLUTION=1280x720
mid/index.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=96000,CODECS="mp4a.40.2"
audio.m3u8
`;
const calls = [];
globalThis.fetch = async (url, opt) => { calls.push([url, opt]);
  if (url.includes("127.0.0.1")) return { ok: true, status: 200 };
  return { ok: true, url: "https://cdn.test/v/master.m3u8", text: async () => MASTER }; };
require(require("path").join(__dirname, "../../extension/background.js"));
const msg = (m, tab = 7) => new Promise((res) => { const r = listeners.msg(m, { tab: { id: tab } }, res); if (r !== true) res("(no reply)"); });
(async () => {
  const hdr = (url, ct, extra = []) => listeners.hdr({ tabId: 7, statusCode: 200, url, responseHeaders: [{ name: "Content-Type", value: ct }, ...extra] });
  hdr("https://cdn.test/v/master.m3u8", "application/vnd.apple.mpegurl");
  hdr("https://cdn.test/v/seg1.ts", "video/MP2T");                                   // ignored
  hdr("https://cdn.test/clip.mp4", "video/mp4", [{ name: "Content-Length", value: "5000000" }]);
  hdr("https://cdn.test/tiny.mp4", "video/mp4", [{ name: "Content-Length", value: "1000" }]);   // too small
  await new Promise((r) => setTimeout(r, 100));
  const list = await msg({ cmd: "list" });
  assert.deepStrictEqual(list.map((m) => m.kind), ["hls", "file"]); assert.strictEqual(list[0].page, "https://site.test/watch");
  assert.strictEqual(badge[7], "2"); assert(sent.some(([id, c]) => id === 7 && c === "media-updated"), "panel notified");
  console.log("PASS detection: HLS + big file kept, segment/tiny ignored, badge=2, panel notified");

  const v = await msg({ cmd: "variants", url: "https://cdn.test/v/master.m3u8" });
  assert.deepStrictEqual(v.map((x) => [x.height, x.bandwidth]), [[720, 2800000], [360, 900000], [0, 96000]]);
  assert.strictEqual(v[0].url, "https://cdn.test/v/mid/index.m3u8"); assert.strictEqual(v[0].fps, 60);
  console.log("PASS variants: sorted best-first, duplicates removed, URLs resolved, fps parsed:", JSON.stringify(v.map((x) => `${x.height}p/${x.bandwidth}`)));
  assert.deepStrictEqual(await msg({ cmd: "variants", url: "https://evil.test/x.m3u8" }), []);
  assert.deepStrictEqual(await msg({ cmd: "variants", url: "https://cdn.test/v/master.m3u8" }, 99), []);
  console.log("PASS variants refuses URLs this tab never loaded (and other tabs)");

  await msg({ cmd: "found", url: "https://cdn.test/other.mp4" }); assert.strictEqual((await msg({ cmd: "list" })).length, 3);
  assert.strictEqual(await msg({ cmd: "found", url: "javascript:alert(1)" }), "(no reply)");
  console.log("PASS content-script 'found' adds http(s) videos only");

  // audio/video pairing (Facebook-style DASH: separate small audio file + video file)
  const efg = (tag) => Buffer.from(JSON.stringify({ vencode_tag: tag })).toString("base64url");
  hdr("https://fb.test/v/a.mp4?efg=" + efg("dash_ln_heaac_vbr3_audio") + "&bytestart=0&byteend=999", "video/mp4", [{ name: "Content-Length", value: "1000" }]);
  hdr("https://fb.test/v/v.mp4?efg=" + efg("dash_h264-basic-gen2_1080p") + "&bytestart=0&byteend=999", "video/mp4", [{ name: "Content-Length", value: "1000" }]);
  await new Promise((r) => setTimeout(r, 100));
  const pl = await msg({ cmd: "list" });
  const vid = pl.find((m) => m.role === "video");
  assert(vid && /a\.mp4/.test(vid.audioUrl), "video paired with its small audio stream");
  console.log("PASS audio/video roles detected, small audio kept, video paired with audioUrl");

  mem.token = "TKN"; mem.port = 6800;
  const r = await msg({ cmd: "send", job: { url: "https://cdn.test/v/master.m3u8", kind: "hls", quality: 720, bandwidth: 2800000, referer: "https://site.test/watch", filename: "My Clip" } });
  const post = calls.find(([u]) => u === "http://127.0.0.1:6800/add");
  const body = JSON.parse(post[1].body);
  assert(r.ok); assert.strictEqual(post[1].headers["X-OpenDM-Token"], "TKN");
  assert.deepStrictEqual([body.kind, body.quality, body.bandwidth, body.cookie], ["hls", 720, 2800000, "sid=abc"]);
  console.log("PASS send: POST /add with token, quality=720, bandwidth=2800000, cookie, kind=hls");
  // phantom-download guard: only fresh downloads that follow a real user gesture are taken over
  const posts = () => calls.filter(([u]) => u === "http://127.0.0.1:6800/add").length;
  const dl = (o) => listeners.dl({ id: 1, state: "in_progress", startTime: new Date().toISOString(), referrer: "https://site.test/p", ...o });
  const wait = () => new Promise((r) => setTimeout(r, 50));
  let n = posts(); await dl({ url: "https://cdn.test/a.png" }); await wait();
  assert.strictEqual(posts(), n); console.log("PASS no user gesture -> page-started download left to the browser");
  await msg({ cmd: "gesture" }); await dl({ url: "https://cdn.test/old.msi", startTime: new Date(Date.now() - 60000).toISOString() }); await wait();
  assert.strictEqual(posts(), n); console.log("PASS old/restored download ignored");
  globalThis.__focused = false; await dl({ url: "https://cdn.test/bg.zip" }); await wait(); globalThis.__focused = true;
  assert.strictEqual(posts(), n); console.log("PASS unfocused browser window ignored");
  await dl({ url: "https://cdn.test/real.zip" }); await wait();
  assert.strictEqual(posts(), n + 1); console.log("PASS fresh download after a gesture is sent");
  await dl({ url: "https://cdn.test/real.zip" }); await wait();
  assert.strictEqual(posts(), n + 1); console.log("PASS duplicate ignored");
  for (const x of ["b", "c", "d", "e"]) await dl({ url: "https://cdn.test/" + x + ".zip" });
  await wait(); assert.strictEqual(posts(), n + 3); console.log("PASS burst of downloads capped at 3");
  delete mem.token; const bad = await msg({ cmd: "send", job: { url: "https://x.test/a.zip" } });
  assert(!bad.ok && /not paired/.test(bad.error)); console.log("PASS send without pairing -> clear error:", bad.error);
})().catch((e) => { console.error("FAIL", e); process.exit(1); });
