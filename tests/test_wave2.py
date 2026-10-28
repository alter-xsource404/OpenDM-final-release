"""Wave 2 tests: antivirus scan, smart link resolver, clipboard history, skins, toolbar layout.
Run with:  python -m unittest discover -s tests -v   (no network, no antivirus and no display needed: scanners are faked, servers are local)"""
import base64, json, os, stat, subprocess, sys, tempfile, textwrap, threading, time, unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import opendm
from test_wave1 import Base, send, drive, DATA


# ------------------------------------------------------------------ antivirus
class TestFindAv(unittest.TestCase):
    def _win(self, files, prefer="auto", which=None):
        env = {"ProgramData": "C:/PD", "ProgramFiles": "C:/PF", "ProgramFiles(x86)": "C:/PF86"}
        plat = [f for f in files if "Platform" in f]
        return opendm.find_av(prefer, system="Windows", env=env, which=which or (lambda n: None), isfile=lambda p: p in files, globber=lambda pat: plat)

    def test_defender_newest_platform_folder_wins(self):
        old, new = "C:/PD/Microsoft/Windows Defender/Platform/4.18.9-0/MpCmdRun.exe", "C:/PD/Microsoft/Windows Defender/Platform/4.18.10-0/MpCmdRun.exe"
        self.assertEqual(self._win([old, new]), ("defender", new))  # 4.18.10 is newer than 4.18.9 (numbers, not text)

    def test_defender_falls_back_to_program_files(self):
        pf = "C:/PF/Windows Defender/MpCmdRun.exe"
        self.assertEqual(self._win([pf]), ("defender", pf))

    def test_clamav_on_windows_and_preference(self):
        clam = "C:/PF/ClamAV/clamscan.exe"
        pf = "C:/PF/Windows Defender/MpCmdRun.exe"
        self.assertEqual(self._win([clam]), ("clamav", clam))
        self.assertEqual(self._win([clam, pf])[0], "defender")  # auto: Defender first
        self.assertEqual(self._win([clam, pf], "clamav")[0], "clamav")
        self.assertIsNone(self._win([clam], "defender"))  # an explicit choice is not silently swapped

    def test_linux_uses_clamscan_from_path_and_never_defender(self):
        found = opendm.find_av("auto", system="Linux", env={}, which=lambda n: "/usr/bin/clamscan" if n == "clamscan" else None, isfile=lambda p: True)
        self.assertEqual(found, ("clamav", "/usr/bin/clamscan"))
        self.assertIsNone(opendm.find_av("auto", system="Linux", env={}, which=lambda n: None, isfile=lambda p: True))

    def test_nothing_installed(self):
        self.assertIsNone(self._win([]))


class TestAvParsing(unittest.TestCase):
    def test_commands(self):
        c = opendm.av_command("defender", "MpCmdRun.exe", "C:/x.exe")
        self.assertEqual(c[:2], ["MpCmdRun.exe", "-Scan"])
        self.assertIn("-DisableRemediation", c)  # report only: OpenDM doesn't delete files by itself
        self.assertEqual(c[c.index("-File") + 1], "C:/x.exe")
        self.assertEqual(opendm.av_command("clamav", "clamscan", "/t/x")[-1], "/t/x")

    def test_defender_codes(self):
        self.assertEqual(opendm.parse_av("defender", 0, "Scan finished."), ("clean", ""))
        out = "Scanning C:/x found 1 threats.\nThreat                  : Virus:DOS/EICAR_Test_File\nResources : 1 total\n"
        self.assertEqual(opendm.parse_av("defender", 2, out), ("infected", "Virus:DOS/EICAR_Test_File"))
        self.assertEqual(opendm.parse_av("defender", 2, "found threats")[0], "infected")
        self.assertEqual(opendm.parse_av("defender", 1, "")[0], "error")
        self.assertEqual(opendm.parse_av("defender", 0x80508023, "")[0], "error")

    def test_clamav_codes(self):
        self.assertEqual(opendm.parse_av("clamav", 0, "/t/x: OK"), ("clean", ""))
        self.assertEqual(opendm.parse_av("clamav", 1, "/t/a b.exe: Win.Test.EICAR_HDB-1 FOUND\n"), ("infected", "Win.Test.EICAR_HDB-1"))
        self.assertEqual(opendm.parse_av("clamav", 2, "ERROR: Can't open file")[0], "error")


