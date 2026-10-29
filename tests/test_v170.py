"""v1.7.0: file names, native-host latency behaviour, immediate start."""
import io, json, os, struct, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import opendm


def frame(o):
    d = json.dumps(o).encode()
    return struct.pack("=I", len(d)) + d


def unframe(b):
    out, i = [], 0
    while i < len(b):
        (n,) = struct.unpack("=I", b[i:i + 4])
        out.append(json.loads(b[i + 4:i + 4 + n]))
        i += 4 + n
    return out


class TestNames(unittest.TestCase):
    def test_clean_name_windows_rules(self):
        c = opendm.clean_name
        self.assertEqual(c("CON"), "_CON")
        self.assertEqual(c("nul.mp4"), "_nul.mp4")
        self.assertEqual(c('a:b*c?.mp4'), "a_b_c_.mp4")
        self.assertEqual(c("x\u202ey\u200bz.mp4"), "xyz.mp4")
        self.assertEqual(c("  name...  "), "name")
        self.assertEqual(c(""), "download")
        self.assertEqual(c("Mr. Beast. Wow"), "Mr. Beast. Wow")
        long = c(("word " * 80) + ".mp4")
        self.assertTrue(long.endswith(".mp4") and len(long) <= opendm.MAX_STEM + 4, len(long))
        bn = "\u0987\u09a8\u09b6\u09be " * 60
        self.assertLessEqual(len(c(bn + ".mp4")), opendm.MAX_STEM + 4)

    def test_generic_titles_are_rejected(self):
        for t in ("Facebook", "Reels", "(3) Facebook", "Video", "Reel by Someone", "Name on Instagram", "12345", "  "):
            self.assertTrue(opendm.is_generic_title(t), t)
        self.assertFalse(opendm.is_generic_title("\u0987\u09a8\u09b6\u09be \u0986\u09b2\u09cd\u09b2\u09be\u09b9 \u09aa\u09be\u09b0\u09ab\u09c7\u0995\u09cd\u099f"))

    def test_pick_title_order(self):
        self.assertEqual(opendm.pick_title({"title": "Real - YouTube", "description": "other"}), "Real")
        self.assertEqual(opendm.pick_title({"title": "Facebook", "description": "\n The caption line\nsecond"}), "The caption line")
        self.assertEqual(opendm.pick_title({"title": "Facebook", "fulltitle": "Full one"}), "Full one")
        self.assertEqual(opendm.pick_title({"title": "Facebook", "id": "1"}), "")
        self.assertEqual(opendm.pick_title({"title": "123", "id": "123"}), "")
        self.assertLessEqual(len(opendm.pick_title({"title": "w " * 200})), 100)

    def test_fallback_title_is_descriptive(self):
        self.assertEqual(opendm.fallback_title({"extractor_key": "Facebook", "id": "1584636679632422"}), "Facebook video 1584636679632422")
        self.assertEqual(opendm.fallback_title({"webpage_url": "https://www.instagram.com/reel/abc/", "id": "abc"}), "Instagram video abc")
        self.assertEqual(opendm.fallback_title({}), "video")

    def test_summarize_formats_carries_title_and_fallback(self):
        r = opendm.summarize_formats({"title": "Facebook", "description": "Caption here", "id": "9", "extractor_key": "Facebook", "duration": 5,
                                      "formats": [{"height": 720, "vcodec": "avc1", "acodec": "mp4a", "ext": "mp4", "filesize": 1000}]})
        self.assertEqual((r["title"], r["fallback"]), ("Caption here", "Facebook video 9"))
        r = opendm.summarize_formats({"title": "Facebook", "id": "9", "extractor_key": "Facebook", "formats": []})
        self.assertEqual((r["title"], r["fallback"]), ("", "Facebook video 9"))


class TestHostLatency(unittest.TestCase):
    def host(self, codes, running=True):
        h = opendm.NativeHost(state_dir=tempfile.mkdtemp(), launch=lambda: launched.append(1), sleep=lambda s: None, wait_seconds=1)
        launched = self.launched = []
        h.calls = []
        seq = iter(codes)

        def call(method, path, body=None):
            h.calls.append(path)
            return next(seq)
        h._call = call
        h.alive = lambda: running or bool(launched)
        return h

    def test_add_is_one_request_when_running(self):
        h = self.host([200])
        self.assertEqual(h.handle({"cmd": "add", "job": {"url": "https://x.test/a.zip"}}), {"ok": True})
        self.assertEqual(h.calls, ["/add"])  # no /ping first
        self.assertEqual(self.launched, [])

    def test_add_starts_opendm_only_when_nothing_answers(self):
        h = self.host([0, 200], running=False)
        self.assertEqual(h.handle({"cmd": "add", "job": {"url": "https://x.test/a.zip"}}), {"ok": True})
        self.assertEqual((h.calls, len(self.launched)), (["/add", "/add"], 1))

    def test_prefetch_never_launches_opendm(self):
        h = self.host([], running=False)
        h._json_call = lambda path, body, timeout=80: (0, None)
        r = h.handle({"cmd": "formats", "job": {"url": "https://www.youtube.com/watch?v=1", "prefetch": True}})
        self.assertEqual((r["ok"], r.get("prefetch"), self.launched), (False, True, []))

    def test_replies_echo_id_and_slow_formats_does_not_block(self):
        import threading
        h = self.host([200])
        gate = threading.Event()

        def slow(path, body, timeout=80):
            gate.wait(5)
            return 200, {"ok": True, "formats": [{"height": 720}]}
        h._json_call = slow
        out = io.BytesIO()
        msgs = [{"cmd": "formats", "id": 1, "job": {"url": "https://www.youtube.com/watch?v=1"}}, {"cmd": "add", "id": 2, "job": {"url": "https://x.test/a.zip"}}]
        t = threading.Thread(target=lambda: h.serve(["--native-host"], io.BytesIO(b"".join(frame(m) for m in msgs)), out))
        t.start()
        for _ in range(100):  # the add (id 2) is answered while formats (id 1) is still waiting
            if out.getvalue():
                break
            threading.Event().wait(0.02)
        first = unframe(out.getvalue())
        self.assertEqual([r["id"] for r in first], [2])
        gate.set()
        t.join(10)
        self.assertEqual(sorted(r["id"] for r in unframe(out.getvalue())), [1, 2])


class TestKick(unittest.TestCase):
    def test_kick_starts_queued_downloads_now(self):
        m = opendm.Manager.__new__(opendm.Manager)
        started = []

        class D:
            status, force = "Queued", False

            def start(self):
                started.append(1)
                self.status = "Connecting"
        m.items, m.max_active = [D(), D(), D()], 2
        m.in_window = lambda: True
        m.kick()
        self.assertEqual(len(started), 2)  # respects the simultaneous-download limit


if __name__ == "__main__":
    unittest.main()
