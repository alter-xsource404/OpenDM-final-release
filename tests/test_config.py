"""Tests for the Configuration window's backends: proxy / SOCKS, site logins, capture rules, start-up, sounds, antivirus, duplicates, the dialog itself.
Run with:  python -m unittest tests.test_config -v   (no network needed; uses local servers)"""
import http.server, json, os, socket, struct, sys, tempfile, threading, unittest, urllib.request
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import opendm


class Origin(http.server.BaseHTTPRequestHandler):
    seen = []

    def log_message(self, *a):
        pass

    def do_GET(self):
        Origin.seen.append({"path": self.path, "auth": self.headers.get("Authorization"), "proxy_auth": self.headers.get("Proxy-Authorization"), "host": self.headers.get("Host")})
        body = b"hello"
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def serve(handler):
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


class FakeSocks5(threading.Thread):
    """A tiny SOCKS5 server: records what was asked for, then connects to the real origin and relays."""
    def __init__(self, origin_port, user=None, pw=None):
        super().__init__(daemon=True)
        self.srv, self.origin_port, self.user, self.pw, self.asked = socket.socket(), origin_port, user, pw, []
        self.srv.bind(("127.0.0.1", 0))
        self.srv.listen(5)
        self.port = self.srv.getsockname()[1]
        self.start()

    def recv(self, c, n):
        b = b""
        while len(b) < n:
            b += c.recv(n - len(b))
        return b

    def run(self):
        while True:
            try:
                c, _ = self.srv.accept()
            except OSError:
                return
            try:
                self.recv(c, 1)
                n = self.recv(c, 1)[0]
                methods = self.recv(c, n)
                if self.user:
                    assert 2 in methods
                    c.sendall(b"\x05\x02")
                    self.recv(c, 1)
                    u = self.recv(c, self.recv(c, 1)[0]).decode()
                    p = self.recv(c, self.recv(c, 1)[0]).decode()
                    ok = (u, p) == (self.user, self.pw)
                    c.sendall(b"\x01" + (b"\x00" if ok else b"\x01"))
                    if not ok:
                        c.close()
                        continue
                else:
                    c.sendall(b"\x05\x00")
                self.recv(c, 3)
                atyp = self.recv(c, 1)[0]
                assert atyp == 3  # the name is resolved by the proxy
                host = self.recv(c, self.recv(c, 1)[0]).decode()
                port = struct.unpack(">H", self.recv(c, 2))[0]
                self.asked.append((host, port))
                up = socket.create_connection(("127.0.0.1", self.origin_port))
                c.sendall(b"\x05\x00\x00\x01\x00\x00\x00\x00\x00\x00")
                threading.Thread(target=self.pipe, args=(c, up), daemon=True).start()
                threading.Thread(target=self.pipe, args=(up, c), daemon=True).start()
            except Exception:
                c.close()

    @staticmethod
    def pipe(a, b):
        try:
            while True:
                d = a.recv(65536)
                if not d:
                    break
                b.sendall(d)
        except OSError:
            pass
        finally:
            for s in (a, b):
                try:
                    s.shutdown(socket.SHUT_WR)
                except OSError:
                    pass


class NetCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(self.restore)
        Origin.seen.clear()

    def restore(self):
        opendm.NET.overwrite, opendm.NET.temp_folder = False, ""
        opendm.NET.timeout, opendm.NET.retries = 30, 6


