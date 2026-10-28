"""Wave 1 tests: checksums, proxies + logins, FTP, resume safety, automatic retry, sounds, theme palette.
Run with:  python -m unittest discover -s tests -v   (no network needed; every server here is local)"""
import base64, hashlib, http.server, json, os, re, shutil, socket, socketserver, struct, sys, tempfile, threading, time, unittest
import urllib.error, urllib.request
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import opendm

DATA = os.urandom(3 * 1024 * 1024)
FAKE = "fake.opendm.test"  # a name no DNS knows: it only works if the proxy resolves it


# ------------------------------------------------------------------ little servers
def send(h, code, body=b"", headers=None):
    h.send_response(code)
    for k, v in (headers or {}).items():
        h.send_header(k, v)
    h.send_header("Content-Length", str(len(body)))
    h.end_headers()
    if h.command != "HEAD":
        try:
            h.wfile.write(body)
        except OSError:
            pass


def serve_bytes(h, body, headers=None):
    """200 / 206 with Range and If-Range handled the way RFC 7233 says."""
    hd, rng, ifr = dict(headers or {}), h.headers.get("Range"), h.headers.get("If-Range")
    if rng and ifr and ifr not in (hd.get("ETag"), hd.get("Last-Modified")):
        rng = None  # the file isn't the one the client started with: send all of it
    if rng:
        a, b = re.match(r"bytes=(\d+)-(\d*)", rng).groups()
        a, b = int(a), int(b) if b else len(body) - 1
        return send(h, 206, body[a:b + 1], {**hd, "Content-Range": f"bytes {a}-{b}/{len(body)}"})
    send(h, 200, body, hd)


def start_http(fn, port=0):
    seen = []

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            seen.append((self.path, dict(self.headers)))
            fn(self)
        do_HEAD = do_GET
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    srv.seen, srv.url = seen, f"http://127.0.0.1:{srv.server_address[1]}"
    return srv


