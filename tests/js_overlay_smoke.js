// Runs extension/content.js against a tiny fake DOM: attaches the overlay to a playing <video>, checks position / drag / reset / close /
// SPA re-arm, opens the quality menu and sends a download. Usage: node js_overlay_smoke.js   (exit code 0 = pass)
const fs = require("fs"), path = require("path"), assert = require("assert");

class El {
  constructor(tag) {
    this.tagName = String(tag).toUpperCase(); this.children = []; this.style = {}; this.listeners = {}; this.className = ""; this.textContent = "";
    const set = new Set();
    this.classList = { add: (c) => set.add(c), remove: (c) => set.delete(c), contains: (c) => set.has(c), toggle: (c, on) => (on === undefined ? !set.has(c) : on) ? set.add(c) : set.delete(c) };
    this.offsetWidth = 150; this.offsetHeight = 30; this.activeElement = null; this.isConnected = true;
  }
  append(...k) { this.children.push(...k); } replaceChildren(...k) { this.children = k; }
  remove() { this.removed = true; this.isConnected = false; }
  addEventListener(t, f) { (this.listeners[t] ||= []).push(f); } removeEventListener(t, f) { this.listeners[t] = (this.listeners[t] || []).filter((x) => x !== f); }
  fire(t, ev = {}) { for (const f of [...(this.listeners[t] || [])]) f({ target: this, button: 0, stopPropagation() {}, composedPath: () => [], ...ev }); }
  getAttribute() { return null; } setPointerCapture() {} closest() { return null; } querySelector() { return null; } querySelectorAll() { return []; } contains() { return false; }
  getBoundingClientRect() { return this.rect || { left: 0, top: 0, right: 0, bottom: 0, width: 0, height: 0 }; }
  attachShadow() { const r = new El("shadow"); r.adoptedStyleSheets = []; El.lastRoot = r; return r; }
  find(pred, out = []) { if (pred(this)) out.push(this); this.children.forEach((c) => c instanceof El && c.find(pred, out)); return out; }
}
const rafQueue = []; const flush = () => { const q = rafQueue.splice(0); q.forEach((f) => f(0)); };
const tick = () => new Promise((r) => setTimeout(r, 20));
const sent = [], store = { ovOff: null };
const docEl = new El("html");
const winL = {};
globalThis.window = globalThis; globalThis.top = globalThis;
Object.assign(globalThis, {
  innerWidth: 1280, innerHeight: 720, location: { href: "https://www.youtube.com/watch?v=abc", hostname: "www.youtube.com", pathname: "/watch", search: "?v=abc" },
  CSSStyleSheet: class { replaceSync() {} }, MutationObserver: class { observe() {} }, ResizeObserver: class { observe() {} disconnect() {} },
  requestAnimationFrame: (f) => rafQueue.push(f), setInterval: () => 0,
  document: Object.assign(new El("document"), { createElement: (t) => new El(t), documentElement: docEl, title: "My Clip - YouTube", fullscreenElement: null, querySelectorAll: () => [], querySelector: () => null }),
  addEventListener: (t, f) => (winL[t] ||= []).push(f),
});
const formats = { ok: true, title: "Great Video", duration: 100, speed: 2e6, audio: { ext: "m4a", size: 1.6e6, approx: false },
  formats: [{ height: 1080, fps: 60, ext: "mp4", size: 52e6, approx: false }, { height: 720, fps: 30, ext: "mp4", size: 30e6, approx: true }] };
Object.defineProperty(globalThis, "navigator", { value: { connection: { downlink: 8 } }, configurable: true });
globalThis.chrome = {
  runtime: { sendMessage: async (m) => { sent.push(m); return m.cmd === "formats" ? formats : m.cmd === "list" ? [] : { ok: true }; }, onMessage: { addListener() {} } },
  storage: { onChanged: { addListener() {} }, local: { get: async () => ({ floating: true, overlay: true, ovCompact: false, hiddenSites: [], pos: null, ovOff: store.ovOff }), set: async (o) => Object.assign(store, o) } },
};
require("vm").runInThisContext(fs.readFileSync(path.join(__dirname, "..", "extension", "content.js"), "utf8"), { filename: "content.js" });

