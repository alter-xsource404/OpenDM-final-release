// OpenDM browser integration (Chrome / Edge / Brave / Firefox, Manifest V3) - v1.7 (one persistent native-messaging connection instead of a new host process per message); v1.6: capture rules come from OpenDM's Configuration; v1.5: audio/video stream pairing, no sniffer panel
const api = globalThis.browser ?? globalThis.chrome;
const DEFAULTS = { port: 6800, token: "", intercept: true, minSizeKB: 0 };

const getCfg = async () => ({ ...DEFAULTS, ...(await api.storage.local.get(DEFAULTS)) });

async function cookieHeader(url) {
  try {
    const cs = await api.cookies.getAll({ url });
    return cs.map((c) => `${c.name}=${c.value}`).join("; ");
  } catch { return ""; }
}

// ---- talking to OpenDM -------------------------------------------------------------------
// Preferred: the native-messaging host that OpenDM registers with the browser by itself. It needs no port and no
// pairing token, only trusts this extension's ID, and starts OpenDM if it isn't running.
// Fallback: the local server on 127.0.0.1 with a pairing token pasted into the options page.
const NATIVE_HOST = "org.opendm.nativehost";
const withTimeout = (p, ms) => Promise.race([p, new Promise((_, rej) => setTimeout(() => rej(new Error("timed out")), ms))]);
// v1.7: sendNativeMessage starts a NEW host process for every message (for a packaged OpenDM that means unpacking and starting the whole
// program each time: seconds). connectNative keeps one host process alive; messages carry an id, the host echoes it, so calls can overlap
// (a slow "formats" lookup never blocks a download hand-over). Falls back to sendNativeMessage where connectNative doesn't exist.
let nPort = null, nSeq = 0;
const nPending = new Map();
function nativePort() {
  if (nPort) return nPort;
  const p = api.runtime.connectNative(NATIVE_HOST);
  p.onMessage.addListener((m) => {
    const w = m && nPending.get(m.id);
    if (!w) return;
    nPending.delete(m.id); clearTimeout(w.t);
    const { id, ...reply } = m; w.res(reply);
  });
  p.onDisconnect.addListener(() => {
    const err = new Error((api.runtime.lastError && api.runtime.lastError.message) || "Native host has exited.");
    if (nPort === p) nPort = null;
    for (const [id, w] of nPending) { clearTimeout(w.t); w.rej(err); nPending.delete(id); }
  });
  return (nPort = p);
}
function viaPort(msg, ms) {
  return new Promise((res, rej) => {
    const id = ++nSeq, t = setTimeout(() => { nPending.delete(id); rej(new Error("timed out")); }, ms);
    nPending.set(id, { res, rej, t });
    const post = () => nativePort().postMessage({ ...msg, id });
    try { post(); } catch { nPort = null; try { post(); } catch (e) { nPending.delete(id); clearTimeout(t); rej(e); } }   // a stale port: reconnect once
  });
}
const nativeCall = (msg, ms = 30000) =>   // 30 s: OpenDM may need time to start
  typeof api.runtime.connectNative === "function" ? viaPort(msg, ms) : withTimeout(Promise.resolve(api.runtime.sendNativeMessage(NATIVE_HOST, msg)), ms);

async function sendToOpenDM(job) {
  const full = { ...job, ts: Date.now(), cookie: await cookieHeader(job.url), userAgent: navigator.userAgent };
  let reply = null, nativeError = "";
  try { reply = await nativeCall({ cmd: "add", job: full }); } catch (e) { nativeError = e?.message || String(e); }  // host not registered / not allowed
  if (reply) {
    if (reply.ok) return;
    throw new Error(reply.error || "OpenDM refused the download");  // OpenDM answered: don't retry another way
  }
  const cfg = await getCfg();
  if (!cfg.token) throw new Error("not paired: OpenDM's browser integration isn't registered yet" + (nativeError ? ` (${nativeError})` : ""));
  const r = await fetch(`http://127.0.0.1:${cfg.port}/add`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-OpenDM-Token": cfg.token },
    body: JSON.stringify(full),
  });
  if (!r.ok) throw new Error("OpenDM replied " + r.status);
}

