// OpenDM v1.7 - media file-name resolution (pure functions, no DOM; loaded before content.js and unit-tested in tests/js/names.test.js).
// Order: the site's own media title -> post caption / description -> page metadata -> a descriptive "<Site> video <id>" fallback.
(function (g) {
  "use strict";
  const SITES = "YouTube|Facebook|Instagram|TikTok|Twitter|X|Vimeo|Dailymotion|Reddit|Twitch|Bilibili|Rumble|Streamable";
  const TAIL = new RegExp("\\s*[-|\\u2013\\u2014\\u00b7]\\s*(?:" + SITES + ")\\s*$", "i");
  const GENERIC = new RegExp("^(?:" + SITES.toLowerCase() + "|home|watch|reels?|video|videos|stories|story|untitled|log ?in.*|sign ?in.*" +
    "|(?:facebook|instagram|tiktok|youtube) (?:video|reel|reels|watch)|(?:video|reel|photo) by .*|.* on (?:instagram|facebook|tiktok))$", "i");
  const RESERVED = /^(con|prn|aux|nul|com[1-9]|lpt[1-9])$/i;
  const cps = (s) => Array.from(s);   // count code points, so Bengali / emoji are never cut in half

  function shorten(t, n = 100) {
    t = String(t || "").replace(/\s+/g, " ").trim();
    const a = cps(t);
    if (a.length <= n) return t.replace(/[\s.\u2026]+$/, "");
    const cut = a.slice(0, n).join(""), sp = cut.lastIndexOf(" ");
    return (sp >= n * 0.6 ? cut.slice(0, sp) : cut).replace(/[\s.,;:\-\u2026]+$/, "");
  }
  // Windows-safe name part (no extension): forbidden characters, control/bidi characters, trailing dots, reserved device names, length.
  function safeName(s, n = 120) {
    let t = String(s || "").replace(/[\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff]/g, "").replace(/[\/\\:]+/g, "-").replace(/[?*"<>|\u0000-\u001f]+/g, " ")
      .replace(/\s+/g, " ").trim().replace(/^[. ]+|[. ]+$/g, "");
    t = shorten(t, n).replace(/^[. ]+|[. ]+$/g, "");
    return RESERVED.test(t) ? "_" + t : t;
  }
  function cleanTitle(t) {
    t = String(t || "").replace(/\s+/g, " ").trim().replace(/^\(\d+\+?\)\s*/, "");
    const ig = t.match(/^.{1,80}? on Instagram:\s*["\u201c](.+?)["\u201d]?\s*$/s);
    return (ig ? ig[1] : t).replace(TAIL, "").trim();
  }
  const isGeneric = (t) => { t = cleanTitle(t); return t.length < 3 || GENERIC.test(t) || /^[\p{N}\p{P}\p{S}\p{Z}_]+$/u.test(t); };
  // first candidate that really describes the media
  function firstGood(list) {
    for (const x of list || []) { const t = safeName(cleanTitle(x)); if (t.length >= 3 && !isGeneric(t)) return t; }
    return "";
  }
  // "Facebook video 1584636679632422" from the page address
  function fallbackName(pageUrl) {
    try {
      const u = new URL(pageUrl), host = u.hostname.replace(/^(www|m|mobile|web)\./, "");
      const brand = (host.split(".").slice(-2, -1)[0] || host);
      const id = u.searchParams.get("v") || (u.pathname.split("/").filter((s) => /^[\w-]{6,}$/.test(s)).pop() || "");
      return safeName([brand.charAt(0).toUpperCase() + brand.slice(1), "video", id.slice(0, 40)].filter(Boolean).join(" "));
    } catch { return "video"; }
  }
  // ytTitle: from OpenDM/yt-dlp ("" when generic); dom: [aria-label, post caption, structured data ...]; meta: [og:title, og:description, h1, title]
  function pickName({ ytTitle, ytFallback, dom, meta, pageUrl }) {
    return firstGood([ytTitle]) || firstGood(dom) || firstGood(meta) || safeName(ytFallback) || fallbackName(pageUrl);
  }
  const api = { shorten, safeName, cleanTitle, isGeneric, firstGood, fallbackName, pickName };
  g.OpenDMNames = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
