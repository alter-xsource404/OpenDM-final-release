// The extension's native-messaging path, with the real extension/background.js and a scripted "native host".
const assert = require("assert"), path = require("path");
const mem = {}, L = {}, calls = [], native = [], dl = [];
const store = () => ({ get: async (k) => (typeof k === "string" ? { [k]: mem[k] } : Object.fromEntries(Object.entries(k).map(([a, d]) => [a, mem[a] ?? d]))), set: async (o) => Object.assign(mem, o), remove: async (k) => { delete mem[k]; } });
const ev = (n) => ({ addListener: (f) => (L[n] = f) });
let hostBehaviour = null;   // (msg) => reply | throws
globalThis.chrome = {
  storage: { local: store(), session: store(), onChanged: ev("sc") }, webRequest: { onHeadersReceived: ev("h") },
  downloads: { onCreated: ev("dl"), pause: async (id) => dl.push(["pause", id]), resume: async (id) => dl.push(["resume", id]), cancel: async (id) => dl.push(["cancel", id]), erase: async (o) => dl.push(["erase", o.id]) },
  cookies: { getAll: async () => [{ name: "sid", value: "abc" }] }, action: { setBadgeText() {}, setBadgeBackgroundColor() {} },
  tabs: { get: async () => ({ url: "https://site.test/", title: "t" }), onUpdated: ev("u"), onRemoved: ev("r"), sendMessage: async () => {} },
  runtime: { onMessage: ev("m"), onInstalled: ev("i"), getURL: (p) => p, sendNativeMessage: async (host, msg) => { native.push([host, msg]); return hostBehaviour(msg); } },
  contextMenus: { create() {}, onClicked: ev("c") },
};
globalThis.fetch = async (url, opt) => { calls.push([url, opt]); return { ok: true, status: 200 }; };
require(path.join(__dirname, "../../extension/background.js"));
const msg = (m) => new Promise((res) => { const r = L.m(m, {}, res); if (r !== true) res("(none)"); });
const reset = () => { calls.length = native.length = dl.length = 0; delete mem.token; };
const JOB = { url: "https://cdn.test/a.zip", referer: "https://site.test/", filename: "a.zip" };

