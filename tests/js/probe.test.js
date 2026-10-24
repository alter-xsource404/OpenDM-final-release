// Quality detection for direct video files + merging of byte-range pieces.
// Builds tiny MP4s by hand (no ffmpeg needed) and runs the real extension/background.js against a local server.
const assert = require("assert"), http = require("http"), path = require("path");
const mem = {}, L = {};
const store = () => ({ get: async (k) => (typeof k === "string" ? { [k]: mem[k] } : Object.fromEntries(Object.entries(k).map(([a, d]) => [a, mem[a] ?? d]))), set: async (o) => Object.assign(mem, o), remove: async (k) => { delete mem[k]; } });
const ev = (n) => ({ addListener: (f) => (L[n] = f) });
globalThis.chrome = { storage: { local: store(), session: store(), onChanged: ev("sc") }, webRequest: { onHeadersReceived: ev("h") }, downloads: { onCreated: ev("d") }, cookies: { getAll: async () => [] },
  action: { setBadgeText() {}, setBadgeBackgroundColor() {} }, tabs: { get: async () => ({ url: "https://site.test/", title: "t" }), onUpdated: ev("u"), onRemoved: ev("r"), sendMessage: async () => {} },
  runtime: { onMessage: ev("m"), onInstalled: ev("i"), getURL: (p) => p }, contextMenus: { create() {}, onClicked: ev("c") } };
require(path.join(__dirname, "../../extension/background.js"));

// ---- minimal MP4 builder ----
const box = (type, ...kids) => { const body = Buffer.concat(kids), h = Buffer.alloc(8); h.writeUInt32BE(body.length + 8); h.write(type, 4); return Buffer.concat([h, body]); };
const mvhd = (secs) => { const p = Buffer.alloc(100); p.writeUInt32BE(1000, 12); p.writeUInt32BE(secs * 1000, 16); return box("mvhd", p); };
const trak = (kind, w, h) => {
  const tk = Buffer.alloc(84); tk.writeUInt32BE(w * 65536, 76); tk.writeUInt32BE(h * 65536, 80);
  const hd = Buffer.alloc(25); hd.write(kind, 8);
  return box("trak", box("tkhd", tk), box("mdia", box("hdlr", hd)));
};
const ftyp = box("ftyp", Buffer.from("isom\0\0\0\0isom"));
const junk = (n) => box("mdat", Buffer.alloc(n, 7));
const FILES = {
  "/hd.mp4": Buffer.concat([ftyp, box("moov", mvhd(12), trak("vide", 1280, 720), trak("soun", 0, 0)), junk(300000)]),
  "/vertical_noaudio.mp4": Buffer.concat([ftyp, junk(900000), box("moov", mvhd(30), trak("vide", 720, 1280))]),  // moov AFTER 900 KB of data
  "/audio.m4a": Buffer.concat([ftyp, box("moov", mvhd(5), trak("soun", 0, 0))]),
  "/segment.m4s": Buffer.concat([box("styp", Buffer.from("msdh\0\0\0\0msdh")), box("moof", Buffer.alloc(40)), junk(50000)]),
  "/notmp4.mp4": Buffer.alloc(4000, 65),
};
let hits = 0;
const srv = http.createServer((q, s) => {
  hits++; const d = FILES[q.url.split("?")[0]]; if (!d) return s.writeHead(404).end();
  const m = /bytes=(\d+)-(\d*)/.exec(q.headers.range || "");
  if (!m) return s.writeHead(200, { "Content-Length": d.length }).end(d);
  const a = +m[1], b = Math.min(m[2] ? +m[2] : d.length - 1, d.length - 1);
  s.writeHead(206, { "Content-Range": `bytes ${a}-${b}/${d.length}`, "Content-Length": b - a + 1 }).end(d.subarray(a, b + 1));
});
const msg = (m) => new Promise((res) => { const r = L.m(m, { tab: { id: 1 } }, res); if (r !== true) res("(none)"); });
const probe = async (base, f) => { await msg({ cmd: "found", url: base + f }); return msg({ cmd: "probe", url: base + f }); };

srv.listen(0, "127.0.0.1", async () => {
  try {
    const base = "http://127.0.0.1:" + srv.address().port;
    let p = await probe(base, "/hd.mp4");
    assert.deepStrictEqual([p.video, p.audio, p.width, p.height, p.duration, p.size, p.segment], [true, true, 1280, 720, 12, FILES["/hd.mp4"].length, false]);
    console.log("PASS 720p file with sound: 1280x720, 12 s, size read from the server");
    const before = hits; p = await probe(base, "/vertical_noaudio.mp4");
    assert.deepStrictEqual([p.video, p.audio, p.width, p.height, p.duration], [true, false, 720, 1280, 30]);
    console.log(`PASS vertical video-only file whose header is at the END (needed ${hits - before} requests, not the whole file)`);
    p = await probe(base, "/audio.m4a"); assert.deepStrictEqual([p.video, p.audio, p.width], [false, true, 0]); console.log("PASS audio-only file detected");
    p = await probe(base, "/segment.m4s"); assert.strictEqual(p.segment, true); console.log("PASS stream segment (styp/moof) flagged so the panel hides it");
    p = await probe(base, "/notmp4.mp4"); assert.strictEqual(p, null); console.log("PASS unreadable file -> null (panel falls back to 'Direct file')");
    assert.strictEqual(await msg({ cmd: "probe", url: base + "/hd.mp4?other" }), null); console.log("PASS probe refuses URLs the tab never loaded");

    for (const r of ["bytestart=0&byteend=99", "bytestart=100&byteend=199", "byteend=299&bytestart=200"]) await msg({ cmd: "found", url: `${base}/hd.mp4?oh=sig&${r}` });
    const merged = (await msg({ cmd: "list" })).filter((x) => x.url.includes("oh=sig"));
    assert.strictEqual(merged.length, 1); assert.strictEqual(merged[0].url, `${base}/hd.mp4?oh=sig`); assert(merged[0].orig.includes("bytestart"));
    p = await msg({ cmd: "probe", url: merged[0].url }); assert.strictEqual(p.height, 720); assert.strictEqual(p.useUrl, merged[0].url);
    console.log("PASS 3 byte-range pieces of one stream collapse into 1 entry and probe as 720p");
  } catch (e) { console.error("FAIL", e.message); process.exitCode = 1; }
  srv.close();
});