async function connectionStatus() {
  let nativeError = "";
  try { const r = await nativeCall({ cmd: "ping" }); if (r?.ok) return { mode: "native", running: !!r.running, version: r.version, autostart: r.autostart !== false }; }
  catch (e) { nativeError = e?.message || String(e); }
  const cfg = await getCfg();
  if (cfg.token) {
    try {
      const r = await fetch(`http://127.0.0.1:${cfg.port}/ping`, { headers: { "X-OpenDM-Token": cfg.token } });
      return r.ok ? { mode: "manual", running: true } : { mode: "none", error: r.status === 401 ? "Wrong pairing token" : "OpenDM replied " + r.status };
    } catch { /* not running */ }
  }
  return { mode: "none", error: nativeError || "OpenDM's browser integration isn't registered yet" };
}

// ---------------- Which downloads does OpenDM take over? (rules live in OpenDM > Options > Configuration) ----------------
// OpenDM hands its rules over on request (native host "config", or POST /config with the pairing token). The last answer is kept, so the rules
// still apply while OpenDM isn't running. Until the first answer these built-in defaults apply: images and web files are never captured.
const DEFAULT_CAP = {
  intercept: true, capture_types: [], capture_unknown: true, exclude_sites: [], min_size_kb: 0, key_prevent: "alt", key_force: "none", browsers: {},
  skip_types: "jpg jpeg png gif webp bmp svg ico avif heic tif tiff css js mjs map html htm json xml woff woff2 ttf otf".split(" "),
  ctx_link: true, ctx_media: true, video_button: true,
};
let capCache = { t: 0, cfg: null };

async function buildMenus(cap) {
  try { await api.contextMenus.removeAll?.(); } catch {}
  if (cap.ctx_link !== false) api.contextMenus.create({ id: "dl-link", title: "Download link with OpenDM", contexts: ["link"] });
  if (cap.ctx_media !== false) api.contextMenus.create({ id: "dl-media", title: "Download media with OpenDM", contexts: ["video", "audio", "image"] });
}

async function getCapture(maxAge = 60e3) {
  if (capCache.cfg && Date.now() - capCache.t < maxAge) return capCache.cfg;
  let fresh = null;
  try { const r = await nativeCall({ cmd: "config" }); if (r?.ok && r.config) fresh = r.config; } catch {}
  if (!fresh) {
    try {
      const c = await getCfg();
      if (c.token) {
        const r = await fetch(`http://127.0.0.1:${c.port}/config`, { method: "POST", headers: { "Content-Type": "application/json", "X-OpenDM-Token": c.token }, body: "{}" });
        if (r.ok) fresh = await r.json();
      }
    } catch {}
  }
  const stored = (await api.storage.local.get({ capture: null })).capture;
  if (fresh) {
    if (JSON.stringify(fresh) !== JSON.stringify(stored)) await api.storage.local.set({ capture: fresh });
    if (!stored || stored.ctx_link !== fresh.ctx_link || stored.ctx_media !== fresh.ctx_media) buildMenus({ ...DEFAULT_CAP, ...fresh });
  }
  const cfg = { ...DEFAULT_CAP, ...(fresh || stored || {}) };
  capCache = { t: Date.now(), cfg };
  return cfg;
}

