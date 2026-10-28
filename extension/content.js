// OpenDM content script - v1.6
// ONLY the IDM-style "Download this video" button on playing <video> elements (drag it, double-click resets, x hides it for that video).
// FIX (#2): the "OpenDM Video Sniffer" floating panel/bubble was removed completely.
// FIX (no sound): the menu now lists yt-dlp's formats (video+audio merged by OpenDM/ffmpeg) whenever the page is supported;
//   raw sniffed streams are only a fallback and are always sent together with their paired audio stream (job.audioUrl).
// Runs in every frame. Everything lives in a closed shadow root, so page styles can't touch it.
(() => {
  "use strict";
  if (window.__opendmSniffer || !document.documentElement) return;
  window.__opendmSniffer = true;

  const api = globalThis.browser ?? globalThis.chrome;

  // FIX (phantom downloads): tell the background script when the user really interacts with this page, so only downloads
  // that follow a real click/key/right-click are taken over. Scripts cannot fake these (isTrusted).
  // The held modifier keys ride along: they are the "prevent / force downloading with OpenDM" keys from OpenDM's Configuration.
  let lastGesture = 0;
  const gesture = (e) => {
    if (!e.isTrusted || (e.type !== "pointerdown" && Date.now() - lastGesture < 300)) return;
    lastGesture = Date.now();
    try { Promise.resolve(api.runtime.sendMessage({ cmd: "gesture", alt: e.altKey, ctrl: e.ctrlKey, shift: e.shiftKey })).catch(() => {}); } catch {}
  };
  for (const t of ["pointerdown", "keydown", "contextmenu", "touchstart"]) addEventListener(t, gesture, { capture: true, passive: true });
  const ICON = "data:image/png;base64,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";

  const CSS = `
    :host{all:initial;--bg:#fff;--fg:#111827;--bd:#e5e7eb;--chip:#e5e7eb;--hov:#f3f4f6;--sub:#6b7280}
    @media (prefers-color-scheme:dark){:host{--bg:#1f2937;--fg:#f3f4f6;--bd:#374151;--chip:#374151;--hov:#2b3646;--sub:#9ca3af}}
    *{box-sizing:border-box;font:13px/1.35 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
    .chip{font-size:10px;font-weight:700;padding:1px 6px;border-radius:8px;background:var(--chip);color:var(--fg)}
    .ov{position:fixed;left:0;top:0;display:none;will-change:transform;color:var(--fg)}
    .pill{display:flex;align-items:center;gap:6px;height:30px;padding:0 4px 0 7px;border-radius:15px;cursor:grab;user-select:none;touch-action:none;
          background:linear-gradient(135deg,#2563eb,#1d4ed8);color:#fff;font-weight:600;font-size:12px;white-space:nowrap;
          box-shadow:0 2px 10px #0008,0 0 0 1px #ffffff40 inset;opacity:.88;transition:opacity .15s}
    .pill:hover,.ov.open .pill{opacity:1}
    .pill.drag{cursor:grabbing}
    .pill img{width:18px;height:18px;pointer-events:none;border-radius:4px}
    .pill .car{font-size:10px;opacity:.9;pointer-events:none}
    .pill .x{all:unset;cursor:pointer;width:20px;height:20px;border-radius:10px;text-align:center;line-height:20px;font-size:15px;opacity:.85}
    .pill .x:hover{background:#ffffff40;opacity:1}
    .ov.compact .lbl,.ov.compact .car{display:none}
    .ov.compact .pill{padding:0 4px 0 6px}
    .menu{position:absolute;right:0;top:36px;width:min(330px,calc(100vw - 16px));display:none;flex-direction:column;background:var(--bg);color:var(--fg);
          border:1px solid var(--bd);border-radius:12px;box-shadow:0 10px 30px #0007;overflow:hidden}
    .ov.open .menu{display:flex}
    .menu.up{top:auto;bottom:36px}
    .menu.left{right:auto;left:0}
    .mh{display:flex;align-items:center;gap:8px;padding:8px 10px;background:#2563eb;color:#fff}
    .mh img{width:18px;height:18px;border-radius:4px}.mh b{flex:1;font-size:13px}
    .mh button{all:unset;cursor:pointer;width:22px;height:22px;text-align:center;border-radius:5px;line-height:22px;font-size:16px}
    .mh button:hover{background:#fff3}
    .mn{padding:8px 10px 4px}
    .mn input{width:100%;padding:5px 7px;border-radius:6px;border:1px solid var(--bd);background:var(--bg);color:var(--fg);font-weight:600}
    .ml{overflow:auto;padding:2px 6px 6px}
    .q{display:flex;align-items:center;gap:8px;padding:8px 6px;border-radius:8px;cursor:pointer}
    .q:hover{background:var(--hov)}
    .q .ql{font-weight:700;min-width:62px}
    .q .qs{flex:1;min-width:0;color:var(--sub);font-size:12px;text-align:right}
    .q .go{color:#2563eb;font-weight:700}
    .q.busy{opacity:.55;pointer-events:none}
    .sep{padding:8px 6px 2px;font-size:11px;font-weight:700;color:var(--sub);text-transform:uppercase;letter-spacing:.04em}
    .note{padding:10px 8px;color:var(--sub);font-size:12px}
    .mf{padding:6px 10px;font-size:11px;color:var(--sub);border-top:1px solid var(--bd);min-height:26px}
    .mf.err{color:#ef4444}
  `;

  // ---------- helpers ----------
  const el = (tag, props = {}, ...kids) => { const e = document.createElement(tag); Object.assign(e, props); e.append(...kids); return e; };
  const send = async (msg) => { try { return await api.runtime.sendMessage(msg); } catch { return undefined; } };
  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
  const fmtSize = (n) => (n >= 1073741824 ? (n / 1073741824).toFixed(2) + " GB" : n >= 1048576 ? (n / 1048576).toFixed(1) + " MB" : Math.ceil(n / 1024) + " KB");
  const fmtEta = (s) => (s < 5 ? "a few seconds" : s < 90 ? Math.round(s) + " s" : s < 5400 ? Math.round(s / 60) + " min" : Math.floor(s / 3600) + " h " + Math.round((s % 3600) / 60) + " min");
  const safeName = (s) => String(s || "").replace(/[\/\\:]+/g, "-").replace(/[?*"<>|\u0000-\u001f]+/g, " ").replace(/\s+/g, " ").trim().slice(0, 120).trim();
  const fileExt = (u) => { try { const m = new URL(u).pathname.match(/\.([a-z0-9]{2,4})$/i); return m ? m[1].toLowerCase() : "mp4"; } catch { return "mp4"; } };
  const extOf = (u) => { try { return (new URL(u).pathname.match(/\.([a-z0-9]{2,4})$/i)?.[1] || "FILE").toUpperCase(); } catch { return "FILE"; } };
  const connected = (e = "") => /not paired|replied|token|fetch|network|refused|reach|isn't running|timed out/i.test(e) || !e;
  const errorHint = (e = "") =>
    /not paired/i.test(e) ? "OpenDM isn't connected yet. Open OpenDM once: it registers itself with your browser. (Or paste a token in this extension's options.)"
    : /replied 401|token/i.test(e) ? "OpenDM and the extension disagree about the pairing token. Restart OpenDM, or re-paste the token in the extension's options."
    : /fetch|network|refused/i.test(e) || !e ? "OpenDM isn't running (or the port is wrong). Start it and try again." : e;

  // Best guess at the video's caption: the <video>'s own label, then the page's social/meta title, then <h1>/<title>.
  const SITE_TAIL = /\s*[-|\u2013\u2014\u00b7]\s*(YouTube|Facebook|Instagram|TikTok|Twitter|X|Vimeo|Dailymotion|Reddit|Twitch|Bilibili)\s*$/i;
  const GENERIC = /^(facebook|instagram|youtube|tiktok|twitter|x|vimeo|home|watch|reels?|video|videos|log ?in.*|untitled)$/i;
  function cleanTitle(t) {
    t = String(t || "").replace(/\s+/g, " ").trim().replace(/^\(\d+\+?\)\s*/, "");
    const ig = t.match(/^.{1,80}? on Instagram:\s*["\u201c](.+?)["\u201d]?\s*$/s);
    return (ig ? ig[1] : t).replace(SITE_TAIL, "").trim();
  }
  function captionGuess(video) {
    const meta = (s) => document.querySelector(s)?.content;
    const vids = [...document.querySelectorAll("video")];
    const v = video || vids.find((x) => !x.paused && !x.ended) || vids[0];
    const cands = [v?.getAttribute("aria-label"), v?.title, v?.closest("figure")?.querySelector("figcaption")?.textContent,
      meta("meta[property='og:title']"), meta("meta[name='twitter:title']"), document.querySelector("h1")?.textContent,
      document.title, meta("meta[property='og:description']")];
    for (const x of cands) { const t = safeName(cleanTitle(x)); if (t.length >= 3 && !GENERIC.test(t)) return t; }
    return safeName(location.hostname) || "video";
  }

  // The address yt-dlp should read: this page when it is a video page, else the permalink of the post the <video> sits in (feeds, reels).
  const VIDEO_PAGE = /(\/watch\?|\/watch\/\?|\/shorts\/|\/reels?\/[\w-]+|\/p\/[\w-]+|\/tv\/|\/videos?\/|\/status\/|\/clip\/|\/embed\/|youtu\.be\/|\/v\/)/i;
  const PERMALINK = 'a[href*="/reel/"],a[href*="/reels/"],a[href*="/p/"],a[href*="/tv/"],a[href*="/watch/"],a[href*="/videos/"],a[href*="/status/"],a[href*="/shorts/"],a[href*="/watch?"]';
  function pageUrlFor(v) {
    if (VIDEO_PAGE.test(location.pathname + location.search)) return location.href;
    for (let n = v.parentElement, i = 0; n && i < 14; n = n.parentElement, i++) {
      if (n.querySelectorAll("video").length > 1) break;
      const a = n.querySelector(PERMALINK);
      if (a && /^https?:/i.test(a.href)) return a.href;
    }
    return location.href;
  }

  // ---------- state ----------
  let cfg = { overlay: true, ovCompact: false };
  const OV_HOME = { right: 10, top: 10 };
  const ovOff = { ...OV_HOME };   // where the button sits, measured from the video's top-right corner
  let items = [];                 // streams the background script sniffed for this tab (each may carry .audioUrl)
  const variants = new Map();     // HLS master url -> null (loading) | [{height,bandwidth,fps,url}]
  const probes = new Map();       // direct file url -> undefined | null (checking) | {width,height,duration,video,audio,segment,size,useUrl} | false
  const overlays = new Map();     // <video> -> its button
  let refreshTimer = 0;

  // ---------- shadow host ----------
  const host = el("div");
  host.style.cssText = "all:initial;position:fixed;top:0;left:0;width:0;height:0;z-index:2147483647;";
  const root = host.attachShadow({ mode: "closed" });
  try { const sh = new CSSStyleSheet(); sh.replaceSync(CSS); root.adoptedStyleSheets = [sh]; }
  catch { root.append(el("style", { textContent: CSS })); }
  document.documentElement.append(host);
  // our clicks must not reach the page (it would pause the video, close its menus ...)
  for (const t of ["pointerdown", "pointerup", "mousedown", "mouseup", "click", "dblclick", "contextmenu", "keydown", "keyup"]) root.addEventListener(t, (e) => e.stopPropagation());
  // a fullscreen <div> hides everything outside it: move our host inside while it is fullscreen
  document.addEventListener("fullscreenchange", () => {
    const fe = document.fullscreenElement;
    (fe && !["VIDEO", "IFRAME"].includes(fe.tagName) ? fe : document.documentElement).append(host);
    wake();
  });
  function applyVisibility() { host.style.display = cfg.overlay ? "" : "none"; if (!cfg.overlay) overlays.forEach(closeMenu); wake(); }

  // ---------- sniffed streams (fallback source) ----------
  async function loadItems() {
    const r = await send({ cmd: "list" });
    items = Array.isArray(r) ? r : [];
    for (const it of items) {
      if (it.kind === "hls" && !variants.has(it.url)) {
        variants.set(it.url, null);
        send({ cmd: "variants", url: it.url }).then((v) => { variants.set(it.url, Array.isArray(v) ? v : []); dataChanged(); });
      }
      if (it.kind === "file" && !probes.has(it.url)) {
        probes.set(it.url, null);
        send({ cmd: "probe", url: it.url }).then((p) => { probes.set(it.url, p || false); dataChanged(); });
      }
    }
    dataChanged();
  }
  function dataChanged() { overlays.forEach((ov) => ov.el.classList.contains("open") && renderList(ov)); }
  const refreshSoon = () => { clearTimeout(refreshTimer); refreshTimer = setTimeout(loadItems, 300); };

  function shownItems() {
    const kids = new Set();  // hide the per-quality playlists of a master we already list
    for (const v of variants.values()) (v || []).forEach((x) => kids.add(x.url));
    const height = (it) => { const p = probes.get(it.url); return p && p.video ? Math.min(p.width, p.height) : 0; };
    const rank = (it) => (it.kind === "hls" ? 2 : it.kind === "dash" ? 1 : 0);
    return items.filter((it) => !kids.has(it.url) && !(probes.get(it.url) || {}).segment && it.role !== "audio")  // audio halves are attached to their video, not listed
      .reverse().sort((x, y) => rank(y) - rank(x) || height(y) - height(x));
  }

  // FIX (no sound): the audio stream that belongs to a silent video file. The background pairs them by role (efg/mime/content-type) and load time;
  // if it couldn't tell, fall back to "an audio-only file of the same length".
  function audioFor(it) {
    if (it.kind !== "file") return "";
    if (it.audioUrl) return it.audioUrl;
    const p = probes.get(it.url);
    if (!p || !p.video || p.audio) return "";
    const best = items.filter((x) => x.kind === "file" && x.url !== it.url)
      .map((x) => ({ x, q: probes.get(x.url) })).filter(({ q }) => q && q.audio && !q.video && !q.segment)
      .sort((a, b) => Math.abs((a.q.duration || 0) - (p.duration || 0)) - Math.abs((b.q.duration || 0) - (p.duration || 0)))[0];
    return best && (!p.duration || !best.q.duration || Math.abs(best.q.duration - p.duration) <= 2.5) ? (best.q.useUrl || best.x.url) : "";
  }

  // The job for a sniffed stream. Video+audio files are sent together (audioUrl) so OpenDM downloads both and ffmpeg merges them.
  function jobFor(it, name, opts = {}) {
    const isHls = it.kind === "hls", isDash = it.kind === "dash";
    const vs = isHls ? variants.get(it.url) : undefined;
    const p = isHls || isDash ? undefined : probes.get(it.url);
    const v = opts.variant ?? null;
    const eff = v || (vs && vs.length ? vs[0] : null);
    const audioUrl = audioFor(it);
    const q = isHls ? (eff && eff.height ? eff.height + "p" : "") : isDash ? "" : (p && p.video ? Math.min(p.width, p.height) + "p" : "");
    const base = [safeName(name) || "video", q].filter(Boolean).join(" ");
    return {
      url: isHls || isDash ? it.url : (p && p.useUrl) || it.url, referer: it.page || location.href, kind: isHls ? "hls" : isDash ? "dash" : undefined,
      audioUrl: audioUrl || undefined,
      filename: isHls || isDash ? base : base + "." + (audioUrl ? "mp4" : p && p.audio && !p.video ? "m4a" : fileExt(it.url)),
      quality: v?.height || 0, bandwidth: v?.bandwidth || 0,
    };
  }

  // =====================================================================================================
  // "Download this video" button over every playing <video>
  // =====================================================================================================
  const MIN_W = 200, MIN_H = 110;
  const instKey = (v) => location.href + "|" + (v.currentSrc || v.src || "");  // new address or new source = new video "instance"

  let buttonOn = true;   // Configuration > General > "Show the Download this video button"
  Promise.resolve(api.runtime.sendMessage({ cmd: "cfg" })).then((c) => { if (c && c.video_button === false) { buttonOn = false; [...overlays.values()].forEach(destroy); } }).catch(() => {});
  function consider(v) {
    if (!buttonOn || !v || v.tagName !== "VIDEO" || overlays.has(v)) return;
    const ov = { v, played: !v.paused, closedKey: "", fmt: undefined, fmtMsg: "", nameDirty: false, w: 150, h: 30, key: instKey(v) };
    ov.nameInput = el("input", { type: "text", spellcheck: false, title: "File name - you can edit it" });
    ov.nameInput.oninput = () => { ov.nameDirty = true; };
    ov.list = el("div", { className: "ml" });
    ov.foot = el("div", { className: "mf" });
    ov.pill = el("div", { className: "pill", title: "Download this video with OpenDM  (drag to move, double-click to reset)" },
      el("img", { src: ICON }), el("span", { className: "lbl", textContent: "Download this video" }), el("span", { className: "car", textContent: "▾" }),
      el("button", { className: "x", textContent: "×", title: "Hide this button for this video", onclick: (e) => { e.stopPropagation(); ov.closedKey = instKey(v); closeMenu(ov); layout(ov); } }));
    ov.menu = el("div", { className: "menu" },
      el("div", { className: "mh" }, el("img", { src: ICON }), el("b", { textContent: "OpenDM · Download this video" }),
        el("button", { textContent: "×", title: "Close", onclick: () => closeMenu(ov) })),
      el("div", { className: "mn" }, ov.nameInput), ov.list, ov.foot);
    ov.el = el("div", { className: "ov" }, ov.pill, ov.menu);
    enableOverlayDrag(ov);
    root.append(ov.el);
    overlays.set(v, ov);
    if (typeof ResizeObserver === "function") { ov.ro = new ResizeObserver(wake); ov.ro.observe(v); }
    wake();
  }
  function destroy(ov) { ov.ro?.disconnect(); ov.el.remove(); overlays.delete(ov.v); }

  function shouldShow(ov, r) {
    const v = ov.v;
    if (!v.isConnected || !cfg.overlay) return false;
    if (!ov.played && v.paused) return false;                  // the button appears once the video has started playing
    if (ov.closedKey && ov.closedKey === instKey(v)) return false;
    if (r.width < MIN_W || r.height < MIN_H) return false;
    const vw = Math.min(r.right, innerWidth) - Math.max(r.left, 0), vh = Math.min(r.bottom, innerHeight) - Math.max(r.top, 0);
    return vw >= MIN_W * 0.8 && vh >= MIN_H * 0.8;
  }

  // Put the button on the video's top-right corner (or where the user dragged it); follows scrolling/resizing.
  function layout(ov) {
    const r = ov.v.getBoundingClientRect();
    if (!shouldShow(ov, r)) { ov.el.style.display = "none"; return false; }
    const k = instKey(ov.v);
    if (k !== ov.key) { ov.key = k; ov.fmt = undefined; ov.fmtMsg = ""; ov.nameDirty = false; if (ov.el.classList.contains("open")) closeMenu(ov); }
    ov.el.style.display = "block";
    ov.el.classList.toggle("compact", cfg.ovCompact);
    const w = ov.pill.offsetWidth || ov.w, h = ov.pill.offsetHeight || ov.h;
    ov.w = w; ov.h = h;
    const L = Math.max(r.left, 0), T = Math.max(r.top, 0), R = Math.min(r.right, innerWidth), B = Math.min(r.bottom, innerHeight);
    const left = clamp(R - ovOff.right - w, L + 2, Math.max(L + 2, R - w - 2));
    const top = clamp(T + ovOff.top, T + 2, Math.max(T + 2, B - h - 2));
    ov.el.style.transform = `translate(${Math.round(left)}px,${Math.round(top)}px)`;
    ov.vis = { L, T, R, B };
    if (ov.el.classList.contains("open")) {  // open the menu on the side with more room
      const below = innerHeight - (top + h) - 12, above = top - 12;
      const up = below < 240 && above > below;
      ov.menu.classList.toggle("up", up);
      ov.menu.classList.toggle("left", left + w - 330 < 4);
      ov.list.style.maxHeight = Math.max(120, Math.min(innerHeight * 0.6, (up ? above : below) - 110)) + "px";
    }
    return true;
  }

  let looping = false;
  function loop() {
    let any = false;
    for (const ov of [...overlays.values()]) { if (!ov.v.isConnected) { destroy(ov); continue; } any = layout(ov) || any; }
    if (any) requestAnimationFrame(loop); else looping = false;
  }
  function wake() { if (!looping && overlays.size) { looping = true; requestAnimationFrame(loop); } }

  function enableOverlayDrag(ov) {
    const pill = ov.pill;
    pill.addEventListener("pointerdown", (e) => {
      if (e.button !== 0 || e.target.closest(".x")) return;
      const sx = e.clientX, sy = e.clientY, r0 = ovOff.right, t0 = ovOff.top;
      let moved = false;
      try { pill.setPointerCapture(e.pointerId); } catch {}
      const move = (m) => {
        if (!moved && Math.abs(m.clientX - sx) + Math.abs(m.clientY - sy) < 5) return;
        moved = true; pill.classList.add("drag");
        const { L, T, R, B } = ov.vis || { L: 0, T: 0, R: innerWidth, B: innerHeight };
        ovOff.right = clamp(r0 - (m.clientX - sx), 0, Math.max(0, R - L - ov.w - 4));
        ovOff.top = clamp(t0 + (m.clientY - sy), 0, Math.max(0, B - T - ov.h - 4));
        layout(ov);
      };
      const up = () => {
        pill.removeEventListener("pointermove", move); pill.removeEventListener("pointerup", up); pill.classList.remove("drag");
        if (moved) api.storage.local.set({ ovOff: { right: ovOff.right, top: ovOff.top } });
        else toggleMenu(ov);
      };
      pill.addEventListener("pointermove", move); pill.addEventListener("pointerup", up);
    });
    pill.addEventListener("dblclick", (e) => {  // back to the top-right corner
      if (e.target.closest(".x")) return;
      Object.assign(ovOff, OV_HOME); api.storage.local.set({ ovOff: { ...OV_HOME } });
      closeMenu(ov); layout(ov);
    });
  }

  // ---- the quality menu
  function toggleMenu(ov) { ov.el.classList.contains("open") ? closeMenu(ov) : openMenu(ov); }
  function closeMenu(ov) { ov.el.classList.remove("open"); }
  async function openMenu(ov) {
    overlays.forEach((o) => o !== ov && closeMenu(o));
    ov.el.classList.add("open");
    if (!ov.nameDirty) ov.nameInput.value = ov.fmt?.title ? safeName(ov.fmt.title) : captionGuess(ov.v);
    ov.foot.className = "mf"; ov.foot.textContent = "Pick a quality to send it to OpenDM.";
    renderList(ov); layout(ov);
    const src = ov.v.currentSrc || ov.v.src || "";
    if (/^https?:/i.test(src)) await send({ cmd: "found", url: src });  // a plain <video src>: make sure it is in the list
    loadItems();
    if (ov.fmt === undefined) {  // ask OpenDM (yt-dlp) what this page offers: video AND audio formats
      ov.fmt = null;
      const r = await send({ cmd: "formats", url: pageUrlFor(ov.v), referer: location.href });
      ov.fmt = r && r.ok ? r : false;
      ov.fmtMsg = r && !r.ok ? (r.error || "") : (r === undefined ? "no answer" : "");
      ov.speed = r?.speed || 0;
      if (ov.fmt && ov.fmt.title && !ov.nameDirty) ov.nameInput.value = safeName(ov.fmt.title);
      if (ov.fmtMsg && !r?.missing && connected(ov.fmtMsg) && !/not a video page/i.test(ov.fmtMsg)) { ov.foot.className = "mf err"; ov.foot.textContent = errorHint(ov.fmtMsg); }
      renderList(ov);
    }
  }

  const etaFor = (ov, size) => {
    const bps = ov.speed || (navigator.connection?.downlink ? navigator.connection.downlink * 125000 : 0);
    return size > 0 && bps > 0 ? "~" + fmtEta(size / bps) : "";
  };

  // Choices for this video.
  //  1) yt-dlp formats (job kind "ytdlp"): OpenDM downloads best video + best audio and merges them with ffmpeg. Always has sound.
  //  2) ONLY if yt-dlp can't read the page: the streams the browser really loaded, each sent together with its paired audio stream.
  function choicesFor(ov) {
    const name = () => ov.nameInput.value;
    const page = pageUrlFor(ov.v);
    const rows = [];
    const f = ov.fmt;
    if (f && f.ok && (f.formats?.length || f.audio)) {
      for (const x of f.formats || []) {
        rows.push({ label: x.height + "p" + (x.fps > 30 ? x.fps : ""), tag: String(x.ext || "mp4").toUpperCase(), size: x.size, approx: x.approx, sub: "video + sound",
                    job: () => ({ url: page, kind: "ytdlp", quality: x.height, filename: [safeName(name()) || "video", x.height + "p"].join(" "), referer: location.href }) });
      }
      if (f.audio) rows.push({ label: "Audio only", tag: String(f.audio.ext || "m4a").toUpperCase(), size: f.audio.size, approx: f.audio.approx,
                               job: () => ({ url: page, kind: "ytdlp", quality: -1, filename: safeName(name()) || "audio", referer: location.href }) });
      return { rows, fallback: false, loading: 0 };
    }
    if (ov.fmt === null) return { rows, fallback: false, loading: 0 };   // still asking yt-dlp: don't flash raw streams that vanish a second later
    const all = shownItems(), src = ov.v.currentSrc || ov.v.src || "", dur = Number.isFinite(ov.v.duration) ? ov.v.duration : 0;
    const exact = all.filter((it) => src && (it.url === src || it.orig === src || (probes.get(it.url) || {}).useUrl === src));
    const sameLen = all.filter((it) => { const p = probes.get(it.url); return dur && p && p.duration && Math.abs(p.duration - dur) <= 1.5; });
    const mine = exact.length || sameLen.length ? [...new Set([...exact, ...sameLen])] : all.slice(0, 8);
    let loading = 0;
    for (const it of mine) {
      if (it.kind === "hls") {
        const vs = variants.get(it.url);
        if (vs == null) { loading++; continue; }
        if (!vs.length) rows.push({ label: "Original", tag: "HLS", size: 0, job: () => jobFor(it, name()) });
        for (const v of vs) rows.push({ label: v.height ? v.height + "p" + (v.fps > 30 ? v.fps : "") : "Audio / other", tag: "HLS", size: dur ? Math.round(v.bandwidth * dur / 8) : 0, approx: true,
                                       sub: dur ? "" : Math.round(v.bandwidth / 1000) + " kbps", job: () => jobFor(it, name(), { variant: v }) });
      } else if (it.kind === "dash") {
        rows.push({ label: "Best", tag: "DASH", size: 0, sub: "ffmpeg merges the streams", job: () => jobFor(it, name()) });
      } else {
        const p = probes.get(it.url);
        if (p === undefined || p === null) { loading++; continue; }
        if (p && p.segment) continue;
        const audio = audioFor(it);
        const apx = audio ? items.find((x) => x.url === audio) : null;
        const sz = ((p && p.size) || it.size || 0) + (apx ? ((probes.get(apx.url) || {}).size || apx.size || 0) : 0);
        const hasPic = p && p.video;
        rows.push({ label: hasPic ? Math.min(p.width, p.height) + "p" : p && p.audio ? "Audio only" : "Video", tag: audio ? "MP4" : extOf(it.url), size: sz,
                    sub: audio ? "video + sound" : hasPic && !p.audio ? "no sound" : "", job: () => jobFor(it, name()) });
      }
    }
    return { rows, fallback: true, loading };
  }

  function renderList(ov) {
    const { rows: choices, fallback, loading } = choicesFor(ov);
    const out = [];
    if (choices.length) out.push(el("div", { className: "sep", textContent: fallback ? "Detected on this page" : "Available qualities" }));
    for (const c of choices) {
      const bits = [c.size ? (c.approx ? "≈ " : "") + fmtSize(c.size) : "", etaFor(ov, c.size), c.sub].filter(Boolean).join(" · ");
      const q = el("div", { className: "q", title: "Send to OpenDM" }, el("span", { className: "ql", textContent: c.label }), el("span", { className: "chip", textContent: c.tag }),
                   el("span", { className: "qs", textContent: bits }), el("span", { className: "go", textContent: "⬇" }));
      q.onclick = async () => {
        q.classList.add("busy");
        const r = await send({ cmd: "send", job: c.job() });   // background adds cookies + user-agent, then hands it to OpenDM (native messaging / local API)
        q.classList.remove("busy");
        if (r?.ok) { ov.foot.className = "mf"; ov.foot.textContent = "Sent to OpenDM ✔ (" + c.label + ")"; }
        else { ov.foot.className = "mf err"; ov.foot.textContent = errorHint(r?.error); }
      };
      out.push(q);
    }
    if (ov.fmt === null) out.push(el("div", { className: "note", textContent: "Reading the video's streams…" }));
    else if (loading) out.push(el("div", { className: "note", textContent: "Checking detected streams…" }));
    if (!choices.length && ov.fmt !== null && !loading) {
      const missing = ov.fmt === false && /yt-dlp is not installed/i.test(ov.fmtMsg);
      out.push(el("div", { className: "note", textContent: missing
        ? "For every quality on YouTube, Facebook, Instagram and similar sites, install yt-dlp:  pip install yt-dlp  (then restart OpenDM)."
        : "No stream detected yet. Let the video play for a moment (or switch its quality), then open this menu again." }));
    }
    ov.list.replaceChildren(...out);
  }

  // ---------- finding videos: now, and as the page changes ----------
  const markPlayed = (v) => { consider(v); const ov = overlays.get(v); if (ov) { ov.played = true; wake(); } };
  window.addEventListener("playing", (e) => e.target?.tagName === "VIDEO" && markPlayed(e.target), true);
  window.addEventListener("play", (e) => e.target?.tagName === "VIDEO" && markPlayed(e.target), true);
  window.addEventListener("loadstart", (e) => { if (e.target?.tagName === "VIDEO") { consider(e.target); wake(); } }, true);  // reels / playlists swap the source
  let scanTimer = 0;
  function scan() {
    document.querySelectorAll("video").forEach(consider);
    for (const ov of [...overlays.values()]) if (!ov.v.isConnected) destroy(ov);
    wake();
  }
  const scanSoon = () => { if (!scanTimer) scanTimer = setTimeout(() => { scanTimer = 0; scan(); }, 120); };
  new MutationObserver(scanSoon).observe(document.documentElement, { childList: true, subtree: true });

  // Single-page sites change the address without reloading (YouTube, Instagram, Facebook reels): re-arm every button.
  let lastHref = location.href;
  const checkNav = () => {
    if (location.href === lastHref) return;
    lastHref = location.href;
    overlays.forEach((ov) => { ov.fmt = undefined; ov.fmtMsg = ""; ov.nameDirty = false; closeMenu(ov); });
    scanSoon(); wake();
  };
  setInterval(checkNav, 300);
  window.addEventListener("popstate", checkNav); window.addEventListener("hashchange", checkNav);
  try { window.navigation?.addEventListener("navigatesuccess", checkNav); } catch {}
  setInterval(wake, 600);
  for (const t of ["scroll", "resize"]) window.addEventListener(t, wake, { capture: true, passive: true });
  window.addEventListener("pointerdown", (e) => {  // a click anywhere else closes the menu
    const path = e.composedPath ? e.composedPath() : [];
    if (!path.includes(host)) overlays.forEach(closeMenu);
  }, true);
  window.addEventListener("keydown", (e) => { if (e.key === "Escape") overlays.forEach(closeMenu); }, true);

  // ---------- wiring ----------
  api.runtime.onMessage.addListener((m) => {
    if (m?.cmd === "media-updated") overlays.forEach((ov) => ov.el.classList.contains("open") && refreshSoon());
  });
  api.storage.onChanged.addListener((ch) => {
    if (ch.overlay) cfg.overlay = ch.overlay.newValue ?? true;
    if (ch.ovCompact) cfg.ovCompact = !!ch.ovCompact.newValue;
    if (ch.ovOff?.newValue) Object.assign(ovOff, ch.ovOff.newValue);
    applyVisibility();
  });
  api.storage.local.get({ overlay: true, ovCompact: false, ovOff: null }).then((c) => {
    cfg = { overlay: c.overlay, ovCompact: c.ovCompact };
    if (c.ovOff && Number.isFinite(c.ovOff.right) && Number.isFinite(c.ovOff.top)) Object.assign(ovOff, { right: Math.max(0, c.ovOff.right), top: Math.max(0, c.ovOff.top) });
    applyVisibility(); scan();
  });
})();
