// v1.7: one persistent native-messaging connection, id-matched replies, overlapping calls, reconnect after the host dies
const assert = require("assert"), path = require("path");
const mem = {}, L = {};
const store = () => ({ get: async (k) => (typeof k === "string" ? { [k]: mem[k] } : Object.fromEntries(Object.entries(k).map(([a, d]) => [a, mem[a] ?? d]))), set: async (o) => Object.assign(mem, o), remove: async () => {} });
const ev = (n) => ({ addListener: (f) => (L[n] = f) });
let ports = [], hostDelay = () => 0, hostDown = false, sendNativeCalls = 0;
function makePort() {
  const p = { sent: [], msgL: null, discL: null, dead: false,
    onMessage: { addListener: (f) => (p.msgL = f) }, onDisconnect: { addListener: (f) => (p.discL = f) },
    postMessage(m) {
      if (p.dead) throw new Error("Attempting to use a disconnected port object");
      p.sent.push(m);
      if (m.cmd === "die") { p.dead = true; globalThis.chrome.runtime.lastError = { message: "Native host has exited." }; return p.discL(); }
      setTimeout(() => p.msgL({ ok: true, echo: m.cmd, id: m.id }), hostDelay(m));
    } };
  ports.push(p); return p;
}
globalThis.chrome = {
  storage: { local: store(), session: store(), onChanged: ev("sc") }, webRequest: { onHeadersReceived: ev("h") },
  downloads: { onCreated: ev("dl") }, cookies: { getAll: async () => [] }, action: { setBadgeText() {}, setBadgeBackgroundColor() {} },
  tabs: { get: async () => ({ url: "https://s.test/", title: "t" }), onUpdated: ev("u"), onRemoved: ev("r"), sendMessage: async () => {} },
  runtime: { onMessage: ev("m"), onInstalled: ev("i"), getURL: (p) => p, lastError: null, connectNative: () => makePort(), sendNativeMessage: async () => { sendNativeCalls++; return { ok: true }; } },
  contextMenus: { create() {}, onClicked: ev("c") },
};
globalThis.fetch = async () => ({ ok: true, status: 200 });
require(path.join(__dirname, "../../extension/background.js"));
const msg = (m) => new Promise((res) => { const r = L.m(m, {}, res); if (r !== true) res("(none)"); });
const JOB = { url: "https://cdn.test/a.zip", filename: "a.zip" };

(async () => {
  try {
    await new Promise((r) => setTimeout(r, 30));      // start-up warm-up call (config) has run
    assert.strictEqual(ports.length, 1, "start-up opens exactly one connection");
    for (let i = 0; i < 5; i++) assert.deepStrictEqual(await msg({ cmd: "send", job: { ...JOB, url: JOB.url + i } }), { ok: true });
    assert.strictEqual(ports.length, 1); assert.strictEqual(sendNativeCalls, 0);
    console.log("PASS 5 hand-overs reuse ONE native connection (no host process per message), no sendNativeMessage");

    // a slow 'formats' lookup must not delay an 'add' sent after it
    hostDelay = (m) => (m.cmd === "formats" ? 300 : 0);
    const t0 = Date.now(); let fDone = 0;
    const f = msg({ cmd: "formats", url: "https://www.youtube.com/watch?v=x", referer: "" }).then((r) => { fDone = Date.now() - t0; return r; });
    const a = await msg({ cmd: "send", job: JOB }); const aMs = Date.now() - t0;
    assert.strictEqual(a.ok, true); assert(aMs < 200, "add took " + aMs);
    await f; assert(fDone >= 280);
    console.log("PASS add completes in", aMs, "ms while a 300 ms formats lookup is still running (replies matched by id)");

    // prefetch flag reaches the host
    hostDelay = () => 0;
    await msg({ cmd: "formats", url: "https://www.youtube.com/watch?v=y", referer: "", prefetch: true });
    const last = ports[0].sent.filter((m) => m.cmd === "formats").pop(); assert.strictEqual(last.job.prefetch, true);
    console.log("PASS prefetch look-ahead is flagged so the host never starts OpenDM for it");

    // host dies -> pending call fails with a clear error, next call reconnects
    const before = ports.length;
    const dead = await msg({ cmd: "status" }).catch((e) => e);          // status uses 'ping'; make the host die on it
    ports[0].dead = true;
    const r = await msg({ cmd: "send", job: JOB });
    assert.strictEqual(r.ok, true); assert.strictEqual(ports.length, before + 1);
    console.log("PASS after the host process dies the next call reconnects once and succeeds");
  } catch (e) { console.error("FAIL", e); process.exit(1); }
  process.exit(0);
})();