const extOf = (s) => { const m = /\.([a-z0-9]{1,10})$/i.exec(String(s || "").split(/[?#]/)[0]); return m ? m[1].toLowerCase() : ""; };
const hostMatch = (host, pats) => (pats || []).some((p) => {
  const q = p.replace(/^\*\./, "");
  return host === q || host.endsWith("." + q) || (p.includes("*") && new RegExp("^" + p.replace(/[.+?^${}()|[\]\\]/g, "\\$&").replace(/\*/g, ".*") + "$").test(host));
});
// Same rules as OpenDM's capture_decision(): excluded site -> no; skip list -> no; capture list -> yes; anything else -> "unknown types" switch.
function captureAllowed(cap, url, filename, forced) {
  let u; try { u = new URL(url); } catch { return false; }
  if (!forced && hostMatch(u.hostname.toLowerCase(), cap.exclude_sites)) return false;
  if (forced) return true;
  const ext = extOf(filename) || extOf(u.pathname);
  if ((cap.skip_types || []).includes(ext)) return false;
  if ((cap.capture_types || []).includes(ext)) return true;
  return cap.capture_unknown !== false;
}
async function browserName() {
  const ua = navigator.userAgent;
  if (/Firefox\//.test(ua)) return "firefox";
  if (/Edg\//.test(ua)) return "edge";
  if (/OPR\/|Opera|Vivaldi/.test(ua)) return "other";
  try { if (navigator.brave && (await navigator.brave.isBrave())) return "brave"; } catch {}
  return "chrome";
}

// Take over browser downloads - but ONLY ones the user is starting right now.
// FIX (phantom downloads): the old code grabbed every download the browser reported (old/resumed items, page-script downloads,
// downloads from a window the user isn't using). Now a download must be fresh, in the focused window, follow a real user
// gesture (or a typed address), not be a duplicate, and not be part of a burst. Anything else is left to the browser, untouched.
const GESTURE_MS = 20e3, FRESH_MS = 15e3, DEDUPE_MS = 60e3, BURST_N = 3, BURST_MS = 10e3;
let lastGesture = 0, lastMods = {};
const recentUrls = new Map();   // url -> time OpenDM was last offered it
const burstTimes = [];

async function windowFocused() {
  try { const w = await api.windows?.getLastFocused?.(); return !w || w.focused !== false; } catch { return true; }
}

async function shouldCapture(item, url) {
  const now = Date.now();
  if (item.byExtensionId) return false;                                   // started by another extension
  if (item.state && item.state !== "in_progress") return false;           // finished / interrupted old item
  const started = Date.parse(item.startTime || "");
  if (started && now - started > FRESH_MS) return false;                 // restored or old item, not a new click
  for (const [u, t] of recentUrls) if (now - t > DEDUPE_MS) recentUrls.delete(u);
  if (recentUrls.has(url)) return false;                                  // already offered a moment ago
  if (!(await windowFocused())) return false;                             // user is not in the browser
  const typed = !item.referrer;                                           // address bar / bookmark: no page involved
  if (!typed && now - lastGesture > GESTURE_MS) return false;             // page script started it without the user
  while (burstTimes.length && now - burstTimes[0] > BURST_MS) burstTimes.shift();
  if (burstTimes.length >= BURST_N) return false;                         // a page spraying downloads
  burstTimes.push(now); recentUrls.set(url, now);
  return true;
}

api.downloads.onCreated.addListener(async (item) => {
  const cfg = await getCfg();
  const url = item.finalUrl || item.url;
  if (!cfg.intercept || !/^https?:/i.test(url)) return;
  const cap = await getCapture();
  if (!cap.intercept) return;                                             // "Capture downloads from browsers" is off in OpenDM
  if (cap.browsers && cap.browsers[await browserName()] === false) return; // this browser is switched off in OpenDM
  const fresh = Date.now() - lastGesture < GESTURE_MS, held = (k) => fresh && k && k !== "none" && !!lastMods[k];
  if (held(cap.key_prevent)) return;                                      // the "let the browser do it" key was held
  if (!captureAllowed(cap, url, item.filename, held(cap.key_force))) return;   // file type / excluded site
  const minKB = Math.max(cfg.minSizeKB || 0, cap.min_size_kb || 0);
  if (minKB && item.fileSize > 0 && item.fileSize < minKB * 1024) return;
  if (!(await shouldCapture(item, url))) return;                          // not the user's download: leave it to the browser
  try { await api.downloads.pause(item.id); } catch {}  // keep the browser's copy from finishing while OpenDM (maybe starting up) takes over
  try {
    const name = item.filename ? item.filename.split(/[\\/]/).pop() : "";
    await sendToOpenDM({ url, referer: item.referrer || "", filename: name });
    await api.downloads.cancel(item.id);
    await api.downloads.erase({ id: item.id });
  } catch (e) {
    console.warn("OpenDM unavailable, browser will download it:", e.message);
    try { await api.downloads.resume(item.id); } catch {}  // OpenDM couldn't take it: let the browser carry on
  }
});

// Right-click menus (which ones exist is decided in OpenDM's Configuration)
api.runtime.onInstalled.addListener(() => buildMenus(DEFAULT_CAP));
api.runtime.onStartup?.addListener(() => getCapture(0).catch(() => {}));   // also opens the native connection ahead of the first capture
getCapture(0).catch(() => {});   // service worker (re)started: warm the host process and the capture rules now, not at the first download
api.contextMenus.onClicked.addListener(async (info, tab) => {
  const url = info.linkUrl || info.srcUrl;
  if (!url) return;
  try { await sendToOpenDM({ url, referer: info.pageUrl || tab?.url || "" }); }
  catch (e) { console.warn(e.message); api.tabs.create({ url: api.runtime.getURL("options.html") }); }
});

// ---------------- Video detection ("Download this video") ----------------
const sess = api.storage.session ?? api.storage.local;
const HLS_CT = /mpegurl/i;
const DASH_CT = /dash\+xml/i;
const kindOf = (url) => (/\.m3u8(\?|#|$)/i.test(url) ? "hls" : /\.mpd(\?|#|$)/i.test(url) ? "dash" : "file");
const FILE_CT = /^(video\/(mp4|webm|x-matroska|quicktime)|audio\/(mpeg|mp4|aac|ogg|webm|flac|wav))/i;
const hdr = (d, n) => d.responseHeaders?.find((h) => h.name.toLowerCase() === n)?.value ?? "";

// FIX (no sound): DASH sites (Facebook, Instagram, Reels, YouTube) serve picture and sound as two separate files.
// Tag every sniffed file as "video" or "audio" so both halves of one playback can be found and paired.
//   1) content-type audio/*   2) ?mime=audio/..  (YouTube)   3) ?efg=<base64 json>.vencode_tag (Facebook/Instagram CDN, e.g. "..._audio")
const b64json = (s) => { try { return JSON.parse(atob(s.replace(/-/g, "+").replace(/_/g, "/"))); } catch { return null; } };
function roleOf(url, ct) {
  if (/^audio\//i.test(ct)) return "audio";
  try {
    const u = new URL(url), mime = u.searchParams.get("mime"), efg = u.searchParams.get("efg");
    if (mime) return /^audio/i.test(mime) ? "audio" : "video";
    if (efg) { const tag = String(b64json(efg)?.vencode_tag || ""); if (tag) return /audio|heaac|aac|opus/i.test(tag) ? "audio" : "video"; }
  } catch {}
  return /^video\//i.test(ct) ? "video" : "unknown";
}

// FIX (no sound): attach to every video file the audio file that belongs to it (same tab, closest in time to when it was loaded).
function withPairs(list) {
  const audios = list.filter((m) => m.kind === "file" && m.role === "audio");
  if (!audios.length) return list;
  return list.map((m) => {
    if (m.kind !== "file" || m.role !== "video") return m;
    const best = audios.map((a) => ({ a, d: Math.abs((a.t || 0) - (m.t || 0)) + (a.frameId === m.frameId ? 0 : 5000) })).sort((x, y) => x.d - y.d)[0];
    return best ? { ...m, audioUrl: best.a.url } : m;
  });
}

// Saves run one at a time: two videos arriving together must not overwrite each other's list.
let addQueue = Promise.resolve();
const addMedia = (tabId, item) => (addQueue = addQueue.then(() => addMediaNow(tabId, item)).catch(() => {}));

// Sites like Facebook/Instagram serve one video as many ?bytestart=..&byteend=.. pieces.
// Dropping those two parameters gives the whole file, so all the pieces collapse into one entry.
function normalizeUrl(u) {
  try {
    const x = new URL(u);
    if (!x.searchParams.has("bytestart") && !x.searchParams.has("byteend")) return u;
    x.searchParams.delete("bytestart"); x.searchParams.delete("byteend");
    return x.href;
  } catch { return u; }
}

const seenMedia = new Map();   // tabId -> Set of normalized URLs already listed: duplicates are dropped before any storage or tab lookup
function firstSight(tabId, url) {
  let set = seenMedia.get(tabId);
  if (!set) seenMedia.set(tabId, (set = new Set()));
  if (set.has(url)) return false;
  if (set.size > 200) set.clear();
  set.add(url);
  return true;
}
async function addMediaNow(tabId, item) {
  const norm = normalizeUrl(item.url);
  if (!firstSight(tabId, norm)) return;
  if (norm !== item.url) item = { ...item, url: norm, orig: item.url, size: 0 };
  const key = "media:" + tabId;
  const cur = (await sess.get(key))[key] ?? [];
  if (cur.some((m) => m.url === item.url)) return;
  try { const t = await api.tabs.get(tabId); item.page = t.url; item.title = t.title; } catch {}
  cur.push(item);
  await sess.set({ [key]: cur.slice(-30) });
  api.action.setBadgeText({ tabId, text: String(Math.min(cur.length, 30)) });
  api.action.setBadgeBackgroundColor({ tabId, color: "#2563eb" });
  notifyPanel(tabId);
}

api.webRequest.onHeadersReceived.addListener(
  (d) => {
    if (d.tabId < 0 || d.statusCode >= 400) return;
    const ct = hdr(d, "content-type");
    if (HLS_CT.test(ct) || /\.m3u8(\?|#|$)/i.test(d.url)) {
      addMedia(d.tabId, { url: d.url, kind: "hls", size: 0 });
    } else if (DASH_CT.test(ct) || /\.mpd(\?|#|$)/i.test(d.url)) {
      addMedia(d.tabId, { url: d.url, kind: "dash", size: 0 });  // a DASH manifest: OpenDM hands it to ffmpeg
    } else if (FILE_CT.test(ct)) {
      const total = +(hdr(d, "content-range").split("/")[1] || hdr(d, "content-length") || 0);
      const role = roleOf(d.url, ct);
      const piece = /[?&](bytestart|byteend)=/.test(d.url);   // a ranged piece of a longer stream: size says nothing, keep it
      // FIX (no sound): the 2 MB floor used to apply to everything and silently discarded the (small) audio stream.
      const min = role === "audio" ? 16 * 1024 : 2 * 1024 * 1024;
      if (piece || total >= min) addMedia(d.tabId, { url: d.url, kind: "file", size: total, role, t: Date.now(), frameId: d.frameId });
    }
  },
  { urls: ["<all_urls>"], types: ["media", "xmlhttprequest", "other"] },
  ["responseHeaders"]
);

api.tabs.onUpdated.addListener((id, ci) => {
  if (ci.status === "loading" && ci.url) { seenMedia.delete(id); sess.remove("media:" + id); api.action.setBadgeText({ tabId: id, text: "" }); notifyPanel(id); }
});
api.tabs.onRemoved.addListener((id) => { seenMedia.delete(id); sess.remove("media:" + id); });

// ---------------- Quality of direct files: read the MP4 header, not the whole file ----------------
const u32 = (b, o) => (((b[o] << 24) | (b[o + 1] << 16) | (b[o + 2] << 8) | b[o + 3]) >>> 0);
const u64 = (b, o) => u32(b, o) * 4294967296 + u32(b, o + 4);
const tag = (b, o) => String.fromCharCode(b[o], b[o + 1], b[o + 2], b[o + 3]);

function* boxes(b, start, end) {
  for (let o = start; o + 8 <= end;) {
    let size = u32(b, o), hdr = 8;
    const type = tag(b, o + 4);
    if (size === 1) { if (o + 16 > end) return; size = u64(b, o + 8); hdr = 16; }
    else if (size === 0) size = end - o;
    if (size < hdr) return;
    yield { type, off: o, size, hdr };
    o += size;
  }
}

function parseMoov(b, box) {
  const out = { width: 0, height: 0, duration: 0, video: false, audio: false, fragmented: false };
  const end = Math.min(box.off + box.size, b.length);
  for (const c of boxes(b, box.off + box.hdr, end)) {
    const p = c.off + c.hdr;
    if (c.type === "mvex") out.fragmented = true;
    if (c.type === "mvhd") {
      const v = b[p], ts = u32(b, p + (v ? 20 : 12)), du = v ? u64(b, p + 24) : u32(b, p + 16);
      if (ts && du < 0xffffffff) out.duration = du / ts;
    }
    if (c.type !== "trak") continue;
    let w = 0, h = 0, kind = "";
    for (const t of boxes(b, p, Math.min(c.off + c.size, b.length))) {
      if (t.type === "tkhd") { const o = t.off + t.hdr + (b[t.off + t.hdr] ? 88 : 76); w = u32(b, o) / 65536; h = u32(b, o + 4) / 65536; }
      if (t.type === "mdia") for (const m of boxes(b, t.off + t.hdr, Math.min(t.off + t.size, b.length))) if (m.type === "hdlr") kind = tag(b, m.off + m.hdr + 8);
    }
    if (kind === "vide") { out.video = true; if (w * h >= out.width * out.height) { out.width = Math.round(w); out.height = Math.round(h); } }
    else if (kind === "soun") out.audio = true;
  }
  return out;
}

async function rangeBytes(url, start, len) {
  const r = await fetch(url, { headers: { Range: `bytes=${start}-${start + len - 1}` }, credentials: "include" });
  if (!r.ok) throw new Error("http " + r.status);
  const cr = r.headers.get("content-range");
  const total = cr ? +cr.split("/")[1] || 0 : +(r.headers.get("content-length") || 0);
  if (r.status === 206) return { buf: new Uint8Array(await r.arrayBuffer()), total };
  if (start > 0) { r.body?.cancel(); throw new Error("server ignores Range"); }
  const rd = r.body.getReader(), parts = [];  // Range ignored: take only the first bytes, then hang up
  let n = 0;
  while (n < len) { const { done, value } = await rd.read(); if (done) break; parts.push(value); n += value.length; }
  rd.cancel().catch(() => {});
  const buf = new Uint8Array(Math.min(n, len)); let o = 0;
  for (const p of parts) { const take = Math.min(p.length, buf.length - o); buf.set(p.subarray(0, take), o); o += take; }
  return { buf, total };
}

async function probeMp4(url) {
  const WIN = 256 * 1024;
  let { buf, total } = await rangeBytes(url, 0, WIN), base = 0, off = 0;
  for (let guard = 0; guard < 40; guard++) {
    if (off < base || off + 16 > base + buf.length) {  // next box header isn't in our window: fetch from there
      if (total && off >= total) break;
      ({ buf } = await rangeBytes(url, off, WIN)); base = off;
      if (buf.length < 8) break;
    }
    const rel = off - base;
    let size = u32(buf, rel), hdr = 8;
    const type = tag(buf, rel + 4);
    if (size === 1) { size = u64(buf, rel + 8); hdr = 16; } else if (size === 0) size = (total || off + buf.length) - off;
    if (size < hdr) break;
    if (type === "moof" || type === "styp") return { segment: true, size: total, video: false, audio: false, width: 0, height: 0, duration: 0 };  // a piece of a stream, not a video
    if (type === "moov") {
      if (rel + size > buf.length) { if (size > 16 * 1024 * 1024) break; ({ buf } = await rangeBytes(url, off, size)); base = off; }
      const info = parseMoov(buf, { off: off - base, size, hdr });
      return { ...info, size: total, segment: info.fragmented && total > 0 && total < 20 * 1024 };  // tiny fMP4 = init segment only
    }
    off += size;
    if (total && off >= total) break;
  }
  return null;  // not an MP4 we can read (webm, mp3, ...): the panel just shows "Direct file"
}

const pcache = new Map();
async function probeMedia(url, orig) {
  if (pcache.has(url)) return pcache.get(url);
  let out = null;
  for (const u of orig ? [url, orig] : [url]) {  // if the cleaned-up URL doesn't work, fall back to the original
    try { out = await probeMp4(u); } catch { out = null; }
    if (out) { out.useUrl = u; break; }
  }
  pcache.set(url, out);
  return out;
}

// ---------------- Refresh an open "Download this video" menu when new streams arrive ----------------
function notifyPanel(tabId) {
  try { Promise.resolve(api.tabs.sendMessage(tabId, { cmd: "media-updated" }, { frameId: 0 })).catch(() => {}); } catch {}
}
async function listMedia(tabId) { const k = "media:" + tabId; return withPairs((await sess.get(k))[k] ?? []); }  // FIX: items carry audioUrl when a matching audio stream was sniffed

// Read the qualities offered by an HLS master playlist (empty list = single-quality stream)
const vcache = new Map();
async function getVariants(url) {
  if (vcache.has(url)) return vcache.get(url);
  let out = [];
  try {
    const r = await fetch(url, { credentials: "include" });
    const text = r.ok ? await r.text() : "";
    if (text.includes("#EXT-X-STREAM-INF")) {
      const lines = text.split(/\r?\n/);
      lines.forEach((l, i) => {
        if (!l.startsWith("#EXT-X-STREAM-INF:")) return;
        const a = Object.fromEntries([...l.slice(18).matchAll(/([A-Z0-9-]+)=("[^"]*"|[^,]*)/g)].map((m) => [m[1], m[2].replace(/"/g, "")]));
        const uri = lines.slice(i + 1).find((x) => x.trim() && !x.startsWith("#"));
        if (uri) out.push({ height: +(a.RESOLUTION?.split("x")[1] || 0), bandwidth: +(a.BANDWIDTH || 0),
                            fps: a["FRAME-RATE"] ? Math.round(+a["FRAME-RATE"]) : 0, url: new URL(uri.trim(), r.url).href });
      });
      const seen = new Set();
      out = out.filter((v) => !seen.has(v.height + "/" + v.bandwidth) && seen.add(v.height + "/" + v.bandwidth))
               .sort((x, y) => y.height - x.height || y.bandwidth - x.bandwidth);
    }
  } catch { /* leave empty: the panel falls back to "Best available" */ }
  vcache.set(url, out);
  return out;
}

// ---------------- Stream list from OpenDM (yt-dlp): YouTube, Facebook, Instagram ... ----------------
// OpenDM reads the page's qualities and sizes; the answer is cached for a few minutes. Nothing downloads until the user picks a row.
const fcache = new Map();
async function getFormats(url, referer, prefetch) {
  const hit = fcache.get(url);
  if (hit && Date.now() - hit.t < 5 * 60e3) return hit.data;
  const job = { url, referer: referer || "", cookie: await cookieHeader(url), userAgent: navigator.userAgent, ...(prefetch ? { prefetch: true } : {}) };
  let data = null, nativeError = "";
  try { data = await nativeCall({ cmd: "formats", job }, 90000); }  // yt-dlp can take a while
  catch (e) { nativeError = e?.message || String(e); }
  if (!data) {
    const cfg = await getCfg();
    if (!cfg.token) throw new Error("not paired: OpenDM's browser integration isn't registered yet" + (nativeError ? ` (${nativeError})` : ""));
    if (prefetch) return { ok: false, error: "prefetch skipped", prefetch: true };
    const r = await fetch(`http://127.0.0.1:${cfg.port}/formats`, {
      method: "POST", headers: { "Content-Type": "application/json", "X-OpenDM-Token": cfg.token }, body: JSON.stringify(job),
    });
    if (!r.ok) throw new Error("OpenDM replied " + r.status);
    data = await r.json();
  }
  if (data?.prefetch) return data;   // OpenDM isn't running: nothing to cache
  if (data?.ok && data.formats?.length) fcache.set(url, { t: Date.now(), data });
  if (fcache.size > 40) fcache.delete(fcache.keys().next().value);
  return data;
}

api.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  const tabId = sender.tab?.id;
  const reply = (p) => { p.then(sendResponse, (e) => sendResponse({ ok: false, error: e.message })); return true; };
  switch (msg?.cmd) {
    case "gesture": lastGesture = Date.now(); lastMods = { alt: !!msg.alt, ctrl: !!msg.ctrl, shift: !!msg.shift }; return false;   // real click/key in a page (content.js)
    case "cfg": return reply(getCapture(5 * 60e3));   // content.js: should the "Download this video" button show?
    case "send": return reply(sendToOpenDM(msg.job).then(() => ({ ok: true })));
    case "status": return reply(connectionStatus().then((s) => ({ ok: true, ...s })));
    case "formats":  // the overlay's menu; only for web addresses
      return /^https?:/i.test(msg.url || "") ? reply(getFormats(msg.url, msg.referer, !!msg.prefetch)) : false;
    case "list": return tabId == null ? false : reply(listMedia(tabId));
    case "variants":  // only for streams this tab actually loaded
      return tabId == null ? false : reply(listMedia(tabId).then((l) => (l.some((m) => m.url === msg.url) ? getVariants(msg.url) : [])));
    case "probe":  // quality of a direct file, only for files this tab actually loaded
      return tabId == null ? false : reply(listMedia(tabId).then((l) => { const m = l.find((x) => x.url === msg.url); return m ? probeMedia(m.url, m.orig) : null; }));
    case "found":
      if (tabId == null || !/^https?:/i.test(msg.url || "")) return false;
      return reply(addMedia(tabId, { url: msg.url, kind: kindOf(msg.url), size: 0 }).then(() => ({ ok: true })));
  }
});