class TestScanFile(unittest.TestCase):
    def setUp(self):
        fd, self.f = tempfile.mkstemp()
        os.write(fd, b"hello")
        os.close(fd)
        self.addCleanup(os.remove, self.f)

    def run_with(self, code, out="", prefer="auto", engine="clamav", **kw):
        runner = lambda cmd, **k: subprocess.CompletedProcess(cmd, code, out, "")
        return opendm.scan_file(self.f, prefer, runner=runner, finder=lambda p: (engine, "scanner"), **kw)

    def test_clean_and_infected(self):
        r = self.run_with(0)
        self.assertEqual((r["state"], r["engine"]), ("clean", "clamav"))
        self.assertIn("no threats", opendm.av_summary(r))
        r = self.run_with(1, f"{self.f}: Eicar-Test-Signature FOUND\n")
        self.assertEqual((r["state"], r["threat"]), ("infected", "Eicar-Test-Signature"))
        self.assertTrue(opendm.av_summary(r).startswith("WARNING"))
        self.assertIn("Eicar-Test-Signature", opendm.av_summary(r))

    def test_no_engine_is_reported_not_faked_as_clean(self):
        r = opendm.scan_file(self.f, finder=lambda p: None)
        self.assertEqual(r["state"], "unavailable")
        self.assertIn("no antivirus", opendm.av_summary(r).lower())

    def test_scanner_errors_are_not_clean(self):
        self.assertEqual(self.run_with(2)["state"], "error")
        self.assertEqual(opendm.scan_file(self.f, runner=mock.Mock(side_effect=OSError("boom")), finder=lambda p: ("clamav", "x"))["state"], "error")
        t = mock.Mock(side_effect=subprocess.TimeoutExpired("x", 1))
        r = opendm.scan_file(self.f, runner=t, finder=lambda p: ("defender", "x"), timeout=120)
        self.assertEqual(r["state"], "error")
        self.assertIn("2 minutes", r["detail"])

    def test_missing_file(self):
        r = opendm.scan_file(self.f + ".gone", finder=lambda p: ("clamav", "x"), runner=mock.Mock(side_effect=AssertionError("must not run")))
        self.assertEqual(r["state"], "error")

    @unittest.skipIf(os.name == "nt", "uses a shell script as the fake scanner")
    def test_real_subprocess_with_a_fake_clamscan(self):
        script = os.path.join(tempfile.mkdtemp(), "clamscan")
        with open(script, "w") as f:
            f.write(textwrap.dedent("""\
                #!/bin/sh
                for last; do :; done
                case "$(cat "$last")" in *EICAR*) echo "$last: Eicar-Test-Signature FOUND"; exit 1;; esac
                echo "$last: OK"; exit 0
                """))
        os.chmod(script, os.stat(script).st_mode | stat.S_IEXEC)
        finder = lambda p: ("clamav", script)
        self.assertEqual(opendm.scan_file(self.f, finder=finder)["state"], "clean")
        with open(self.f, "w") as f:
            f.write("X5O EICAR test")
        r = opendm.scan_file(self.f, finder=finder)
        self.assertEqual((r["state"], r["threat"]), ("infected", "Eicar-Test-Signature"))


