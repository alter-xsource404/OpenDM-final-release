// v1.7 file-name resolution (extension/names.js)
const assert = require("assert"), N = require("../../extension/names.js");
const BN = "ইনশা আল্লাহ পারফেক্ট টাইমে প্রস্তুতি গুছিয়ে রিভিশন করতে পারলে শুরুর দিকেই চান্স হয়ে যাবে";
const fb = "https://www.facebook.com/reel/1584636679632422";
// the reported bug: generic "Facebook" from yt-dlp / tab title must not win over the real caption
assert.strictEqual(N.pickName({ ytTitle: "Facebook", dom: ["", BN], meta: ["Facebook"], pageUrl: fb }), BN);
// site title wins over caption when it is real
assert.strictEqual(N.pickName({ ytTitle: "Real Title - YouTube", dom: [BN], meta: [], pageUrl: fb }), "Real Title");
// nothing usable -> descriptive fallback, never a bare "Facebook"
assert.strictEqual(N.pickName({ ytTitle: "", dom: [], meta: ["Facebook", "(3) Facebook", "Reels"], pageUrl: fb }), "Facebook video 1584636679632422");
assert.strictEqual(N.pickName({ ytTitle: "", ytFallback: "Facebook video 99", dom: [], meta: ["Watch"], pageUrl: fb }), "Facebook video 99");
// metadata order: og:title before document.title
assert.strictEqual(N.pickName({ dom: [], meta: ["OG headline", "tab title"], pageUrl: fb }), "OG headline");
// Instagram caption wrapper
assert.strictEqual(N.cleanTitle('Some User on Instagram: "Hello world"'), "Hello world");
// Windows safety
assert.strictEqual(N.safeName("CON"), "_CON");
assert.strictEqual(N.safeName('a/b:c*d?"e<f>g|h'), "a-b-c d e f g h");
assert.strictEqual(N.safeName("name... "), "name");
assert.strictEqual(N.safeName("x\u202Ey\u200Bz"), "xyz");
// length: cut at a word, never in the middle of a Bengali/emoji code point
const long = (BN + " ").repeat(5), s = N.safeName(long);
assert(Array.from(s).length <= 120 && !/[\ud800-\udbff]$/.test(s) && !s.endsWith(" "), s.length);
const emoji = N.safeName("😀".repeat(300)); assert.strictEqual(Array.from(emoji).length, 120); assert(!/[\ud800-\udbff]$/.test(emoji));
assert.strictEqual(N.isGeneric("Facebook"), true); assert.strictEqual(N.isGeneric("12345"), true); assert.strictEqual(N.isGeneric(BN), false);
assert.strictEqual(N.fallbackName("https://www.youtube.com/watch?v=abcDEF12345"), "Youtube video abcDEF12345");
assert.strictEqual(N.fallbackName("not a url"), "video");
console.log("PASS names.js: generic titles rejected, caption beats tab title, Windows-safe, Unicode-safe, descriptive fallback");