class TestRules(unittest.TestCase):
    def test_capture_decision(self):
        st = dict(opendm.DEFAULT_SETTINGS)
        cd = lambda url, name="", forced=False: opendm.capture_decision(st, url, name, forced)
        self.assertTrue(cd("https://x.test/setup.msi") and cd("https://x.test/v.mp4") and cd("https://x.test/doc.pdf"))
        self.assertFalse(cd("https://scontent.fbcdn.net/t39/845976594_n.jpeg") or cd("https://x.test/a.png") or cd("https://x.test/app.js"))   # page images / assets
        self.assertTrue(cd("https://release-assets.githubusercontent.com/github-production-release-asset/1432002929/7b144cf4"))   # no extension -> unknown types
        st["capture_unknown"] = False
        self.assertFalse(cd("https://release-assets.githubusercontent.com/x/7b144cf4"))
        self.assertTrue(cd("https://x.test/dl?id=1", "setup.exe"))                         # the file name beats the link
        self.assertTrue(cd("https://x.test/dl?id=1", forced=True))                          # force key
        st["exclude_sites"] = "blocked.test\n*.cdn.example"
        self.assertFalse(cd("https://blocked.test/a.zip") or cd("https://a.cdn.example/a.zip"))
        self.assertTrue(cd("https://blocked.test/a.zip", forced=True))                      # the force key beats every rule
        self.assertFalse(cd("ftp://x.test/a.zip") or cd("blob:https://x.test/1"))

    def test_images_are_not_a_default_capture_type(self):
        caps = opendm.split_list(opendm.DEFAULT_SETTINGS["capture_types"])
        self.assertIn("mp4", caps)
        self.assertNotIn("jpg", caps)
        self.assertNotIn("png", caps)

    def test_browser_config_is_clean_and_complete(self):
        st = dict(opendm.DEFAULT_SETTINGS, key_prevent="bogus", exclude_sites="A.test, *.b.test", min_size_kb="x")
        cfg = opendm.browser_config(st)
        self.assertEqual((cfg["key_prevent"], cfg["exclude_sites"], cfg["min_size_kb"]), ("alt", ["a.test", "b.test"], 0))
        self.assertEqual(sorted(cfg["browsers"]), ["brave", "chrome", "edge", "firefox", "other"])
        json.dumps(cfg)

    def test_config_endpoint_needs_the_token(self):
        mgr = opendm.Manager(persist=False)
        mgr.settings["exclude_sites"] = "z.test"
        port = socket.socket(); port.bind(("127.0.0.1", 0)); p = port.getsockname()[1]; port.close()
        srv = opendm.start_api(mgr, lambda: ("/tmp", 8), port=p, token="tok")
        req = lambda tok, method: urllib.request.Request(f"http://127.0.0.1:{p}/config", method=method, data=b"{}" if method == "POST" else None, headers={"X-OpenDM-Token": tok})
        for method in ("GET", "POST"):
            with urllib.request.urlopen(req("tok", method), timeout=5) as r:
                self.assertEqual(json.loads(r.read())["exclude_sites"], ["z.test"])
            with self.assertRaises(urllib.error.HTTPError):
                urllib.request.urlopen(req("bad", method), timeout=5)
        srv.shutdown()


class TestSystem(NetCase):
    def test_autostart_writes_and_removes_the_entry(self):
        if os.name == "nt":
            self.skipTest("uses the registry on Windows")
        self.assertEqual(opendm.set_autostart(True, ["/usr/bin/python3", "/opt/my dir/opendm.py", "--minimized"], home=self.tmp), "")
        path = os.path.join(self.tmp, ".config", "autostart", "opendm.desktop") if sys.platform != "darwin" else os.path.join(self.tmp, "Library", "LaunchAgents", "org.opendm.plist")
        body = open(path).read()
        self.assertIn("--minimized", body)
        self.assertIn("my dir", body)
        self.assertEqual(opendm.set_autostart(False, ["x"], home=self.tmp), "")
        self.assertFalse(os.path.exists(path))

    def test_temp_folder_and_overwrite(self):
        opendm.OPENER.configure({"temp_folder": os.path.join(self.tmp, "tmp"), "file_exists": "overwrite"})
        self.assertEqual(opendm.parts_dir(os.path.join("C:\\x" if os.name == "nt" else "/x", "v.mp4")), os.path.join(self.tmp, "tmp", "v.mp4.parts"))
        d = opendm.Download("http://x.test/f.bin", self.tmp)
        d.name = "f.bin"
        open(os.path.join(self.tmp, "f.bin"), "wb").write(b"old")
        d._plan()
        self.assertEqual(os.path.basename(d.path), "f.bin")             # replaced, not "f (1).bin"
        opendm.OPENER.configure({"file_exists": "rename"})
        open(os.path.join(self.tmp, "f.bin"), "wb").write(b"old")
        d2 = opendm.Download("http://x.test/f.bin", self.tmp)
        d2.name = "f.bin"
        d2._plan()
        self.assertEqual(os.path.basename(d2.path), "f (1).bin")


# ---------------- GUI pieces, driven with a stand-in toolkit (no display needed) ----------------
class Var:
    def __init__(self, value=None):
        self.v = value

    def get(self):
        return self.v

    def set(self, v):
        self.v = v

    def trace_add(self, *a):
        pass


class Text:
    def __init__(self, *a, **k):
        self.t = ""

    def insert(self, _i, s):
        self.t += s

    def delete(self, *a):
        self.t = ""

    def get(self, *a):
        return self.t + "\n"

    def pack(self, *a, **k):
        pass

    def __getattr__(self, name):          # focus_set, bind, ... : accepted and ignored
        return lambda *a, **k: None


class Tree:
    def __init__(self, *a, **k):
        self.rows, self.n, self.sel = {}, 0, ()

    def insert(self, _p, _i, values=()):
        self.n += 1
        self.rows[f"I{self.n}"] = tuple(values)
        return f"I{self.n}"

    def item(self, iid, option=None, values=None):
        if values is not None:
            self.rows[iid] = tuple(values)
        return self.rows[iid]

    def get_children(self):
        return tuple(self.rows)

    def selection(self):
        return self.sel

    def delete(self, *iid):
        self.rows.pop(iid, None)

    def __getattr__(self, name):
        return lambda *a, **k: None