class TestScanInManager(Base):
    def _done(self, name="a.bin"):
        p = os.path.join(self.tmp, name)
        with open(p, "wb") as f:
            f.write(b"data")
        d = opendm.Download("http://x.test/" + name, self.tmp)
        d.status, d.path, d.name = "Completed", p, name
        return d

    def test_finished_download_is_scanned_when_the_window_turns_it_on(self):
        mgr = opendm.Manager(persist=False)
        d = self._done()
        mgr.items.append(d)
        with mock.patch.object(opendm, "scan_file", return_value={"state": "infected", "engine": "defender", "threat": "Virus:Test", "detail": ""}) as sf:
            mgr.schedule()
            self.assertEqual(sf.call_count, 0)  # scanner_on is False: tests and the CLI never scan by themselves
            mgr.scanner_on = True
            self.assertTrue(drive(mgr, lambda: d.scan == "infected"))
            mgr.schedule()
            mgr.schedule()
            self.assertEqual(sf.call_count, 1)  # once, not on every tick
        self.assertIn("Virus:Test", d.scan_info)
        self.assertEqual(opendm.status_text(d), "Complete - THREAT FOUND")

    def test_switched_off_in_settings(self):
        mgr = opendm.Manager(persist=False)
        mgr.scanner_on, mgr.settings["av_scan"] = True, False
        d = self._done()
        mgr.items.append(d)
        with mock.patch.object(opendm, "scan_file") as sf:
            mgr.schedule()
            time.sleep(0.1)
            self.assertEqual(sf.call_count, 0)

    def test_files_from_an_earlier_session_are_not_rescanned_but_the_verdict_survives(self):
        d = self._done()
        d.scan, d.scan_info = "clean", "ClamAV: no threats found."
        back = opendm.Download.from_dict(json.loads(json.dumps(d.to_dict())))
        self.assertEqual((back.scan, back.scan_info), ("clean", "ClamAV: no threats found."))
        old = opendm.Download.from_dict(json.loads(json.dumps(self._done("b.bin").to_dict())))
        self.assertTrue(old._scan_skip)
        mgr = opendm.Manager(persist=False)
        mgr.scanner_on = True
        mgr.items.append(old)
        with mock.patch.object(opendm, "scan_file") as sf:
            mgr.schedule()
            time.sleep(0.1)
            self.assertEqual(sf.call_count, 0)

    def test_a_crash_in_the_scanner_never_leaves_the_flag_stuck(self):
        d = self._done()
        with mock.patch.object(opendm, "scan_file", side_effect=RuntimeError("bug")):
            d.scan_async()
            self.assertTrue(drive(opendm.Manager(persist=False), lambda: not d._scanning))
        self.assertEqual(d.scan, "error")

    def test_manual_rescan_replaces_the_verdict(self):
        d = self._done()
        d.scan = "clean"
        d.scan_async()  # already has a verdict: nothing happens
        self.assertFalse(d._scanning)
        with mock.patch.object(opendm, "scan_file", return_value={"state": "infected", "engine": "clamav", "threat": "X", "detail": ""}):
            d.scan_async(force=True)
            self.assertTrue(drive(opendm.Manager(persist=False), lambda: d.scan == "infected"))

    def test_end_to_end_download_then_scan(self):
        srv = self.file_server()
        mgr = opendm.Manager(persist=False)
        mgr.scanner_on = True
        d = mgr.add(srv.url + "/f.bin", self.tmp, 2)
        with mock.patch.object(opendm, "scan_file", return_value={"state": "clean", "engine": "clamav", "threat": "", "detail": ""}) as sf:
            self.assertTrue(drive(mgr, lambda: d.scan == "clean"))
            self.assertEqual(sf.call_args[0][0], d.path)
        self.assertEqual(opendm.status_text(d), "Complete")  # clean is the normal case: no extra wording

    def test_cli_scan_flag_sets_the_exit_code(self):
        srv = self.file_server()
        args = mock.Mock(urls=[srv.url + "/f.bin"], max_active=3, limit=0, output=self.tmp, sort=False, quality=0, checksum="", proxy="", connections=2, scan=True)
        with mock.patch.object(opendm, "scan_file", return_value={"state": "infected", "engine": "clamav", "threat": "X", "detail": ""}):
            self.assertEqual(opendm.run_cli(args), 1)
        args.scan = False
        with mock.patch.object(opendm, "scan_file") as sf:
            self.assertEqual(opendm.run_cli(args), 0)
            self.assertEqual(sf.call_count, 0)