(async () => {
  try {
    // 1. the normal case: the host takes it, no port or token involved
    reset(); hostBehaviour = () => ({ ok: true });
    assert.deepStrictEqual(await msg({ cmd: "send", job: JOB }), { ok: true });
    assert.strictEqual(native.length, 1); assert.strictEqual(native[0][0], "org.opendm.nativehost");
    assert.deepStrictEqual([native[0][1].cmd, native[0][1].job.url, native[0][1].job.cookie, typeof native[0][1].job.userAgent], ["add", JOB.url, "sid=abc", "string"]);
    assert.strictEqual(calls.length, 0);
    console.log("PASS send goes through the native host (host name org.opendm.nativehost), with cookies and user-agent, and no HTTP call, port or token");

    // 2. the host isn't installed / isn't allowed -> use the manual token path
    reset(); hostBehaviour = () => { throw new Error("Specified native messaging host not found."); }; mem.token = "TKN";
    assert.deepStrictEqual(await msg({ cmd: "send", job: JOB }), { ok: true });
    assert.strictEqual(calls.length, 1); assert.strictEqual(calls[0][1].headers["X-OpenDM-Token"], "TKN"); assert.strictEqual(JSON.parse(calls[0][1].body).url, JOB.url);
    console.log("PASS host not registered -> falls back to the pairing-token connection");

    // 3. the host answered "no": that is final (a second route would only hide the reason)
    reset(); hostBehaviour = () => ({ ok: false, error: "OpenDM isn't running. Start it, or tick 'Start OpenDM when the browser sends a download'." }); mem.token = "TKN";
    const r3 = await msg({ cmd: "send", job: JOB });
    assert.strictEqual(r3.ok, false); assert(/isn't running/.test(r3.error)); assert.strictEqual(calls.length, 0);
    console.log("PASS an error from OpenDM is reported as-is, with no silent retry over HTTP");

    // 4. nothing works and nothing is paired: say how to fix it
    reset(); hostBehaviour = () => { throw new Error("Native host has exited."); };
    const r4 = await msg({ cmd: "send", job: JOB });
    assert.strictEqual(r4.ok, false); assert(/not paired/.test(r4.error) && /registered/.test(r4.error) && /exited/.test(r4.error), r4.error);
    console.log("PASS no host and no token -> clear message:", r4.error);

    // 5. connection status for the options page and popup
    reset(); hostBehaviour = (m) => (m.cmd === "ping" ? { ok: true, running: true, version: "1.5.0", autostart: true } : { ok: true });
    assert.deepStrictEqual(await msg({ cmd: "status" }), { ok: true, mode: "native", running: true, version: "1.5.0", autostart: true });
    hostBehaviour = () => ({ ok: true, running: false, version: "1.5.0", autostart: true });
    assert.deepStrictEqual([(await msg({ cmd: "status" })).mode, (await msg({ cmd: "status" })).running], ["native", false]);
    hostBehaviour = () => { throw new Error("not found"); }; mem.token = "TKN";
    assert.strictEqual((await msg({ cmd: "status" })).mode, "manual");
    delete mem.token; const none = await msg({ cmd: "status" });
    assert.deepStrictEqual([none.mode, none.error], ["none", "not found"]);
    console.log("PASS status reports native / native-but-OpenDM-stopped / manual token / not connected");

    // 6. taking over a browser download: pause it, hand it over, then remove it; if OpenDM can't take it, let the browser continue
    const CAP = { intercept: true, capture_types: ["iso", "zip"], skip_types: ["png"], capture_unknown: false, exclude_sites: ["blocked.test"], min_size_kb: 0,
                  key_prevent: "alt", key_force: "shift", browsers: { chrome: true }, ctx_link: true, ctx_media: true, video_button: false };
    reset(); hostBehaviour = (m) => (m.cmd === "config" ? { ok: true, running: true, config: CAP } : { ok: true });
    await msg({ cmd: "gesture" });   // a real click precedes a real download
    await L.dl({ id: 7, url: "https://cdn.test/big.iso", referrer: "https://site.test/", filename: "C:\\Users\\me\\Downloads\\big.iso", fileSize: 9e6 });
    assert.deepStrictEqual(dl.map((x) => x[0]), ["pause", "cancel", "erase"]); assert.strictEqual(native.find((x) => x[1].cmd === "add")[1].job.filename, "big.iso");
    // OpenDM's capture rules (Configuration > File types / General): file types, excluded sites, unknown types, prevent / force keys, per-browser switch
    const adds = () => native.filter((x) => x[1].cmd === "add").length;
    let skew = 0; const realNow = Date.now; Date.now = () => realNow() + skew;   // each case runs "later", clear of the burst cap
    const tryDl = async (id, url, mods) => { skew += 30000; reset(); await msg({ cmd: "gesture", ...mods }); const n0 = adds(); await L.dl({ id, url, referrer: "https://site.test/" }); return adds() - n0; };
    assert.strictEqual(await tryDl(20, "https://cdn.test/pic.png"), 0, "skip list");
    assert.strictEqual(await tryDl(21, "https://blocked.test/file.zip"), 0, "excluded site");
    assert.strictEqual(await tryDl(22, "https://cdn.test/file.bin"), 0, "unknown type with the switch off");
    assert.strictEqual(await tryDl(23, "https://cdn.test/a.zip", { alt: true }), 0, "prevent key held");
    assert.strictEqual(await tryDl(24, "https://cdn.test/file.bin", { shift: true }), 1, "force key held");
    assert.strictEqual(await tryDl(25, "https://sub.cdn.test/ok.zip"), 1, "a listed type is captured");
    console.log("PASS capture rules: skip list, excluded sites, unknown types, prevent key, force key");
    assert.strictEqual((await msg({ cmd: "cfg" })).video_button, false); console.log("PASS content script learns the video button is switched off");
    skew += 30000; reset(); hostBehaviour = () => ({ ok: false, error: "nope" });
    await L.dl({ id: 8, url: "https://cdn.test/big2.iso", filename: "big.iso" });
    assert.deepStrictEqual(dl.map((x) => x[0]), ["pause", "resume"]);
    console.log("PASS browser download: paused -> handed to OpenDM -> cancelled/erased; on failure it is resumed so nothing is lost");
    reset(); mem.intercept = false; await L.dl({ id: 9, url: "https://cdn.test/x.zip" }); assert.strictEqual(native.length + dl.length, 0); mem.intercept = true;
    console.log("PASS capture switched off -> the extension leaves downloads alone");
  } catch (e) { console.error("FAIL", e.message); process.exitCode = 1; }
})();