class Widget:
    """Just enough of a tk widget for click_wanted()."""
    def __init__(self, cls, **k):
        self.cls, self.k = cls, k

    def winfo_class(self):
        return self.cls

    def instate(self, flags):
        return bool(self.k.get("disabled"))

    def index(self, spec):
        if not self.k.get("on_tab"):
            raise RuntimeError("not on a tab")
        return 0

    def identify_region(self, x, y):
        return self.k.get("region", "nothing")

    def identify_row(self, y):
        return "I001" if self.k.get("row") else ""

    def identify(self, x, y):
        return self.k.get("element", "entry")

    def nearest(self, y):
        return 0

    def bbox(self, i):
        return (0, 0, 10, 20) if self.k.get("row") else ()


class Event:
    def __init__(self, widget, x=5, y=5):
        self.widget, self.x, self.y = widget, x, y


class TestGui(NetCase):
    def make_app(self):
        tkm = mock.MagicMock()
        tkm.TclError = type("TclError", (Exception,), {})
        tkm.StringVar = tkm.BooleanVar = tkm.IntVar = Var
        tkm.Text = Text
        ttkm = mock.MagicMock()
        ttkm.Treeview = Tree
        for name, val in (("tk", tkm), ("ttk", ttkm), ("messagebox", mock.MagicMock()), ("filedialog", mock.MagicMock())):
            p = mock.patch.object(opendm, name, val, create=True)
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.object(opendm, "get_token", lambda *a: "tok")
        p.start()
        self.addCleanup(p.stop)
        app = object.__new__(opendm.App)
        app.mgr, app.root = opendm.Manager(persist=False), mock.MagicMock()
        app.mgr.save_settings = mock.Mock()
        app.folder, app.conns, app.limit_var = Var(os.path.join(self.tmp, "dl")), Var(8), Var(0)
        app.tray, app.set_tray, app.port, app.api_srv, app.note = None, mock.Mock(return_value=""), 6800, True, ("", 0)
        app.widget = mock.MagicMock()
        app.widget.shown = False
        app.toggle_widget = app.apply_theme = mock.Mock()
        app.captured, app.pending_urls, app.pwins = __import__("queue").Queue(), set(), {}
        return app, ttkm

    def press(self, ttkm, text):
        calls = [c for c in ttkm.Button.call_args_list if c.kwargs.get("text") == text]
        calls[-1].kwargs["command"]()

    def test_configuration_window_saves_everything(self):
        app, ttkm = self.make_app()
        st = app.mgr.settings
        st.update(timeout=45, exclude_sites="x.test", dup_links="skip")
        app.options_dialog()
        self.press(ttkm, "OK")
        self.assertEqual((st["timeout"], st["dup_links"], st["exclude_sites"]), (45, "skip", "x.test"))
        self.assertTrue(opendm.NET.timeout == 45)
        self.assertIn("mp4", st["capture_types"].split())
        self.assertEqual(st["key_prevent"], "alt")
        self.assertEqual(sorted(st["capture_browsers"]), ["brave", "chrome", "edge", "firefox", "other"])
        app.mgr.save_settings.assert_called()

    def test_configuration_window_rejects_an_incomplete_proxy(self):
        app, ttkm = self.make_app()
        app.mgr.settings.update(proxy_mode="manual", proxy_host="", proxy_port=0)
        app.options_dialog()
        self.press(ttkm, "OK")
        opendm.messagebox.showerror.assert_called_once()
        app.mgr.save_settings.assert_not_called()

    def test_duplicates_and_clipboard(self):
        app, _ = self.make_app()
        app.flash = mock.Mock()
        u = "https://x.test/file.zip"
        dl = opendm.Download(u, self.tmp)
        app.mgr.items.append(dl)
        opendm.messagebox.askyesno.return_value = False
        self.assertFalse(app.dup_ok(u))                                  # ask -> user says no
        opendm.messagebox.askyesno.return_value = True
        self.assertTrue(app.dup_ok(u))
        app.mgr.settings["dup_links"] = "skip"
        self.assertFalse(app.dup_ok(u))
        app.mgr.settings["dup_links"] = "add"
        self.assertTrue(app.dup_ok(u))
        self.assertTrue(app.dup_ok("https://x.test/other.zip"))
        # clipboard: the first look only records; later file links are offered, other text and images are not
        st = app.mgr.settings
        st["clip_monitor"] = True
        clip = ["https://x.test/already-there.zip"]
        app.root.clipboard_get = lambda: clip[0]
        for text, expect in ((clip[0], 0), ("https://x.test/new.zip", 1), ("https://x.test/photo.jpg", 0), ("just some words", 0), ("https://x.test/a.mp4\nhttps://x.test/b.mp4", 0)):
            clip[0] = text
            app._autoclip_t = 0
            before = app.captured.qsize()
            app.poll_clipboard()
            self.assertEqual(app.captured.qsize() - before, expect, text)
        st["clip_monitor"] = False
        app.poll_clipboard()
        self.assertIsNone(app._autoclip_last)


if __name__ == "__main__":
    unittest.main()