# ------------------------------------------------------------------ smart links
class TestUnwrap(unittest.TestCase):
    def test_known_wrappers(self):
        T = "https://files.example.org/pkg/app.zip"
        q = lambda s: __import__("urllib.parse").parse.quote(s, safe="")
        for wrapped in (f"https://www.google.com/url?q={q(T)}&sa=D", f"https://l.facebook.com/l.php?u={q(T)}&h=AT0",
                        f"https://out.reddit.com/t3_x?url={q(T)}&token=1", f"https://eur01.safelinks.protection.outlook.com/?url={q(T)}&data=05",
                        f"https://www.youtube.com/redirect?q={q(T)}&event=video", "https://href.li/?" + T):
            self.assertEqual(opendm.unwrap_url(wrapped)[0], T, wrapped)

    def test_generic_redirector_paths_and_base64(self):
        T = "https://cdn.example.org/a.iso"
        self.assertEqual(opendm.unwrap_url("https://site.test/redirect?url=" + T)[0], T)
        self.assertEqual(opendm.unwrap_url("https://site.test/out/?target=" + T)[0], T)
        b64 = base64.urlsafe_b64encode(T.encode()).decode().rstrip("=")
        self.assertEqual(opendm.unwrap_url("https://site.test/go?url=" + b64)[0], T)

    def test_nested(self):
        T = "https://cdn.example.org/a.iso"
        inner = "https://site.test/redirect?url=" + T
        url, steps = opendm.unwrap_url("https://www.google.com/url?q=" + __import__("urllib.parse").parse.quote(inner, safe=""))
        self.assertEqual((url, len(steps)), (T, 2))

    def test_ordinary_links_are_left_alone(self):
        for u in ("https://example.com/download?url=https://other.test/f.zip",  # not a redirector path: that is a real page
                  "https://example.com/files/a.zip", "https://www.google.com/search?q=https://x.test/a.zip", "https://site.test/redirect?url=notaurl",
                  "https://site.test/go?url=aHR0c-garbage!!"):
            self.assertEqual(opendm.unwrap_url(u), (u, []), u)


def page(body):
    return {"url": None, "status": 200, "type": "text/html; charset=utf-8", "disp": "", "size": None, "body": body}


def fake_web(pages):
    """A probe() over a dict: url -> response dict (url defaults to the key) or a string of HTML."""
    calls = []

    def probe(url):
        calls.append(url)
        r = pages[url]
        r = page(r) if isinstance(r, str) else dict(r)
        r["url"] = r.get("url") or url
        return r
    probe.calls = calls
    return probe


FILE = {"status": 200, "type": "application/zip", "disp": "", "size": "10", "body": ""}