(async () => {
  await tick();
  const root = El.lastRoot;
  assert(root && docEl.children.length === 1, "the shadow host is attached");
  const video = new El("video");
  Object.assign(video, { paused: false, currentSrc: "blob:https://www.youtube.com/x", duration: 100, parentElement: null });
  video.rect = { left: 100, top: 200, right: 900, bottom: 650, width: 800, height: 450 };
  const overlays = () => root.find((e) => e.className === "ov");
  assert.strictEqual(overlays().length, 0, "nothing before a video plays");
  winL.playing.forEach((f) => f({ target: video })); flush();
  const ov = overlays()[0];
  assert(ov, "a button appears the moment the video plays");
  assert.strictEqual(ov.style.display, "block");
  assert.strictEqual(ov.style.transform, "translate(740px,210px)", "top-right of the video: right edge 900-10-150, top 200+10");

  video.rect = { left: 100, top: 100, right: 900, bottom: 550, width: 800, height: 450 }; flush();   // scrolled / moved: it follows
  assert.strictEqual(ov.style.transform, "translate(740px,110px)");
  video.rect = { left: 100, top: -150, right: 900, bottom: 300, width: 800, height: 450 }; flush();   // top edge scrolled away: stays on screen
  assert.strictEqual(ov.style.transform, "translate(740px,10px)");
  video.rect = { left: 0, top: 0, right: 1700, bottom: 900, width: 1700, height: 900 }; flush();      // wider than the window: inside the viewport
  assert(/translate\((\d+)px/.exec(ov.style.transform)[1] <= 1280 - 150);
  video.rect = { left: 100, top: 200, right: 900, bottom: 650, width: 800, height: 450 }; flush();

  const pill = ov.find((e) => e.className === "pill")[0], x = pill.find((e) => e.className === "x")[0];
  pill.fire("pointerdown", { clientX: 800, clientY: 215, pointerId: 1 });      // drag 100px left, 60px down
  pill.fire("pointermove", { clientX: 700, clientY: 275 }); pill.fire("pointerup", {}); flush();
  assert.strictEqual(ov.style.transform, "translate(640px,270px)", "dragged");
  assert.deepStrictEqual(store.ovOff, { right: 110, top: 70 }, "position is remembered");
  assert(!ov.classList.contains("open"), "a drag doesn't open the menu");
  pill.fire("dblclick", { target: pill }); flush();
  assert.strictEqual(ov.style.transform, "translate(740px,210px)", "double-click resets to the top-right anchor");
  assert.deepStrictEqual(store.ovOff, { right: 10, top: 10 });

  // the quality menu
  sent.length = 0;
  pill.fire("pointerdown", { clientX: 800, clientY: 215, pointerId: 1 }); pill.fire("pointerup", {});
  assert(ov.classList.contains("open"), "a click opens the menu");
  await tick(); await tick(); flush();
  const fm = sent.find((m) => m.cmd === "formats");
  assert(fm && fm.url === "https://www.youtube.com/watch?v=abc", "asks OpenDM (yt-dlp) for this page's qualities");
  const rows = ov.find((e) => e.className === "q");
  assert.deepStrictEqual(rows.map((r) => r.children[0].textContent), ["1080p60", "720p", "Audio only"]);
  assert(/49\.6 MB · ~26 s/.test(rows[0].children[2].textContent) && /~/.test(rows[0].children[2].textContent), "size and ETA: " + rows[0].children[2].textContent);
  assert(/^≈ /.test(rows[1].children[2].textContent), "estimated sizes are marked");
  const nameInput = ov.find((e) => e.tagName === "INPUT")[0];
  assert.strictEqual(nameInput.value, "Great Video", "the name comes from yt-dlp's title");
  sent.length = 0;
  await rows[1].onclick(); await tick();
  const job = sent.find((m) => m.cmd === "send").job;
  assert.deepStrictEqual([job.url, job.kind, job.quality, job.filename], ["https://www.youtube.com/watch?v=abc", "ytdlp", 720, "Great Video 720p"]);
  await rows[2].onclick();
  assert.strictEqual(sent.filter((m) => m.cmd === "send").pop().job.quality, -1, "audio only");

  // close hides the button for this video only; a new video / address brings it back
  x.onclick({ stopPropagation() {} }); flush();
  assert.strictEqual(ov.style.display, "none");
  video.currentSrc = "blob:https://www.youtube.com/next"; location.href = "https://www.youtube.com/watch?v=def"; winL.loadstart.forEach((f) => f({ target: video })); flush();  // the player swaps the source
  assert.strictEqual(ov.style.display, "block", "a new video instance shows the button again at once");

  // another (feed) video that has not started playing gets no button; a tiny one never does
  const feed = new El("video"); Object.assign(feed, { paused: true, currentSrc: "", duration: NaN, parentElement: null });
  feed.rect = { left: 0, top: 0, right: 300, bottom: 200, width: 300, height: 200 };
  winL.loadstart.forEach((f) => f({ target: feed })); flush();
  assert.strictEqual(overlays().length, 2); assert.strictEqual(overlays()[1].style.display, "none", "not shown until it plays");
  feed.paused = false; feed.rect = { left: 0, top: 0, right: 100, bottom: 60, width: 100, height: 60 };
  winL.playing.forEach((f) => f({ target: feed })); flush();
  assert.strictEqual(overlays()[1].style.display, "none", "too small");
  console.log("overlay smoke: ok");
})().catch((e) => { console.error(e); process.exit(1); });