def start_proxy(user=None, pw=None):
    """A forward HTTP proxy. Requests for FAKE are sent on to 127.0.0.1 (that is the proxy 'resolving' the name)."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def fn(h):
        if user is not None:
            want = "Basic " + base64.b64encode(f"{user}:{pw}".encode()).decode()
            if h.headers.get("Proxy-Authorization") != want:
                return send(h, 407, b"", {"Proxy-Authenticate": 'Basic realm="p"'})
        req = urllib.request.Request(h.path.replace(FAKE, "127.0.0.1"), headers={k: v for k, v in h.headers.items() if k.lower() in ("range", "if-range")}, method=h.command)
        try:
            with opener.open(req, timeout=10) as r:
                keep = {k: v for k, v in r.headers.items() if k in ("Content-Range", "ETag")}
                send(h, r.status, r.read() if h.command != "HEAD" else b"", keep)
        except urllib.error.HTTPError as e:
            send(h, e.code, b"")
    return start_http(fn)


def _recv_n(s, n):
    buf = b""
    while len(buf) < n:
        c = s.recv(n - len(buf))
        if not c:
            raise OSError("closed")
        buf += c
    return buf


def start_socks(user=None, pw=None):
    """A SOCKS5 server (RFC 1928 / 1929). Names are resolved here: FAKE means 127.0.0.1."""
    log = []

    class H(socketserver.BaseRequestHandler):
        def handle(self):
            s = self.request
            try:
                _, n = _recv_n(s, 2)
                methods = _recv_n(s, n)
                if user is not None:
                    if 2 not in methods:
                        return s.sendall(b"\x05\xff")
                    s.sendall(b"\x05\x02")
                    _recv_n(s, 1)
                    u = _recv_n(s, _recv_n(s, 1)[0]).decode()
                    p = _recv_n(s, _recv_n(s, 1)[0]).decode()
                    ok = (u, p) == (user, pw)
                    s.sendall(b"\x01" + (b"\x00" if ok else b"\x01"))
                    if not ok:
                        return
                else:
                    s.sendall(b"\x05\x00")
                _, _, _, atyp = _recv_n(s, 4)
                host = socket.inet_ntoa(_recv_n(s, 4)) if atyp == 1 else _recv_n(s, _recv_n(s, 1)[0]).decode() if atyp == 3 else "?"
                port = struct.unpack(">H", _recv_n(s, 2))[0]
                log.append((atyp, host, port))
                up = socket.create_connection(("127.0.0.1" if host == FAKE else host, port), timeout=5)
                s.sendall(b"\x05\x00\x00\x01\x00\x00\x00\x00\x00\x00")

                def pump(a, b):
                    try:
                        while True:
                            d = a.recv(65536)
                            if not d:
                                break
                            b.sendall(d)
                    except OSError:
                        pass
                    finally:
                        for x in (a, b):
                            try:
                                x.shutdown(socket.SHUT_RDWR)
                            except OSError:
                                pass
                t = threading.Thread(target=pump, args=(up, s), daemon=True)
                t.start()
                pump(s, up)
                t.join(2)
            except OSError:
                pass

    class Srv(socketserver.ThreadingTCPServer):
        allow_reuse_address, daemon_threads = True, True
    srv = Srv(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    srv.log, srv.port = log, srv.server_address[1]
    return srv


class MiniFtp:
    """Just enough of an FTP server for ftplib: USER/PASS, TYPE, SIZE, REST, CWD, PASV, RETR, QUIT."""

    def __init__(self, files, user=None, pw=None):
        self.files, self.user, self.pw, self.log = files, user, pw, []
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(8)
        self.port = self.sock.getsockname()[1]
        threading.Thread(target=self.serve, daemon=True).start()

    def close(self):
        self.sock.close()

    def serve(self):
        while True:
            try:
                c, _ = self.sock.accept()
            except OSError:
                return
            threading.Thread(target=self.handle, args=(c,), daemon=True).start()

    def handle(self, c):
        say = lambda t: c.sendall((t + "\r\n").encode())
        say("220 mini ftp")
        rest, pasv, who, authed = 0, None, None, self.user is None
        try:
            for line in c.makefile("rb"):
                cmd, _, arg = line.decode().rstrip("\r\n").partition(" ")
                cmd = cmd.upper()
                self.log.append((cmd, arg))
                if cmd == "USER":
                    who = arg
                    say("331 password please")
                elif cmd == "PASS":
                    authed = self.user is None or (who, arg) == (self.user, self.pw)
                    say("230 welcome" if authed else "530 login incorrect")
                elif cmd == "QUIT":
                    say("221 bye")
                    break
                elif not authed:
                    say("530 please log in")
                elif cmd == "TYPE":
                    say("200 binary")
                elif cmd == "SIZE":
                    say(f"213 {len(self.files[arg])}" if arg in self.files else "550 no such file")
                elif cmd == "REST":
                    rest = int(arg)
                    say("350 restarting")
                elif cmd == "CWD":
                    say("250 ok" if arg == "/" or any(k.startswith(arg.rstrip("/") + "/") for k in self.files) else "550 not a directory")
                elif cmd == "PASV":
                    pasv = socket.socket()
                    pasv.bind(("127.0.0.1", 0))
                    pasv.listen(1)
                    p = pasv.getsockname()[1]
                    say(f"227 Entering Passive Mode (127,0,0,1,{p >> 8},{p & 255})")
                elif cmd == "RETR":
                    if arg not in self.files:
                        say("550 no such file")
                        continue
                    say("150 sending")
                    conn, _ = pasv.accept()
                    try:
                        conn.sendall(self.files[arg][rest:])
                    except OSError:
                        pass
                    conn.close()
                    rest = 0
                    say("226 done")
                else:
                    say("502 not implemented")
        except OSError:
            pass
        finally:
            c.close()


# ------------------------------------------------------------------ helpers
def run(d, timeout=60):
    d.start()
    t = time.time()
    while d.status in ("Connecting", "Downloading", "Queued") and time.time() - t < timeout:
        time.sleep(0.02)
    return d


def drive(mgr, cond, timeout=30):
    """Call mgr.schedule() the way the window does, until cond() or timeout. Returns cond()."""
    t = time.time()
    while time.time() - t < timeout:
        mgr.schedule()
        if cond():
            return True
        time.sleep(0.05)
    return cond()


def sha(b, algo="sha256"):
    return hashlib.new(algo, b).hexdigest()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp, self.servers = tempfile.mkdtemp(), []
        opendm.OPENER.configure({})

    def tearDown(self):
        opendm.GLOBAL_LIMIT.set_rate(0)
        opendm.OPENER.configure({})
        for s in self.servers:
            if hasattr(s, "shutdown"):
                s.shutdown()
                s.server_close()
            elif hasattr(s, "close"):
                s.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def http(self, fn, port=0):
        s = start_http(fn, port)
        self.servers.append(s)
        return s

    def file_server(self, body=DATA, headers=None):
        return self.http(lambda h: serve_bytes(h, body, headers) if h.path.startswith("/f") else send(h, 404))

    def ftp(self, *a, **k):
        s = MiniFtp(*a, **k)
        self.servers.append(s)
        return s


# ------------------------------------------------------------------ checksums
class TestChecksum(Base):
    def test_parse_forms(self):
        h = sha(b"x")
        self.assertEqual(opendm.parse_checksum(h), ("sha256", h))
        self.assertEqual(opendm.parse_checksum("SHA256:" + h.upper()), ("sha256", h))
        self.assertEqual(opendm.parse_checksum("sha-256 = " + h), ("sha256", h))
        self.assertEqual(opendm.parse_checksum(h + " *setup.exe"), ("sha256", h))  # sha256sum output
        self.assertEqual(opendm.parse_checksum(sha(b"x", "md5"))[0], "md5")
        self.assertEqual(opendm.parse_checksum(sha(b"x", "sha1"))[0], "sha1")
        self.assertEqual(opendm.parse_checksum(sha(b"x", "sha512"))[0], "sha512")

    def test_rejects_garbage_and_mislabelled(self):
        for bad in ("", "hello", "abc123", "sha256:" + sha(b"x", "md5"), "zz" * 32, "md5:" + sha(b"x")):
            self.assertIsNone(opendm.parse_checksum(bad), bad)
        self.assertEqual(opendm.normalize_checksum("   "), "")
        with self.assertRaises(ValueError):
            opendm.normalize_checksum("not a hash")

    def test_hash_file_multi(self):
        p = os.path.join(self.tmp, "a.bin")
        open(p, "wb").write(DATA)
        got = opendm.hash_file_multi(p)
        for a in opendm.HASH_ALGOS:
            self.assertEqual(got[a], sha(DATA, a))
        stop = threading.Event()
        stop.set()
        self.assertEqual(opendm.hash_file_multi(p, stop=stop), {})
        self.assertIsNone(opendm.hash_file(p, "md5", stop=stop))

    def _fetch(self, checksum):
        srv = self.file_server()
        mgr = opendm.Manager(persist=False)
        d = mgr.add(srv.url + "/f.bin", self.tmp, 2, checksum=checksum)
        self.assertTrue(drive(mgr, lambda: d.verified != "" or d.status == "Error"), d.error)
        return mgr, d

    def test_good_hash_is_verified(self):
        _, d = self._fetch("sha256:" + sha(DATA))
        self.assertEqual((d.status, d.verified), ("Completed", "ok"))
        self.assertEqual(opendm.status_text(d), "Complete (hash OK)")

    def test_bad_hash_is_flagged_and_file_kept(self):
        _, d = self._fetch("md5:" + sha(b"other", "md5"))
        self.assertEqual((d.status, d.verified), ("Completed", "bad"))
        self.assertEqual(d.actual_hash, sha(DATA, "md5"))
        self.assertIn("MISMATCH", opendm.status_text(d))
        self.assertTrue(os.path.exists(d.path))

    def test_checksum_set_after_completion_is_checked(self):
        srv = self.file_server()
        mgr = opendm.Manager(persist=False)
        d = mgr.add(srv.url + "/f.bin", self.tmp, 2)
        self.assertTrue(drive(mgr, lambda: d.status == "Completed"))
        self.assertEqual(d.verified, "")
        d.set_checksum(sha(DATA, "sha1"))
        self.assertTrue(drive(mgr, lambda: d.verified == "ok"))
        d.set_checksum(sha(b"nope", "sha1"))  # changing the value clears the old verdict
        self.assertEqual(d.verified, "")
        self.assertTrue(drive(mgr, lambda: d.verified == "bad"))

    def test_missing_file(self):
        d = opendm.Download("http://x.test/f", self.tmp)
        d.status, d.path, d.checksum = "Completed", os.path.join(self.tmp, "gone"), "md5:" + sha(b"", "md5")
        self.assertEqual(d.verify(), "missing")

    def test_persisted(self):
        d = opendm.Download("http://x.test/f", self.tmp)
        d.set_checksum(sha(b"1"))
        d.verified, d.validator = "ok", '"abc"'
        d2 = opendm.Download.from_dict(json.loads(json.dumps(d.to_dict())))
        self.assertEqual((d2.checksum, d2.verified, d2.validator), ("sha256:" + sha(b"1"), "ok", '"abc"'))

    def test_add_rejects_bad_checksum(self):
        with self.assertRaises(ValueError):
            opendm.Manager(persist=False).add("http://x.test/f", self.tmp, checksum="12345")


# ------------------------------------------------------------------ proxies, logins
class TestNetHelpers(unittest.TestCase):
    def test_split_login(self):
        self.assertEqual(opendm.split_login("ftp://me:p%40ss@host:21/a/b.zip?x=1"), ("ftp://host:21/a/b.zip?x=1", ("me", "p@ss")))
        self.assertEqual(opendm.split_login("http://host/f"), ("http://host/f", None))
        self.assertEqual(opendm.split_login("http://me@host/f"), ("http://host/f", ("me", "")))

    def test_bypass(self):
        b = opendm.parse_bypass("example.com, *.corp.test; 10.0.0.0/8")
        for host in ("localhost", "127.0.0.1", "example.com", "www.example.com", "a.b.corp.test", "corp.test", "10.2.3.4"):
            self.assertTrue(opendm.bypass_match(host, b), host)
        for host in ("example.org", "notexample.com", "11.0.0.1", "evil-example.com"):
            self.assertFalse(opendm.bypass_match(host, b), host)
        self.assertTrue(opendm.bypass_match("anything", ["*"]))

    def test_proxy_url_and_parse(self):
        st = {"proxy_mode": "manual", "proxy_type": "http", "proxy_host": "h.test", "proxy_port": 3128, "proxy_user": "me@x", "proxy_pass": "p:w/"}
        self.assertEqual(opendm.proxy_url(st), "http://me%40x:p%3Aw%2F@h.test:3128")
        self.assertEqual(opendm.proxy_url({**st, "proxy_type": "socks5", "proxy_port": 0}), "socks5h://me%40x:p%3Aw%2F@h.test:1080")
        self.assertEqual(opendm.proxy_url({**st, "proxy_mode": "system"}), "")
        back = opendm.parse_proxy(opendm.proxy_url(st))
        self.assertEqual((back["proxy_user"], back["proxy_pass"], back["proxy_port"]), ("me@x", "p:w/", 3128))
        self.assertEqual(opendm.parse_proxy("socks5://1.2.3.4")["proxy_type"], "socks5")
        with self.assertRaises(ValueError):
            opendm.parse_proxy("ftp://nope")

    def test_is_transient_and_retry_after(self):
        mk = lambda c, h=None: urllib.error.HTTPError("http://x", c, "m", h or {}, None)
        for c in (408, 429, 500, 502, 503):
            self.assertTrue(opendm.is_transient(mk(c)), c)
        for c in (401, 403, 404, 410):
            self.assertFalse(opendm.is_transient(mk(c)), c)
        self.assertTrue(opendm.is_transient(urllib.error.URLError("dns")))
        self.assertTrue(opendm.is_transient(ConnectionResetError()))
        self.assertFalse(opendm.is_transient(IOError("the server returned an empty file")))
        self.assertEqual(opendm.retry_after(mk(503, {"Retry-After": "7"})), 7)
        self.assertEqual(opendm.retry_after(mk(503, {"Retry-After": "9999"})), 120)
        self.assertEqual(opendm.retry_after(mk(503, {"Retry-After": "soon"})), 0)
        self.assertEqual(opendm.retry_after(mk(503, {})), 0)
        self.assertEqual(opendm.retry_after(ValueError("x")), 0)
        when = time.strftime("%a, %d %b %Y %H:%M:%S GMT", time.gmtime(time.time() + 30))
        self.assertTrue(25 <= opendm.retry_after(mk(503, {"Retry-After": when})) <= 31)


class TestProxy(Base):
    def cfg(self, **kw):
        return {"proxy_mode": "manual", "proxy_type": "http", "proxy_host": "127.0.0.1", **kw}

    def test_http_proxy_with_login(self):
        origin, proxy = self.file_server(), start_proxy("bob", "s3cret")
        self.servers.append(proxy)
        opendm.OPENER.configure(self.cfg(proxy_port=proxy.server_address[1], proxy_user="bob", proxy_pass="s3cret"))
        d = run(opendm.Download(f"http://{FAKE}:{origin.server_address[1]}/f.bin", self.tmp, 3))
        self.assertEqual(d.status, "Completed", d.error)
        self.assertEqual(sha(open(d.path, "rb").read()), sha(DATA))
        self.assertTrue(all(p.startswith("http://" + FAKE) for p, _ in proxy.seen))  # absolute-form requests = really went through the proxy
        self.assertTrue(all("Proxy-Authorization" in h for _, h in proxy.seen))

    def test_http_proxy_wrong_login_is_a_permanent_error(self):
        origin, proxy = self.file_server(), start_proxy("bob", "s3cret")
        self.servers.append(proxy)
        opendm.OPENER.configure(self.cfg(proxy_port=proxy.server_address[1], proxy_user="bob", proxy_pass="wrong"))
        d = run(opendm.Download(f"http://{FAKE}:{origin.server_address[1]}/f.bin", self.tmp, 2))
        self.assertEqual(d.status, "Error")
        self.assertIn("407", d.error)
        self.assertFalse(d.transient)

    def test_socks5_resolves_names_on_the_proxy_and_logs_in(self):
        origin, socks = self.file_server(), start_socks("u", "p")
        self.servers.append(socks)
        opendm.OPENER.configure(self.cfg(proxy_type="socks5", proxy_port=socks.port, proxy_user="u", proxy_pass="p"))
        d = run(opendm.Download(f"http://{FAKE}:{origin.server_address[1]}/f.bin", self.tmp, 3))
        self.assertEqual(d.status, "Completed", d.error)
        self.assertEqual(sha(open(d.path, "rb").read()), sha(DATA))
        self.assertTrue(socks.log and all(a == 3 and h == FAKE for a, h, _ in socks.log))  # sent as a *name* (ATYP 3)

    def test_socks5_wrong_password_fails(self):
        origin, socks = self.file_server(), start_socks("u", "p")
        self.servers.append(socks)
        opendm.OPENER.configure(self.cfg(proxy_type="socks5", proxy_port=socks.port, proxy_user="u", proxy_pass="nope"))
        d = run(opendm.Download(f"http://{FAKE}:{origin.server_address[1]}/f.bin", self.tmp, 1))
        self.assertEqual(d.status, "Error")
        self.assertIn("refused the user name", d.error)
        self.assertFalse(d.transient)

    def test_socks5_connect_refused_by_target(self):
        socks = start_socks()
        self.servers.append(socks)
        with self.assertRaises(opendm.SocksError):
            opendm.socks5_connect(("127.0.0.1", socks.port), ("127.0.0.1", 1))  # nothing listens on port 1

    def test_local_addresses_skip_the_proxy(self):
        origin, socks = self.file_server(), start_socks()
        self.servers.append(socks)
        opendm.OPENER.configure(self.cfg(proxy_type="socks5", proxy_port=socks.port))
        d = run(opendm.Download(origin.url + "/f.bin", self.tmp, 2))
        self.assertEqual(d.status, "Completed", d.error)
        self.assertEqual(socks.log, [])

    def test_custom_bypass_list(self):
        origin, proxy = self.file_server(), start_proxy()
        self.servers.append(proxy)
        opendm.OPENER.configure(self.cfg(proxy_port=proxy.server_address[1], proxy_bypass=FAKE))
        # FAKE cannot be resolved without the proxy, so a bypassed FAKE must fail: it did not use the proxy
        d = run(opendm.Download(f"http://{FAKE}:{origin.server_address[1]}/f.bin", self.tmp, 1))
        self.assertEqual(d.status, "Error")
        self.assertEqual(proxy.seen, [])

    def test_none_ignores_the_environment_and_system_obeys_it(self):
        origin = self.file_server()
        env = {"http_proxy": "http://127.0.0.1:1", "HTTP_PROXY": "http://127.0.0.1:1"}
        with mock.patch.dict(os.environ, env):
            for k in ("no_proxy", "NO_PROXY"):
                os.environ.pop(k, None)
            opendm.OPENER.configure({"proxy_mode": "none"})
            self.assertEqual(run(opendm.Download(origin.url + "/f.bin", self.tmp, 1)).status, "Completed")
            opendm.OPENER.configure({"proxy_mode": "system"})
            with self.assertRaises(Exception):
                opendm.OPENER.open(urllib.request.Request(origin.url + "/f.bin"), timeout=5)

    def test_check_proxy(self):
        origin, proxy = self.file_server(), start_proxy("a", "b")
        self.servers.append(proxy)
        url = f"http://{FAKE}:{origin.server_address[1]}/f.bin"
        ok, msg = opendm.check_proxy(self.cfg(proxy_port=proxy.server_address[1], proxy_user="a", proxy_pass="b"), url)
        self.assertTrue(ok, msg)
        ok, msg = opendm.check_proxy(self.cfg(proxy_port=proxy.server_address[1]), url)
        self.assertFalse(ok)
        self.assertIn("user name", msg)
        ok, _ = opendm.check_proxy(self.cfg(proxy_port=1), url, timeout=3)
        self.assertFalse(ok)

    def test_ytdlp_and_ffmpeg_get_the_proxy(self):
        opendm.OPENER.configure(self.cfg(proxy_port=3128, proxy_user="u", proxy_pass="p"))
        self.assertEqual(opendm.ytdlp_opts()["proxy"], "http://u:p@127.0.0.1:3128")
        self.assertEqual(opendm.OPENER.ffmpeg_proxy_args(), ["-http_proxy", "http://u:p@127.0.0.1:3128"])
        opendm.OPENER.configure(self.cfg(proxy_type="socks5", proxy_port=1080))
        self.assertEqual(opendm.ytdlp_opts()["proxy"], "socks5h://127.0.0.1:1080")
        self.assertEqual(opendm.OPENER.ffmpeg_proxy_args(), [])  # ffmpeg can't do SOCKS for http
        opendm.OPENER.configure({"proxy_mode": "none"})
        self.assertEqual(opendm.ytdlp_opts()["proxy"], "")
        opendm.OPENER.configure({})
        self.assertNotIn("proxy", opendm.ytdlp_opts())


class TestLogins(Base):
    def auth_server(self, user="bob", pw="s3cret"):
        want = "Basic " + base64.b64encode(f"{user}:{pw}".encode()).decode()

        def fn(h):
            if h.headers.get("Authorization") != want:
                return send(h, 401, b"", {"WWW-Authenticate": 'Basic realm="files"'})
            serve_bytes(h, DATA)
        return self.http(fn)

    def test_site_login_from_settings(self):
        srv = self.auth_server()
        opendm.OPENER.configure({"site_logins": [{"host": "127.0.0.1", "user": "bob", "pass": "s3cret"}]})
        d = run(opendm.Download(srv.url + "/f.bin", self.tmp, 3))
        self.assertEqual(d.status, "Completed", d.error)
        self.assertEqual(sha(open(d.path, "rb").read()), sha(DATA))

    def test_no_login_is_a_permanent_error(self):
        d = run(opendm.Download(self.auth_server().url + "/f.bin", self.tmp, 2))
        self.assertEqual(d.status, "Error")
        self.assertIn("401", d.error)
        self.assertFalse(d.transient)

    def test_wrong_login(self):
        opendm.OPENER.configure({"site_logins": [{"host": "127.0.0.1", "user": "bob", "pass": "nope"}]})
        d = run(opendm.Download(self.auth_server().url + "/f.bin", self.tmp, 2))
        self.assertEqual(d.status, "Error")

    def test_credentials_in_the_link(self):
        srv = self.auth_server()
        host = srv.url.split("//")[1]
        d = run(opendm.Download(f"http://bob:s3cret@{host}/f.bin", self.tmp, 2))
        self.assertEqual(d.status, "Completed", d.error)
        self.assertEqual(d.url, srv.url + "/f.bin")  # the password is not part of the address
        self.assertNotIn("s3cret", d.url)
        self.assertEqual(tuple(d.login), ("bob", "s3cret"))
        d2 = opendm.Download.from_dict(json.loads(json.dumps(d.to_dict())))  # still known after a restart, so it can resume
        self.assertEqual(tuple(d2.login), ("bob", "s3cret"))

    def test_authorization_is_not_forwarded_to_another_host(self):
        b = self.http(lambda h: send(h, 200, b"ok"))
        a = self.http(lambda h: send(h, 302, b"", {"Location": b.url + "/landing"}))
        opendm.OPENER.open(urllib.request.Request(a.url + "/x", headers={"Authorization": "Basic eHg6eXk=", "Cookie": "s=1"}), timeout=5).read()
        self.assertIn("Authorization", a.seen[0][1])
        self.assertNotIn("Authorization", b.seen[0][1])
        self.assertNotIn("Cookie", b.seen[0][1])


# ------------------------------------------------------------------ FTP
class TestFtp(Base):
    FILES = {"/pub/data.bin": DATA, "/pub/readme": b"hello ftp", "/pub/empty.txt": b""}

    def test_detect_kind_and_manager(self):
        self.assertEqual(opendm.detect_kind("ftp://h/f.zip"), "ftp")
        self.assertEqual(opendm.detect_kind("FTPS://h/f.zip"), "ftp")
        d = opendm.Manager(persist=False).add("ftp://me:pw@h.test/f.zip", self.tmp)
        self.assertIsInstance(d, opendm.FtpDownload)
        self.assertEqual((d.connections, d.url), (1, "ftp://h.test/f.zip"))
        self.assertNotIn("pw", d.desc)

    def test_anonymous_download(self):
        s = self.ftp(self.FILES)
        d = run(opendm.Download.from_dict({"kind": "ftp", "url": f"ftp://127.0.0.1:{s.port}/pub/data.bin", "folder": self.tmp}))
        self.assertEqual(d.status, "Completed", d.error)
        self.assertEqual(d.name, "data.bin")
        self.assertEqual(sha(open(d.path, "rb").read()), sha(DATA))
        self.assertIn(("USER", "anonymous"), s.log)

    def test_file_without_extension(self):
        s = self.ftp(self.FILES)
        d = run(opendm.FtpDownload(f"ftp://127.0.0.1:{s.port}/pub/readme", self.tmp))
        self.assertEqual((d.status, open(d.path, "rb").read()), ("Completed", b"hello ftp"))

    def test_login_in_link_and_from_settings(self):
        s = self.ftp(self.FILES, "ann", "pw")
        d = run(opendm.FtpDownload(f"ftp://ann:pw@127.0.0.1:{s.port}/pub/data.bin", self.tmp))
        self.assertEqual(d.status, "Completed", d.error)
        opendm.OPENER.configure({"site_logins": [{"host": "127.0.0.1", "user": "ann", "pass": "pw"}]})
        d2 = run(opendm.FtpDownload(f"ftp://127.0.0.1:{s.port}/pub/readme", self.tmp))
        self.assertEqual(d2.status, "Completed", d2.error)

    def test_wrong_login_fails_fast_and_is_permanent(self):
        s = self.ftp(self.FILES, "ann", "pw")
        t = time.time()
        d = run(opendm.FtpDownload(f"ftp://ann:bad@127.0.0.1:{s.port}/pub/data.bin", self.tmp))
        self.assertEqual(d.status, "Error")
        self.assertIn("530", d.error)
        self.assertFalse(d.transient)
        self.assertLess(time.time() - t, 8)

    def test_missing_file_and_folder(self):
        s = self.ftp(self.FILES)
        d = run(opendm.FtpDownload(f"ftp://127.0.0.1:{s.port}/pub/nope.zip", self.tmp))
        self.assertEqual(d.status, "Error")
        self.assertFalse(d.transient)
        d = run(opendm.FtpDownload(f"ftp://127.0.0.1:{s.port}/pub", self.tmp))
        self.assertEqual(d.status, "Error")
        self.assertIn("folder", d.error)

    def test_pause_and_resume_uses_rest(self):
        s = self.ftp(self.FILES)
        opendm.GLOBAL_LIMIT.set_rate(1 << 20)
        d = opendm.FtpDownload(f"ftp://127.0.0.1:{s.port}/pub/data.bin", self.tmp)
        d.start()
        time.sleep(1.0)
        d.pause()
        d.thread.join()
        self.assertEqual(d.status, "Paused")
        self.assertTrue(0 < d.percent < 100, d.percent)
        d2 = opendm.Download.from_dict(json.loads(json.dumps(d.to_dict())))
        self.assertIsInstance(d2, opendm.FtpDownload)
        opendm.GLOBAL_LIMIT.set_rate(0)
        run(d2)
        self.assertEqual(d2.status, "Completed", d2.error)
        self.assertEqual(sha(open(d2.path, "rb").read()), sha(DATA))
        self.assertTrue(any(c == "REST" and int(a) > 0 for c, a in s.log), s.log)

    def test_ftp_is_not_accepted_from_the_browser_api(self):
        mgr = opendm.Manager(persist=False)
        srv = opendm.start_api(mgr, lambda: (self.tmp, 2), free_port())
        self.servers.append(srv)
        r = urllib.request.Request(f"http://127.0.0.1:{srv.server_address[1]}/add", data=json.dumps({"url": "ftp://h/f.zip"}).encode(),
                                   headers={"X-OpenDM-Token": opendm.get_token(), "Content-Type": "application/json"})
        with self.assertRaises(urllib.error.HTTPError):
            urllib.request.urlopen(r, timeout=5)
        self.assertEqual(mgr.items, [])


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ------------------------------------------------------------------ resume safety
class TestResumeSafety(Base):
    def test_validator_choice(self):
        for headers, want in (({"ETag": '"v1"'}, '"v1"'), ({"ETag": 'W/"weak"'}, ""), ({"ETag": 'W/"w"', "Last-Modified": "Mon, 01 Jan 2024 00:00:00 GMT"}, "Mon, 01 Jan 2024 00:00:00 GMT"), ({}, "")):
            srv = self.file_server(headers=headers)
            d = opendm.Download(srv.url + "/f.bin", self.tmp)
            d._probe()
            self.assertEqual(d.validator, want, headers)

    def _pause_midway(self, srv):
        opendm.GLOBAL_LIMIT.set_rate(1 << 20)
        d = opendm.Download(srv.url + "/f.bin", self.tmp, 2)
        d.start()
        time.sleep(0.8)
        d.pause()
        d.thread.join()
        self.assertEqual(d.status, "Paused")
        self.assertTrue(0 < d.percent < 100)
        opendm.GLOBAL_LIMIT.set_rate(0)
        return json.loads(json.dumps(d.to_dict()))

    def test_unchanged_file_resumes_with_if_range(self):
        srv = self.file_server(headers={"ETag": '"v1"'})
        state = self._pause_midway(srv)
        n = len(srv.seen)
        d = run(opendm.Download.from_dict(state))
        self.assertEqual(d.status, "Completed", d.error)
        self.assertEqual(sha(open(d.path, "rb").read()), sha(DATA))
        self.assertEqual(d.replans, 0)
        later = [h for _, h in srv.seen[n:]]
        self.assertTrue(later and all(h.get("If-Range") == '"v1"' for h in later))

    def test_changed_file_starts_over_instead_of_corrupting(self):
        content = {"body": DATA, "tag": '"v1"'}
        srv = self.http(lambda h: serve_bytes(h, content["body"], {"ETag": content["tag"]}))
        state = self._pause_midway(srv)
        content["body"], content["tag"] = os.urandom(len(DATA)), '"v2"'  # replaced on the server
        d = run(opendm.Download.from_dict(state))
        self.assertEqual(d.status, "Completed", d.error)
        self.assertEqual(sha(open(d.path, "rb").read()), sha(content["body"]))
        self.assertEqual(d.replans, 1)
        self.assertEqual(d.validator, '"v2"')

    def test_flapping_etag_does_not_loop_forever(self):
        n = [0]

        def fn(h):
            n[0] += 1
            serve_bytes(h, DATA, {"ETag": f'"e{n[0]}"'})  # a different tag on every request, like some CDNs
        state = self._pause_midway(self.http(fn))
        d = run(opendm.Download.from_dict(state), timeout=40)
        self.assertEqual(d.status, "Completed", d.error)
        self.assertEqual(sha(open(d.path, "rb").read()), sha(DATA))
        self.assertLessEqual(d.replans, 1)

    def test_retry_after_is_honoured(self):
        hits = [0]

        def fn(h):
            hits[0] += 1
            if hits[0] == 2:  # request 1 is the probe; the first real transfer request is told to wait
                return send(h, 503, b"", {"Retry-After": "3"})
            serve_bytes(h, DATA[:500_000])
        srv = self.http(fn)
        t = time.time()
        d = run(opendm.Download(srv.url + "/f.bin", self.tmp, 1))
        self.assertEqual(d.status, "Completed", d.error)
        self.assertGreaterEqual(time.time() - t, 2.8)

    def test_pause_interrupts_a_long_wait(self):
        hits = [0]

        def fn(h):
            hits[0] += 1
            if hits[0] >= 2:
                return send(h, 503, b"", {"Retry-After": "100"})
            serve_bytes(h, DATA)
        d = opendm.Download(self.http(fn).url + "/f.bin", self.tmp, 1)
        d.start()
        time.sleep(1.0)
        t = time.time()
        d.pause()
        d.thread.join(5)
        self.assertFalse(d.thread.is_alive())
        self.assertLess(time.time() - t, 4)


# ------------------------------------------------------------------ automatic retry
class TestAutoRetry(Base):
    def mgr(self, **st):
        m = opendm.Manager(persist=False)
        m.NET_POLL, m.NET_FRESH = 0.05, 5
        m.net_check = lambda: True
        m.settings.update(st)
        return m

    def test_transient_failure_is_retried_until_it_works(self):
        port = free_port()  # nothing listens yet: connection refused
        mgr = self.mgr()
        with mock.patch.object(opendm, "RETRY_DELAYS", (0.05,)):
            d = mgr.add(f"http://127.0.0.1:{port}/f.bin", self.tmp, 2)
            self.assertTrue(drive(mgr, lambda: d.status == "Error", 20))
            self.assertTrue(d.transient)
            self.assertTrue(drive(mgr, lambda: d.retries >= 1, 20))
            self.http(lambda h: serve_bytes(h, DATA), port)  # the 'network' is back
            self.assertTrue(drive(mgr, lambda: d.status == "Completed", 30), (d.status, d.error))
        self.assertEqual(sha(open(d.path, "rb").read()), sha(DATA))
        self.assertEqual(d.retries, 0)  # success resets the counter

    def test_gives_up_after_retry_max(self):
        mgr = self.mgr(retry_max=1)
        with mock.patch.object(opendm, "RETRY_DELAYS", (0.05,)):
            d = mgr.add(f"http://127.0.0.1:{free_port()}/f.bin", self.tmp, 1)
            self.assertTrue(drive(mgr, lambda: d.retries == 1 and d.status == "Error" and d.retry_at == 0 and not mgr.will_retry(d), 30))
            time.sleep(0.5)
            drive(mgr, lambda: False, 0.5)
        self.assertEqual((d.status, d.retries), ("Error", 1))

    def test_offline_does_not_use_up_attempts(self):
        online = [False]
        mgr = self.mgr()
        mgr.net_check = lambda: online[0]
        with mock.patch.object(opendm, "RETRY_DELAYS", (0.05,)):
            d = mgr.add(f"http://127.0.0.1:{free_port()}/f.bin", self.tmp, 1)
            self.assertTrue(drive(mgr, lambda: d.status == "Error", 20))
            drive(mgr, lambda: False, 1.5)  # well past the retry time, but we are 'offline'
            self.assertEqual((d.status, d.retries), ("Error", 0))
            self.assertIn("waiting for network", opendm.status_text(d))
            online[0] = True
            self.assertTrue(drive(mgr, lambda: d.retries >= 1, 20))

    def test_permanent_errors_are_not_retried(self):
        mgr = self.mgr()
        srv = self.http(lambda h: send(h, 404))
        d = mgr.add(srv.url + "/f.bin", self.tmp, 1)
        self.assertTrue(drive(mgr, lambda: d.status == "Error", 20))
        drive(mgr, lambda: False, 0.5)
        self.assertEqual((d.transient, d.retry_at, d.retries), (False, 0.0, 0))

    def test_can_be_switched_off(self):
        mgr = self.mgr(auto_retry=False)
        d = mgr.add(f"http://127.0.0.1:{free_port()}/f.bin", self.tmp, 1)
        self.assertTrue(drive(mgr, lambda: d.status == "Error", 20))
        drive(mgr, lambda: False, 0.5)
        self.assertEqual((d.retries, d.retry_at), (0, 0.0))

    def test_manual_resume_resets_the_counters(self):
        d = opendm.Download("http://127.0.0.1:1/f.bin", self.tmp)
        d.retries, d.retry_at, d.status = 3, time.time() + 99, "Error"
        d.thread = None
        with mock.patch.object(d, "_run", lambda: None):
            d.start()
            d.thread.join()
        self.assertEqual((d.retries, d.retry_at), (0, 0.0))

    def test_status_text_counts_down(self):
        d = opendm.Download("http://x.test/f", self.tmp)
        d.status, d.error, d.transient, d.retry_at = "Error", "timed out", True, time.time() + 30
        self.assertRegex(opendm.status_text(d), r"retry in \d+s: timed out")


# ------------------------------------------------------------------ sounds
class TestSound(unittest.TestCase):
    def test_plan_per_platform(self):
        have = lambda *names: (lambda p: p in names)
        self.assertEqual(opendm.sound_plan("error", "Windows"), ("win", "SystemHand", False))
        self.assertEqual(opendm.sound_plan("complete", "Windows", "C:/a.wav", exists=lambda p: True), ("win", "C:/a.wav", True))
        self.assertEqual(opendm.sound_plan("complete", "Windows", "C:/a.mp3", exists=lambda p: True), ("win", "SystemAsterisk", False))  # winsound plays only .wav
        self.assertEqual(opendm.sound_plan("error", "Darwin", which=lambda c: "/x/afplay", exists=lambda p: True), ("cmd", ["afplay", "/System/Library/Sounds/Basso.aiff"]))
        self.assertIsNone(opendm.sound_plan("error", "Darwin", which=lambda c: None, exists=lambda p: True))
        plan = opendm.sound_plan("complete", "Linux", which=lambda c: c if c == "paplay" else None, exists=lambda p: p.endswith("complete.oga"))
        self.assertEqual(plan, ("cmd", ["paplay", "/usr/share/sounds/freedesktop/stereo/complete.oga"]))
        self.assertIsNone(opendm.sound_plan("complete", "Linux", which=lambda c: None, exists=lambda p: True))  # no player installed
        self.assertIsNone(opendm.sound_plan("complete", "Linux", which=lambda c: c, exists=lambda p: False))  # no sound file
        ap = opendm.sound_plan("complete", "Linux", which=lambda c: c if c == "aplay" else None, exists=lambda p: p.endswith(".oga"))
        self.assertIsNone(ap)  # aplay can't play ogg
        ap = opendm.sound_plan("complete", "Linux", "/me/ding.wav", which=lambda c: c if c == "aplay" else None, exists=lambda p: True)
        self.assertEqual(ap, ("cmd", ["aplay", "-q", "/me/ding.wav"]))

    def player(self, **st):
        played, now = [], [1000.0]
        p = opendm.SoundPlayer({**opendm.DEFAULT_SETTINGS, **st}, runner=lambda ev, custom: played.append((ev, custom)) or True, clock=lambda: now[0])
        p.t, p.played = now, played
        return p

    def test_priority_picks_one_sound_per_burst(self):
        p = self.player()
        self.assertEqual(p.flush({"complete", "all_done"}), "all_done")  # the queue finishing replaces the last 'ding'
        p.t[0] += 5
        self.assertEqual(p.flush({"complete", "error", "all_done"}), "error")
        p.t[0] += 5
        self.assertIsNone(p.flush(set()))
        self.assertEqual([e for e, _ in p.played], ["all_done", "error"])

    def test_min_gap(self):
        p = self.player()
        self.assertEqual(p.flush({"complete"}), "complete")
        p.t[0] += 0.5
        self.assertIsNone(p.flush({"complete"}))
        p.t[0] += 2
        self.assertEqual(p.flush({"complete"}), "complete")

    def test_switches(self):
        self.assertIsNone(self.player(sound=False).flush({"error"}))
        p = self.player(sound_error=False)
        self.assertEqual(p.flush({"error", "complete"}), "complete")  # the next-best enabled event is played instead

    def test_quiet_hours_and_focus(self):
        p = self.player(sound_quiet=True, sound_quiet_from="22:00", sound_quiet_to="07:00")
        self.assertFalse(p.allowed("complete", now_min=23 * 60))
        self.assertFalse(p.allowed("complete", now_min=3 * 60))
        self.assertTrue(p.allowed("complete", now_min=12 * 60))
        self.assertFalse(opendm.in_hours("10:00", "10:00", 600))
        self.assertTrue(opendm.in_hours("09:00", "17:00", 600))
        focused = [True]
        p = opendm.SoundPlayer({**opendm.DEFAULT_SETTINGS, "sound_unfocused_only": True}, focused=lambda: focused[0], runner=lambda *a: True)
        self.assertFalse(p.allowed("complete"))
        focused[0] = False
        self.assertTrue(p.allowed("complete"))

    def test_custom_file_and_fallback(self):
        p = self.player(sound_files={"error": "/me/boom.wav"})
        p.flush({"error"})
        self.assertEqual(p.played, [("error", "/me/boom.wav")])
        bell = []
        p = opendm.SoundPlayer(dict(opendm.DEFAULT_SETTINGS), runner=lambda *a: False)
        p.fallback = lambda: bell.append(1)
        p.flush({"complete"})
        self.assertEqual(bell, [1])  # nothing could play: the window's bell is the fallback


# ------------------------------------------------------------------ theme palette
class TestTheme(unittest.TestCase):
    def tearDown(self):
        opendm.set_palette(opendm.make_palette("light"))

    def test_helpers(self):
        self.assertEqual(opendm.valid_hex(" #ABCDEF "), "#abcdef")
        for bad in ("", "red", "#fff", "#12345g", None):
            self.assertEqual(opendm.valid_hex(bad), "")
        self.assertEqual(opendm.mix("#000000", "#ffffff", 0.5), "#808080")
        self.assertEqual(opendm.contrast_fg("#ffffff"), "#000000")
        self.assertEqual(opendm.contrast_fg("#000000"), "#ffffff")
        self.assertEqual(opendm.contrast_fg(opendm.DEFAULT_ACCENT), "#ffffff")

    def test_palettes_are_complete_and_readable(self):
        light, dark = opendm.make_palette("light"), opendm.make_palette("dark", "#ea580c")
        self.assertEqual(set(light), set(dark))
        self.assertEqual((light["mode"], dark["mode"]), ("light", "dark"))
        self.assertEqual(opendm.make_palette("nonsense")["mode"], "light")
        self.assertEqual(opendm.make_palette("dark", "garbage")["accent"], opendm.DEFAULT_ACCENT)
        self.assertEqual(light["accent_soft"], "#bfdbfe")  # the original light look is unchanged
        self.assertLess(opendm.luminance(dark["bg"]), 0.05)
        for name, hexv in opendm.ACCENTS:
            p = opendm.make_palette("dark", hexv)
            self.assertEqual(p["accent"], hexv, name)
            self.assertIn(p["accent_fg"], ("#000000", "#ffffff"))

    def test_mode_resolution(self):
        self.assertEqual(opendm.resolve_mode("dark"), "dark")
        self.assertEqual(opendm.resolve_mode("light"), "light")
        with mock.patch.object(opendm, "system_is_dark", return_value=True):
            self.assertEqual(opendm.resolve_mode("system"), "dark")
        with mock.patch.object(opendm, "system_is_dark", return_value=False):
            self.assertEqual(opendm.resolve_mode("system"), "light")

    def test_graph_follows_the_palette(self):
        class Cv:
            def __init__(self):
                self.calls = []

            def delete(self, *a):
                pass

            def winfo_width(self):
                return 400

            def winfo_height(self):
                return 110

            def __getattr__(self, name):
                return lambda *a, **k: self.calls.append((name, k))
        opendm.set_palette(opendm.make_palette("dark", "#16a34a"))
        cv = Cv()
        opendm.draw_graph(cv, [100.0, 200.0, 300.0])
        fills = {k.get("fill") for _, k in cv.calls}
        self.assertIn("#16a34a", fills)
        self.assertIn(opendm.PAL["accent_soft"], fills)
        self.assertNotIn("#2563eb", fills)
        cv = Cv()
        opendm.draw_segmap(cv, [(0.0, 1.0, 0.5)])
        self.assertIn("#16a34a", {k.get("fill") for _, k in cv.calls})


# ------------------------------------------------------------------ command line
class TestCli(Base):
    def cli(self, *args):
        import subprocess
        r = subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "opendm.py"), *args],
                           capture_output=True, text=True, timeout=60, env={**os.environ, "HOME": self.tmp, "USERPROFILE": self.tmp})
        return r.returncode, r.stdout + r.stderr

    def test_checksum_ok_and_mismatch(self):
        srv = self.file_server()
        rc, out = self.cli(srv.url + "/f.bin", "-o", self.tmp, "--checksum", "sha256:" + sha(DATA))
        self.assertEqual(rc, 0, out)
        self.assertIn("matches", out)
        rc, out = self.cli(srv.url + "/f.bin", "-o", os.path.join(self.tmp, "b"), "--checksum", "md5:" + sha(b"no", "md5"))
        self.assertEqual(rc, 1, out)
        self.assertIn("DOES NOT MATCH", out)

    def test_bad_options(self):
        rc, out = self.cli("http://x.test/f", "--checksum", "nonsense")
        self.assertEqual(rc, 2, out)
        rc, out = self.cli("http://x.test/a", "http://x.test/b", "--checksum", sha(b"1"))
        self.assertEqual(rc, 2, out)
        rc, out = self.cli("http://x.test/a", "--proxy", "ftp://nope")
        self.assertEqual(rc, 2, out)

    def test_failed_download_exit_code(self):
        srv = self.http(lambda h: send(h, 404))
        rc, out = self.cli(srv.url + "/f.bin", "-o", self.tmp)
        self.assertEqual(rc, 1, out)


if __name__ == "__main__":
    unittest.main()