class TestResolve(unittest.TestCase):
    def test_direct_file(self):
        r = opendm.resolve_link("https://a.test/f.zip", fake_web({"https://a.test/f.zip": FILE}))
        self.assertEqual((r["state"], r["url"]), ("direct", "https://a.test/f.zip"))

    def test_shortener_redirect_to_a_file(self):
        r = opendm.resolve_link("https://sho.rt/abc", fake_web({"https://sho.rt/abc": {**FILE, "url": "https://cdn.test/real.zip"}}))
        self.assertEqual((r["state"], r["url"]), ("resolved", "https://cdn.test/real.zip"))

    def test_download_attachment_without_a_file_extension(self):
        r = opendm.resolve_link("https://a.test/get?id=4", fake_web({"https://a.test/get?id=4": {"status": 200, "type": "text/html", "disp": 'attachment; filename="x.bin"', "body": ""}}))
        self.assertEqual(r["state"], "direct")

    def test_landing_page_picks_the_download_button_not_the_ads(self):
        html = """<a href="/about">About</a> <a href="https://ads.test/win" class="sponsored" rel="sponsored">Download NOW - win a prize</a>
                  <a href="/files/setup-1.2.exe" class="btn-download">Download for Windows</a> <img src="/logo.png"><a href="/style.css">css</a>"""
        web = fake_web({"https://a.test/get": html, "https://a.test/files/setup-1.2.exe": FILE})
        r = opendm.resolve_link("https://a.test/get", web)
        self.assertEqual((r["state"], r["url"]), ("resolved", "https://a.test/files/setup-1.2.exe"))
        self.assertNotIn("https://ads.test/win", web.calls)  # the ad was never even visited

    def test_two_equally_good_links_are_offered_to_the_user(self):
        html = '<a href="/a.zip">Download A</a> <a href="/b.zip">Download B</a>'
        r = opendm.resolve_link("https://a.test/p", fake_web({"https://a.test/p": html}))
        self.assertEqual(r["state"], "choose")
        self.assertEqual({c["url"] for c in r["candidates"]}, {"https://a.test/a.zip", "https://a.test/b.zip"})

    def test_meta_refresh_and_javascript_redirects(self):
        web = fake_web({"https://a.test/w": '<meta http-equiv="refresh" content="3; url=/dl/x.zip">Your download starts in 3 seconds', "https://a.test/dl/x.zip": FILE,
                        "https://a.test/j": '<script>window.location.href = "https://a.test/dl/x.zip";</script>'})
        self.assertEqual(opendm.resolve_link("https://a.test/w", web)["url"], "https://a.test/dl/x.zip")
        self.assertEqual(opendm.resolve_link("https://a.test/j", web)["url"], "https://a.test/dl/x.zip")

    def test_wrapper_then_landing_page_then_file(self):
        web = fake_web({"https://a.test/page": '<a href="/f.pdf" download>Get it</a>', "https://a.test/f.pdf": FILE})
        r = opendm.resolve_link("https://www.google.com/url?q=https%3A%2F%2Fa.test%2Fpage&sa=D", web)
        self.assertEqual((r["state"], r["url"]), ("resolved", "https://a.test/f.pdf"))
        self.assertTrue(len(r["steps"]) >= 2)

    def test_login_and_payment_walls_are_reported_never_bypassed(self):
        for code in (401, 402, 403):
            web = fake_web({"https://a.test/x": {"status": code, "type": "text/html", "disp": "", "body": "<a href='/f.zip'>Download</a>"}})
            r = opendm.resolve_link("https://a.test/x", web)
            self.assertEqual(r["state"], "blocked", code)
            self.assertEqual(r["url"], "https://a.test/x")  # the address is left as it was
            self.assertEqual(web.calls, ["https://a.test/x"])  # and nothing else was tried
        r = opendm.resolve_link("https://a.test/n", fake_web({"https://a.test/n": "<h1>Subscribe to continue reading</h1><a href='/pricing'>Plans</a>"}))
        self.assertEqual(r["state"], "blocked")
        self.assertIn("doesn't get around", r["note"])

    def test_nothing_found_and_errors(self):
        self.assertEqual(opendm.resolve_link("https://a.test/e", fake_web({"https://a.test/e": "<p>hello</p><a href='/about'>About us</a>"}))["state"], "none")
        self.assertEqual(opendm.resolve_link("https://a.test/e", fake_web({"https://a.test/e": {"status": 404, "type": "text/html", "disp": "", "body": ""}}))["state"], "failed")
        boom = mock.Mock(side_effect=OSError("timed out"))
        r = opendm.resolve_link("https://a.test/e", boom)
        self.assertEqual(r["state"], "failed")
        self.assertIn("timed out", r["note"])

    def test_loops_terminate(self):
        web = fake_web({"https://a.test/1": '<meta http-equiv="refresh" content="0;url=/2">', "https://a.test/2": '<meta http-equiv="refresh" content="0;url=/1">'})
        r = opendm.resolve_link("https://a.test/1", web)
        self.assertLessEqual(len(web.calls), 6)
        self.assertIn(r["state"], ("resolved", "failed", "none"))  # it gives up instead of spinning

    def test_other_schemes_are_skipped(self):
        for u in ("ftp://a.test/f", "file:///etc/passwd", "javascript:alert(1)", ""):
            self.assertEqual(opendm.resolve_link(u, mock.Mock(side_effect=AssertionError("no network")))["state"], "skip")

    def test_google_drive_share_links_are_normalised_first(self):
        web = fake_web({"https://drive.google.com/uc?export=download&id=ABC123": FILE})
        r = opendm.resolve_link("https://drive.google.com/file/d/ABC123/view", web)
        self.assertEqual(r["url"], "https://drive.google.com/uc?export=download&id=ABC123")

    def test_score_link_ordering(self):
        page_url = "https://a.test/p"
        s = lambda **kw: opendm.score_link({"url": "https://a.test/x", "text": "", "download": False, "rel": "", "cls": "", **kw}, page_url)
        self.assertGreater(s(download=True), s())
        self.assertGreater(s(url="https://a.test/a.zip"), s(url="https://a.test/a.png"))
        self.assertGreater(s(text="Download"), s(text="Home"))
        self.assertLess(s(text="Download", rel="sponsored"), 40)


class TestResolveOverHttp(Base):
    """default_probe() through the real connection layer, against local servers."""

    def test_redirect_chain_to_a_file_and_a_landing_page(self):
        def app(h):
            if h.path == "/s/abc":
                send(h, 302, b"", {"Location": "/files/pack.zip"})
            elif h.path == "/files/pack.zip":
                send(h, 200, b"PK\x03\x04" + b"0" * 100, {"Content-Type": "application/zip"})
            elif h.path == "/landing":
                send(h, 200, b'<a href="/files/pack.zip" class="download">Download</a><a href="/promo" rel="sponsored">Ad</a>', {"Content-Type": "text/html"})
            elif h.path == "/members":
                send(h, 403, b"<html>members only</html>", {"Content-Type": "text/html"})
            else:
                send(h, 404)
        srv = self.http(app)
        r = opendm.resolve_link(srv.url + "/s/abc")
        self.assertEqual((r["state"], r["url"]), ("resolved", srv.url + "/files/pack.zip"))
        r = opendm.resolve_link(srv.url + "/landing")
        self.assertEqual((r["state"], r["url"]), ("resolved", srv.url + "/files/pack.zip"))
        self.assertEqual(opendm.resolve_link(srv.url + "/members")["state"], "blocked")
        self.assertEqual(opendm.resolve_link(srv.url + "/nope")["state"], "failed")

    def test_the_file_itself_is_not_downloaded_while_resolving(self):
        sent, chunk, total = [], b"0" * 65536, 1024  # a 64 MB file: far more than the socket buffers can swallow

        def app(h):
            h.send_response(200)
            h.send_header("Content-Type", "application/octet-stream")
            h.send_header("Content-Length", str(len(chunk) * total))
            h.end_headers()
            try:
                for _ in range(total):
                    h.wfile.write(chunk)
                    sent.append(1)
            except OSError:
                pass
        srv = self.http(app)
        self.assertEqual(opendm.resolve_link(srv.url + "/big")["state"], "direct")
        time.sleep(0.3)
        self.assertLess(len(sent), total // 2)  # the connection was closed early, the file was not pulled


# ------------------------------------------------------------------ clipboard history
class TestClipboard(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "sub", "clipboard.json")

    def test_clip_urls(self):
        self.assertEqual(opendm.clip_urls("see https://a.test/f.zip, and (http://b.test/x?y=1). Also ftp://c.test/z; mailto:me@x.test"),
                         ["https://a.test/f.zip", "http://b.test/x?y=1", "ftp://c.test/z"])
        self.assertEqual(opendm.clip_urls("no links, just a password: hunter2"), [])
        self.assertEqual(opendm.clip_urls("https://a.test/1 https://a.test/1"), ["https://a.test/1"])

    def test_order_dedupe_and_new(self):
        h = opendm.ClipHistory(self.path)
        self.assertEqual(h.add_text("https://a.test/1 https://a.test/2", now=1), ["https://a.test/1", "https://a.test/2"])
        self.assertEqual([x["url"] for x in h.items], ["https://a.test/1", "https://a.test/2"])  # same order as copied
        self.assertEqual(h.add_text("https://a.test/3", now=2), ["https://a.test/3"])
        self.assertEqual(h.add_text("https://a.test/1", now=3), [])  # copied again: not new, but moves to the top
        self.assertEqual([x["url"] for x in h.items][0], "https://a.test/1")
        self.assertEqual(len(h.items), 3)

    def test_only_links_are_stored_and_it_survives_a_restart(self):
        h = opendm.ClipHistory(self.path)
        h.add_text("my secret password is hunter2 https://a.test/f.zip")
        with open(self.path) as f:
            raw = f.read()
        self.assertNotIn("hunter2", raw)
        self.assertEqual([x["url"] for x in opendm.ClipHistory(self.path).items], ["https://a.test/f.zip"])

    def test_limit_remove_clear(self):
        h = opendm.ClipHistory(self.path, limit=3)
        for i in range(6):
            h.add_text(f"https://a.test/{i}")
        self.assertEqual([x["url"] for x in h.items], [f"https://a.test/{i}" for i in (5, 4, 3)])
        h.remove(["https://a.test/4"])
        self.assertEqual(len(h.items), 2)
        h.clear()
        self.assertEqual(opendm.ClipHistory(self.path).items, [])

    def test_damaged_file_is_ignored(self):
        os.makedirs(os.path.dirname(self.path))
        for junk in ("{not json", '{"a": 1}', '[1, "x", {"url": "file:///etc/passwd"}, {"url": "https://ok.test/a"}]'):
            with open(self.path, "w") as f:
                f.write(junk)
            self.assertEqual([x["url"] for x in opendm.ClipHistory(self.path).items], ["https://ok.test/a"] if "ok.test" in junk else [])


# ------------------------------------------------------------------ skins, toolbar
class TestSkins(unittest.TestCase):
    def test_default_is_unchanged(self):
        self.assertEqual(opendm.make_palette("dark", "#ea580c"), opendm.make_palette("dark", "#ea580c", "default"))
        self.assertEqual(opendm.make_palette("light")["mode"], "light")
        self.assertEqual(opendm.make_palette("light", skin="no-such-skin"), opendm.make_palette("light"))

    def test_every_skin_is_complete_and_readable(self):
        keys = set(opendm.make_palette("light"))
        for name in opendm.SKINS:
            p = opendm.make_palette("light", skin=name)
            self.assertEqual(set(p), keys, name)
            self.assertEqual(p["mode"], opendm.SKINS[name][0], name)  # the skin decides light / dark, whatever the theme setting says
            lum = sorted((opendm.luminance(p["bg"]) + .05, opendm.luminance(p["fg"]) + .05))
            self.assertGreaterEqual(lum[1] / lum[0], 4.5, f"{name}: text on background")  # WCAG AA
            lum = sorted((opendm.luminance(p["accent"]) + .05, opendm.luminance(p["accent_fg"]) + .05))
            self.assertGreaterEqual(lum[1] / lum[0], 4.5, f"{name}: text on accent")
            for k in ("bg", "panel", "field", "fg", "border", "button", "graph_bg"):
                self.assertTrue(opendm.valid_hex(p[k]) or p[k] == "white", f"{name}.{k}")

    def test_accent_choice(self):
        self.assertEqual(opendm.make_palette("light", skin="nord")["accent"], opendm.SKINS["nord"][2])  # the skin's own accent ...
        self.assertEqual(opendm.make_palette("light", "#ea580c", "nord")["accent"], "#ea580c")  # ... unless the user picked one
        self.assertEqual(opendm.make_palette("dark", "garbage", "forest")["accent"], opendm.SKINS["forest"][2])

    def test_names(self):
        self.assertEqual(opendm.skin_names()[0], "default")
        self.assertEqual(len(set(opendm.skin_names())), len(opendm.skin_names()))
        self.assertGreaterEqual(len(opendm.SKINS), 5)


class TestToolbarLayout(unittest.TestCase):
    known = opendm.TOOLBAR_ACTIONS

    def test_default_covers_the_classic_toolbar(self):
        self.assertEqual([x for x in opendm.DEFAULT_TOOLBAR if x != "|"], [e[0] for e in opendm.TOOLBAR if e])
        self.assertEqual(opendm.toolbar_layout(None, opendm.DEFAULT_TOOLBAR, self.known), opendm.DEFAULT_TOOLBAR)

    def test_every_button_has_an_icon_and_a_method(self):
        for bid, (icon, label, meth) in self.known.items():
            self.assertEqual(bid, icon)
            self.assertTrue(label)
            self.assertTrue(hasattr(opendm.App, meth), meth)
            self.assertTrue(icon in opendm.UI_ICONS or icon in opendm.GLYPHS, icon)

    def test_sanitising(self):
        L = lambda x: opendm.toolbar_layout(x, ["add"], self.known)
        self.assertEqual(L(["|", "add", "|", "|", "stop", "bogus", "add", "|"]), ["add", "|", "stop"])
        self.assertEqual(L(["bogus"]), ["add"])
        self.assertEqual(L([]), ["add"])
        self.assertEqual(L("not a list"), ["add"])
        self.assertEqual(L(["scan", "clip", "|", "widget"]), ["scan", "clip", "|", "widget"])

    def test_glyphs_stay_inside_the_32px_icon(self):
        for name, rects in opendm.GLYPHS.items():
            self.assertTrue(rects, name)
            for x0, y0, x1, y1, c in rects:
                self.assertTrue(0 <= x0 <= x1 <= 31 and 0 <= y0 <= y1 <= 31, (name, x0, y0, x1, y1))
                self.assertRegex(c, r"^#[0-9a-f]{6}$")


if __name__ == "__main__":
    unittest.main()
