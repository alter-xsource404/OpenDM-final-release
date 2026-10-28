#!/usr/bin/env python3
"""End-to-end smoke test of the real main window (needs a display, e.g.  xvfb-run -a python tests/gui_smoke.py).
Drives the actual GUI: menus, toolbar, navigation tree, list columns, sorting, queues, site grabber, dialogs, tray.
Set OPENDM_SHOT=/path/shot.png to also save a screenshot. Exits non-zero if any check fails."""
import os, sys, tempfile
HOME = tempfile.mkdtemp()  # isolated settings + downloads; must be set before opendm is imported
os.environ["HOME"] = os.environ["USERPROFILE"] = HOME
if not os.environ.get("DISPLAY") and sys.platform.startswith("linux"):
    print("SKIP: no display (run with xvfb-run)"); sys.exit(0)
try:
    import tkinter
except ImportError:
    print("SKIP: tkinter is not installed"); sys.exit(0)
import json, time, queue, threading, http.server, re, urllib.request, tkinter as tk, tkinter.messagebox as mb, tkinter.simpledialog as sd
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import opendm, test_opendm as T
home = HOME
for d in (".config/google-chrome", ".mozilla"):  # pretend Chrome and Firefox are installed (Linux registers by file)
    os.makedirs(os.path.join(HOME, d))
FILES = {n: os.urandom(8000) for n in ("clip.mp4", "report.pdf", "data.zip", "song.mp3", "setup.exe", "notes.xyz", "a.jpg", "b.png")}
SITE = b'<title>Holiday Photos</title><a href="a.jpg">1</a><img src="b.png"><a href="report.pdf">r</a><a href="x.css">c</a>'
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        p = self.path.split("?")[0]
        if p == "/site/index.html": body, ct = SITE, "text/html"
        elif p.startswith("/site/") and p[6:] in FILES: body, ct = FILES[p[6:]], "application/octet-stream"
        elif p.lstrip("/") in FILES: body, ct = FILES[p.lstrip("/")], "application/octet-stream"
        elif p == "/slow.bin":
            N = 6 * 1024 * 1024; rng = self.headers.get("Range"); a, b = 0, N - 1
            if rng: a, b = re.match(r"bytes=(\d+)-(\d*)", rng).groups(); a = int(a); b = int(b) if b else N - 1
            self.send_response(206 if rng else 200)
            if rng: self.send_header("Content-Range", f"bytes {a}-{b}/{N}")
            self.send_header("Content-Length", str(b - a + 1)); self.end_headers()
            try:
                for q in range(a, b + 1, 32768): self.wfile.write(b"\0" * min(32768, b + 1 - q)); time.sleep(0.03)
            except OSError: pass
            return
        else: self.send_response(404); self.send_header("Content-Length", "0"); self.end_headers(); return
        self.send_response(200); self.send_header("Content-Type", ct); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def log_message(self, *a): pass
threading.Thread(target=http.server.ThreadingHTTPServer(("127.0.0.1", 18789), H).serve_forever, daemon=True).start()
sys.modules.update(T._fake_pystray())
dialogs, asks = [], []
for n in ("showinfo", "showerror"): setattr(mb, n, lambda *a, _n=n, **k: dialogs.append((_n, str(a[1]) if len(a) > 1 else "")))
mb.askyesno = lambda *a, **k: (dialogs.append(("askyesno", str(a[1]))), True)[1]
sd.askstring = lambda *a, **k: asks.pop(0) if asks else None
fails = []
def check(ok, msg):
    print(("PASS " if ok else "FAIL ") + msg); (fails.append(msg) if not ok else None)
app = opendm.App(16867)
app.mgr.settings.update(confirm_captured=False, show_complete_dialog=False)  # these checks drive the list directly; the confirm/complete windows are covered in test_opendm.py
def driver():
    root = app.root
    def ui(fn):
        q = queue.Queue()
        def run():
            try: q.put(("ok", fn()))
            except Exception as e: q.put(("err", repr(e)))
        root.after(0, run); st, v = q.get(timeout=20)
        if st == "err": raise RuntimeError(v)
        return v
    def walk(w):
        yield w
        for c in w.winfo_children(): yield from walk(c)
    def menu_of(label): 
        def f():
            bar = app.menubar
            for i in range(bar.index("end") + 1):
                if bar.entrycget(i, "label") == label: return bar.nametowidget(bar.entrycget(i, "menu"))
        return ui(f)
    def labels(m): return ui(lambda: [m.entrycget(i, "label") for i in range(m.index("end") + 1) if m.type(i) not in ("separator", "tearoff")])
    def invoke(m, label):
        def f():
            for i in range(m.index("end") + 1):
                if m.type(i) != "separator" and m.entrycget(i, "label") == label: m.invoke(i); return True
            return False
        return ui(f)
    rows = lambda: ui(lambda: [app.tree.item(i, "values") for i in app.tree.get_children()])
    tok = opendm.get_token()
    def api(url, **kw): urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:16867/add", data=json.dumps({"url": url, **kw}).encode(), headers={"X-OpenDM-Token": tok, "Content-Type": "application/json"}), timeout=5)
    time.sleep(2)
    # ---- 1. menu bar
    top = ui(lambda: [app.menubar.entrycget(i, "label") for i in range(app.menubar.index("end") + 1)])
    check(top == ["Tasks", "File", "Downloads", "View", "Help", "Registration"], f"menu bar: {top}")
    for name in top: print("      ", name.ljust(13), labels(menu_of(name)))
    # ---- 2. toolbar
    tb = ui(lambda: [(b.cget("text"), bool(str(b.cget("image")))) for b in app.tbtn.values()])
    check([t for t, _ in tb] == ["Add URL", "Resume", "Stop", "Stop All", "Delete", "Delete C.", "Options", "Scheduler", "Start Queue", "Stop Queue", "Grabber", "Browser"] and all(i for _, i in tb),
          f"toolbar: {len(tb)} icon+label buttons: {[t for t, _ in tb]}")
    check(ui(lambda: str(app.tbtn["add"].cget("compound"))) == "top", "toolbar buttons show the icon above the label (like IDM)")
    # ---- 3. navigation tree
    def tree_text(iid=""): return ui(lambda: [(app.side.item(c, "text").strip(), tree_text_children(c)) for c in app.side.get_children(iid)])
    def tree_text_children(c): return [app.side.item(k, "text").strip() for k in app.side.get_children(c)]
    nav = ui(lambda: [(app.side.item(c, "text").strip(), [app.side.item(k, "text").strip() for k in app.side.get_children(c)]) for c in app.side.get_children("")])
    print("      nav:", nav)
    top_names = [re.sub(r" \(\d+\)$", "", t) for t, _ in nav]
    check(top_names == ["All Downloads", "Unfinished", "Finished", "Grabber projects", "Queues"], f"navigation tree top level: {top_names}")
    cats = [re.sub(r" \(\d+\)$", "", t) for t in nav[0][1]]
    check(cats == ["General", "Compressed", "Documents", "Music", "Video", "Images", "Programs"], f"categories sit under All Downloads: {cats}")
    check([re.sub(r" \(\d+\)$", "", t) for t in nav[4][1]] == ["Main download queue"], "Queues contains the Main download queue")
    # ---- 4. list columns
    heads = ui(lambda: [app.tree.heading(c, "text") for c in app.tree["columns"]])
    check(heads == ["File Name", "Q", "Size", "Status", "Time left", "Transfer rate", "Last Try", "Description"], f"list columns: {heads}")
    # ---- 5. real downloads
    for n in ("clip.mp4", "report.pdf", "data.zip", "song.mp3", "setup.exe", "notes.xyz"): api(f"http://127.0.0.1:18789/{n}")
    t = time.time()
    while time.time() - t < 30 and not (len(rows()) == 6 and all(r[3] == "Complete" for r in rows())): time.sleep(0.3)
    r = rows(); print("      sample row:", r[0])
    check(len(r) == 6 and all(x[3] == "Complete" for x in r), "six downloads finished; Status column reads 'Complete'")
    check(all(re.match(r"^[A-Z][a-z]{2} \d{2} \d{2}:\d{2}:\d{2} \d{4}$", x[6]) for x in r), "Last Try column shows 'Oct 20 14:03:11 2026' style dates")
    check({x[7] for x in r} == {"127.0.0.1:18789"}, "Description defaults to the source site")
    check(all(x[1] == "" for x in r), "finished downloads have no queue number in Q")
    # later + queue numbers
    ui(lambda: app.mgr.add("http://127.0.0.1:18789/a.jpg", app.folder.get(), 1, later=True)); ui(lambda: app.mgr.add("http://127.0.0.1:18789/b.png", app.folder.get(), 1, later=True)); ui(app.after_change)
    q = [x for x in rows() if x[3] == "Stopped"]
    check([(x[0], x[1]) for x in q] == [("a.jpg", "1"), ("b.png", "2")], f"'Download later' items show the guessed file name and wait in the queue as Q = 1, 2: {[(x[0], x[1], x[3]) for x in q]}")
    # ---- 6. a running download: percent, time left, transfer rate
    ui(lambda: app.limit_var.set(400)); api("http://127.0.0.1:18789/slow.bin"); time.sleep(3.5)  # 400 KB/s so it is still running
    live = [x for x in rows() if x[0].startswith("slow")] or [x for x in rows() if "slow" in x[0]]
    print("      live row:", live[0] if live else None)
    check(bool(live) and re.match(r"^\d+\.\d{2}%$", live[0][3]) and re.search(r"(sec|min)", live[0][4]) and re.search(r"(Bytes|KBytes|MBytes)/sec", live[0][5]), "running download: 'xx.xx%', 'Time left' like '9 sec', 'Transfer rate' like '1.0 MBytes/sec'")
    ui(lambda: app.tree.selection_set(app.tree.get_children()[-1])) ; time.sleep(0.4)
    ui(app.stop_all); time.sleep(1.5); ui(lambda: app.limit_var.set(0))
    st = [x for x in rows() if "slow" in x[0]][0][3]; check(st.startswith("Stopped"), f"Stop All -> status '{st}'")
    # ---- 7. sorting
    ui(lambda: app.sort_by("size")); h = ui(lambda: app.tree.heading("size", "text"))
    sizes = [x[0] for x in rows()]
    check("\u25b2" in h, f"clicking a column title sorts and marks it: {h!r}")
    ui(lambda: app.sort_by("name")); names = [x[0].lower() for x in rows()]; check(names == sorted(names), "sort by File Name is alphabetical")
    ui(lambda: app.sort_by("name")); names = [x[0].lower() for x in rows()]; check(names == sorted(names, reverse=True), "clicking again reverses it")
    ui(lambda: app.sort_by("", toggle=False))
    # ---- 8. navigation filters
    def pick(iid): ui(lambda: app.side.selection_set(iid)); time.sleep(0.8)
    pick("finished"); check(len(rows()) == 6, "Finished -> 6 rows")
    pick("unfinished"); check(len(rows()) == 3, f"Unfinished -> the 2 waiting + the stopped slow one ({len(rows())} rows)")
    cat_iid = ui(lambda: next(i for i, (l, f) in app.side_map.items() if f == "cat:Video")); pick(cat_iid); check([x[0] for x in rows()] == ["clip.mp4"], "category 'Video' -> clip.mp4")
    # ---- 9. queues
    asks.append("Night"); invoke(menu_of("Downloads"), "New queue..."); time.sleep(0.5)
    check("Night" in app.mgr.settings["queues"], "Downloads > New queue... creates a queue")
    pick("all"); ui(lambda: app.tree.selection_set([i for i in app.tree.get_children() if "a.jpg" in app.tree.item(i, "values")[0]]))
    ui(lambda: app.move_selected_queue("Night")); time.sleep(0.8)
    qiid = ui(lambda: next(i for i, (l, f) in app.side_map.items() if f == "queue:Night")); pick(qiid)
    check([x[0] for x in rows()] == ["a.jpg"] and rows()[0][1] == "1", "Move to queue 'Night' -> shows under Queues > Night with Q=1")
    ui(app.start_queue); time.sleep(2.5); pick("all")
    done = [x for x in rows() if x[0] == "a.jpg"]; check(bool(done) and done[0][3] == "Complete", "Start Queue starts that queue's stopped downloads")
    # ---- 10. site grabber
    invoke(menu_of("Tasks"), "Run site grabber..."); time.sleep(0.8)
    win = ui(lambda: [w for w in root.winfo_children() if w.winfo_class() == "Toplevel"][-1])
    ents = ui(lambda: [w for w in walk(win) if w.winfo_class() == "TEntry"])
    ui(lambda: (ents[0].delete(0, "end"), ents[0].insert(0, "http://127.0.0.1:18789/site/index.html")))
    ui(lambda: [w for w in walk(win) if w.winfo_class() == "TButton" and w.cget("text") == "Explore"][0].invoke()); time.sleep(2.5)
    res = ui(lambda: [w for w in walk(win) if w.winfo_class() == "Treeview"][0]); found = ui(lambda: [res.item(i, "values")[0] for i in res.get_children()])
    check(sorted(found) == ["a.jpg", "b.png", "report.pdf"], f"grabber found the files on the page: {found}")
    ui(lambda: [w for w in walk(win) if w.winfo_class() == "TButton" and w.cget("text") == "Start Download"][0].invoke()); time.sleep(3)
    ui(lambda: win.destroy())
    proj = ui(lambda: [app.side.item(i, "text").strip() for i in app.side.get_children("projects")])
    check(proj == ["Holiday Photos (3)"], f"'Grabber projects' now lists the project: {proj}")
    pidd = ui(lambda: next(i for i, (l, f) in app.side_map.items() if f == "project:Holiday Photos")); pick(pidd)
    check(sorted(x[0] for x in rows()) == ["a.jpg", "b.png", "report.pdf"] and all(x[3] == "Complete" for x in rows()), "selecting the project lists exactly its downloads, all complete")
    pick("all")
    # ---- 11. file/downloads menu states + context menu
    ui(lambda: app.tree.selection_remove(app.tree.selection()))
    fm = menu_of("File"); en = lambda m, l: ui(lambda: [m.entrycget(i, "state") for i in range(m.index("end") + 1) if m.type(i) != "separator" and m.entrycget(i, "label") == l][0])
    ui(app.update_state); check(en(fm, "Open") == "disabled" and en(fm, "Properties...") == "disabled", "File menu items are greyed out with nothing selected")
    ui(lambda: app.tree.selection_set([i for i in app.tree.get_children() if app.tree.item(i, "values")[0] == "clip.mp4"])); time.sleep(0.4); ui(app.update_state)
    check(en(fm, "Open") == "normal" and en(fm, "Properties...") == "normal" and en(fm, "Move/Rename...") == "normal", "...and enabled once a finished file is selected")
    check(ui(lambda: str(app.tbtn["resume"].instate(["disabled"]))) == "True" and ui(lambda: str(app.tbtn["delete"].instate(["disabled"]))) == "False", "toolbar: Resume greyed (nothing to resume), Delete enabled")
    ctx = ui(lambda: [app.ctx.entrycget(i, "label") for i in range(app.ctx.index("end") + 1) if app.ctx.type(i) != "separator"])
    check(ctx == ["Open", "Open folder", "Resume", "Stop", "Delete", "Move to category", "Move to queue", "Limit speed...", "Redownload", "Hashes...", "Properties...", "Copy address"], f"right-click menu: {ctx}")
    # rename
    asks.append("movie.mp4"); ui(app.rename_file); time.sleep(0.5)
    check(any(x[0] == "movie.mp4" for x in rows()) and os.path.exists(os.path.join(home, "Downloads", "Video", "movie.mp4")), "File > Move/Rename renames the file on disk")
    # properties
    ui(lambda: app.tree.selection_set([i for i in app.tree.get_children() if app.tree.item(i, "values")[0] == "movie.mp4"])); ui(app.properties_dialog); time.sleep(0.5)
    pw = ui(lambda: [w for w in root.winfo_children() if w.winfo_class() == "Toplevel"][-1])
    ents = ui(lambda: [w for w in walk(pw) if w.winfo_class() == "TEntry"]); ui(lambda: (ents[-1].delete(0, "end"), ents[-1].insert(0, "my holiday video")))
    ui(lambda: [w for w in walk(pw) if w.winfo_class() == "TButton" and w.cget("text") == "OK"][0].invoke()); time.sleep(0.8)
    check([x[7] for x in rows() if x[0] == "movie.mp4"] == ["my holiday video"], "Properties lets you edit the Description column")
    # ---- 12. delete (list + disk)
    app.confirm_delete = lambda sel: (True, True)
    ui(app.delete); time.sleep(0.6)
    check(not any(x[0] == "movie.mp4" for x in rows()) and not os.path.exists(os.path.join(home, "Downloads", "Video", "movie.mp4")), "Delete removes the entry and (when ticked) the file from disk")
    n_done = len([x for x in rows() if x[3] == "Complete"]); ui(app.delete_completed); time.sleep(0.6)
    check(not [x for x in rows() if x[3] == "Complete"] and n_done > 0, f"Delete C. cleared {n_done} completed entries from the list")
    # ---- 13. options
    invoke(menu_of("Downloads"), "Options..."); time.sleep(0.6)
    ow = ui(lambda: [w for w in root.winfo_children() if w.winfo_class() == "Toplevel"][-1]); nb = ui(lambda: [w for w in walk(ow) if w.winfo_class() == "TNotebook"][0])
    tabs = ui(lambda: [nb.tab(i, "text") for i in range(nb.index("end"))]); check(tabs == ["General", "Save to", "Connection", "Browser", "Proxy", "Logins", "Appearance", "Sounds", "Extras"], f"Options has tabs: {tabs}")
    spin = ui(lambda: [w for w in walk(ow) if w.winfo_class() == "TSpinbox"]); ui(lambda: (spin[1].delete(0, "end"), spin[1].insert(0, "5")))
    ui(lambda: [w for w in walk(ow) if w.winfo_class() == "TButton" and w.cget("text") == "OK"][0].invoke()); time.sleep(0.5)
    check(app.mgr.max_active == 5 and json.load(open(os.path.join(home, ".opendm", "settings.json")))["max_active"] == 5, "Options > Connection: 'Maximum simultaneous downloads' applied and saved")
    # ---- 14. view menu
    vm = menu_of("View"); panes = lambda: ui(lambda: len(app.body.panes()))
    invoke(vm, "Categories pane"); time.sleep(0.4); check(panes() == 1, "View > Categories pane hides the navigation tree")
    invoke(vm, "Categories pane"); time.sleep(0.4); check(panes() == 2, "...and shows it again")
    invoke(vm, "Toolbar"); time.sleep(0.3); check(ui(lambda: app.toolbar.winfo_manager()) == "", "View > Toolbar hides the toolbar"); invoke(vm, "Toolbar")
    # ---- 15. registration
    n0 = len(dialogs); invoke(menu_of("Registration"), "Registration status..."); time.sleep(0.4)
    check("free" in dialogs[-1][1].lower() and "serial" in dialogs[-1][1].lower(), f"Registration menu is honest: {dialogs[-1][1][:70]!r}...")
    invoke(menu_of("Registration"), "License (MIT)..."); time.sleep(0.5)
    lw = ui(lambda: [w for w in root.winfo_children() if w.winfo_class() == "Toplevel"][-1]); txt = ui(lambda: [w for w in walk(lw) if w.winfo_class() == "Text"][0].get("1.0", "end"))
    check("MIT License" in txt, "License window shows the MIT text"); ui(lambda: lw.destroy())
    # ---- 16. system tray (fake pystray: there is no desktop tray under Xvfb)
    tray = app.tray
    check(tray is not None and tray.available and tray.icon.running, "tray icon started with the window")
    ui(app.request_close); time.sleep(0.4)
    check(ui(root.state) == "withdrawn" and tray.icon.notes and "still running" in tray.icon.notes[-1][1], "the window's X button hides OpenDM to the tray and says so")
    tray.cmds.put("show"); time.sleep(0.6); check(ui(root.state) == "normal", "tray > Show OpenDM brings the window back")
    tray.cmds.put("limit:512"); time.sleep(0.6); check(opendm.GLOBAL_LIMIT.rate == 512 * 1024, "tray > Speed limit > 512 KB/s sets the limit")
    tray.cmds.put("limit:0"); time.sleep(0.5)
    check("OpenDM -" in tray.icon.title, f"tray tooltip: {tray.icon.title!r}")
    ui(root.withdraw); n0 = len(tray.icon.notes); api("http://127.0.0.1:18789/report.pdf"); time.sleep(3)
    check(any("Finished: report" in m for _, m in tray.icon.notes[n0:]), "hidden window -> 'Finished: report.pdf' balloon notification")
    ui(root.deiconify); time.sleep(0.4)
    invoke(menu_of("Downloads"), "Options..."); time.sleep(0.6)
    ow = ui(lambda: [w for w in root.winfo_children() if w.winfo_class() == "Toplevel"][-1])
    ui(lambda: [w for w in walk(ow) if w.winfo_class() == "TCheckbutton"][0].invoke())
    ui(lambda: [w for w in walk(ow) if w.winfo_class() == "TButton" and w.cget("text") == "OK"][0].invoke()); time.sleep(0.6)
    check(app.tray is None and not tray.icon.running and json.load(open(os.path.join(home, ".opendm", "settings.json")))["tray"] is False, "Options: untick the tray icon -> it stops and the choice is saved")
    # ---- 17. browser integration (native messaging registration)
    cm = os.path.join(home, ".config", "google-chrome", "NativeMessagingHosts", "org.opendm.nativehost.json")
    fm = os.path.join(home, ".mozilla", "native-messaging-hosts", "org.opendm.nativehost.json")
    check(os.path.exists(cm) and os.path.exists(fm), "OpenDM registered itself with the installed browsers at startup (no click needed)")
    m = json.load(open(cm)); check(m["allowed_origins"] == [f"chrome-extension://{opendm.DEFAULT_EXTENSION_IDS[0]}/"] and os.access(m["path"], os.X_OK), "the Chrome manifest trusts only OpenDM's extension and points at a runnable launcher")
    ui(lambda: app.tbtn["browser"].invoke()); time.sleep(0.8)
    bw = ui(lambda: [w for w in root.winfo_children() if w.winfo_class() == "Toplevel"][-1]); tvw = ui(lambda: [w for w in walk(bw) if w.winfo_class() == "Treeview"][0])
    rowsb = ui(lambda: {tvw.item(i, "values")[0]: tvw.item(i, "values")[1] for i in tvw.get_children()})
    print("      browsers:", rowsb)
    check(rowsb["Google Chrome"].startswith("Registered") and rowsb["Mozilla Firefox"].startswith("Registered") and rowsb["Microsoft Edge"] == "Browser not found", "Browser dialog shows each browser's real status")
    def bbtn(text): return [w for w in walk(bw) if w.winfo_class() == "TButton" and w.cget("text") == text][0]
    ui(lambda: bbtn("Remove registration").invoke()); time.sleep(0.4)
    check(not os.path.exists(cm) and ui(lambda: tvw.item(tvw.get_children()[0], "values")[1]) == "Not registered", "Remove registration deletes it and the status updates")
    ui(lambda: bbtn("Register / Repair").invoke()); time.sleep(0.4)
    check(os.path.exists(cm), "Register / Repair puts it back")
    ents = ui(lambda: [w for w in walk(bw) if w.winfo_class() == "TEntry" and "readonly" not in w.state()])
    nbad = len(dialogs); ui(lambda: (ents[0].delete(0, "end"), ents[0].insert(0, "not-an-id"))); ui(lambda: bbtn("Save").invoke()); time.sleep(0.3)
    check(dialogs[-1][0] == "showerror" and "not-an-id" in dialogs[-1][1], "an invalid extension ID is rejected with an explanation")
    ui(lambda: (ents[0].delete(0, "end"), ents[0].insert(0, "q" * 0 + "p" * 32))); ui(lambda: bbtn("Save").invoke()); time.sleep(0.4)
    check("p" * 32 in open(cm).read() and json.load(open(os.path.join(home, ".opendm", "settings.json")))["extension_ids"] == ["p" * 32], "a valid extra extension ID is saved and added to the browser manifests")
    cbs = ui(lambda: [w for w in walk(bw) if w.winfo_class() == "TCheckbutton"]); ui(lambda: cbs[1].invoke()); time.sleep(0.3)
    check(json.load(open(os.path.join(home, ".opendm", "settings.json")))["autostart_from_browser"] is False, "the 'start OpenDM when the browser sends a download' switch is saved")
    ui(lambda: bw.destroy())
    # ---- 15. Wave 1: sounds, hashes, checksum entry, dark theme, new Options tabs, ftp in the Add dialog
    import hashlib
    st = app.mgr.settings
    def last_top(): return ui(lambda: [w for w in root.winfo_children() if w.winfo_class() == "Toplevel"][-1])
    def entries(w, ro=False): return ui(lambda: [e for e in walk(w) if e.winfo_class() == "TEntry" and (("readonly" in e.state()) == ro)])
    def press(w, text): ui(lambda: [b for b in walk(w) if b.winfo_class() == "TButton" and b.cget("text") == text][0].invoke())
    def labels(w): return ui(lambda: [l.cget("text") for l in walk(w) if l.winfo_class() == "TLabel"])
    played = []
    app.sounds.runner = lambda ev, custom: played.append(ev) or True
    app.sounds.last = 0
    d1 = ui(lambda: app.mgr.add("http://127.0.0.1:18789/a.jpg", app.folder.get(), 2))
    t0 = time.time()
    while d1.status != "Completed" and time.time() - t0 < 10: time.sleep(0.1)
    time.sleep(1.3)
    check(d1.status == "Completed" and ("all_done" in played or "complete" in played), f"a finished download plays a sound: {played}")
    played.clear(); app.sounds.last = 0
    ui(lambda: app.mgr.add("http://127.0.0.1:18789/nothere.bin", app.folder.get(), 1)); time.sleep(2.0)
    check(played == ["error"], f"a failed download plays the error sound (once): {played}")
    want = hashlib.sha256(open(d1.path, "rb").read()).hexdigest()
    ui(lambda: app.hashes_dialog(d1)); time.sleep(1.0)
    hw = last_top()
    ro = entries(hw, True)
    check(want in ui(lambda: [e.get() for e in ro]) and len(ro) == 4, "File hashes dialog shows MD5, SHA-1, SHA-256 and SHA-512")
    cmp_e = entries(hw)[0]
    ui(lambda: cmp_e.insert(0, want.upper())); time.sleep(0.3)
    check(any(t.startswith("MATCH") for t in labels(hw)), "...and says MATCH for the right value (any letter case)")
    ui(lambda: (cmp_e.delete(0, "end"), cmp_e.insert(0, "0" * 64))); time.sleep(0.3)
    check(any(t.startswith("DOES NOT MATCH") for t in labels(hw)), "...and DOES NOT MATCH for a wrong one")
    ui(hw.destroy)
    ui(lambda: app.tree.selection_set([i for i in app.tree.get_children() if app.tree.item(i, "values")[0] == "a.jpg"]))
    ui(app.properties_dialog); time.sleep(0.4)
    pw = last_top(); ents = entries(pw)
    ui(lambda: (ents[0].delete(0, "end"), ents[0].insert(0, "nonsense"))); press(pw, "OK"); time.sleep(0.3)
    check(dialogs[-1][0] == "showerror" and ui(pw.winfo_exists), "Properties: a value that isn't a hash is refused and the dialog stays open")
    ui(lambda: (ents[0].delete(0, "end"), ents[0].insert(0, want))); press(pw, "OK"); time.sleep(1.5)
    check(d1.checksum == "sha256:" + want and d1.verified == "ok" and [x[3] for x in rows() if x[0] == "a.jpg"] == ["Complete (hash OK)"], "Properties: expected hash saved, checked in the background, shown in the Status column")
    ui(app.properties_dialog); time.sleep(0.4)
    pw = last_top(); ents = entries(pw)
    ui(lambda: (ents[0].delete(0, "end"), ents[0].insert(0, "md5:" + "1" * 32))); press(pw, "OK"); time.sleep(1.5)
    check(d1.verified == "bad" and [x[3] for x in rows() if x[0] == "a.jpg"] == ["Complete - HASH MISMATCH"] and os.path.exists(d1.path), "a wrong hash is flagged in the list and the file is kept")
    # dark theme on live widgets
    st.update(theme="dark", accent="#16a34a"); ui(app.apply_theme); time.sleep(0.3)
    pal = opendm.PAL
    check(pal["mode"] == "dark" and ui(lambda: app.style.lookup("Treeview", "background")) == pal["field"], "dark theme: the download list is dark")
    got = ui(lambda: (str(app.gcv.cget("bg")), str(app.menubar.cget("bg")), str(app.root.cget("bg"))))
    check(got == (pal["graph_bg"], pal["panel"], pal["bg"]), f"dark theme: window, menus and the speed graph follow {got} vs {(pal['graph_bg'], pal['panel'], pal['bg'])}")
    ui(app.add_dialog); time.sleep(0.4); aw = last_top()
    check(ui(lambda: [w for w in walk(aw) if w.winfo_class() == "Text"][0].cget("bg")) == pal["field"], "dark theme: a dialog opened afterwards is dark too")
    check(ui(lambda: app.style.lookup("Treeview", "background", ["selected"])) in (pal["accent"], pal["field"]), "dark theme: style lookup works for the selection colour")
    # ftp address + checksum in the Add dialog (still open)
    txt = ui(lambda: [w for w in walk(aw) if w.winfo_class() == "Text"][0]); he = entries(aw)[0]
    ui(lambda: (txt.delete("1.0", "end"), txt.insert("1.0", "ftp://h.test/a.zip\nhttp://h.test/b.zip"), he.insert(0, want)))
    press(aw, "Download Later"); time.sleep(0.3)
    check(dialogs[-1][0] == "showinfo" and "single address" in dialogs[-1][1] and ui(aw.winfo_exists), "Add dialog: one checksum for two addresses is refused")
    ui(lambda: (txt.delete("1.0", "end"), txt.insert("1.0", "ftp://h.test/a.zip"), he.delete(0, "end"), he.insert(0, "zzz")))
    press(aw, "Download Later"); time.sleep(0.3)
    check(dialogs[-1][0] == "showinfo" and "checksum" in dialogs[-1][1] and ui(aw.winfo_exists), "Add dialog: a bad checksum is refused")
    ui(lambda: he.delete(0, "end")); press(aw, "Download Later"); time.sleep(0.5)
    check(any(isinstance(d, opendm.FtpDownload) and d.url == "ftp://h.test/a.zip" and d.status == "Paused" for d in app.mgr.items), "Add dialog accepts an ftp:// address (Download Later)")
    # options: proxy, appearance, sounds validation
    invoke(menu_of("Downloads"), "Options..."); time.sleep(0.6)
    ow = last_top(); nb = ui(lambda: [w for w in walk(ow) if w.winfo_class() == "TNotebook"][0])
    frame = lambda i: ui(lambda: nb.nametowidget(nb.tabs()[i]))
    combo = lambda f, word: ui(lambda: [w for w in walk(f) if w.winfo_class() == "TCombobox" and word in str(w.cget("values"))][0])
    f4, f6, f7 = frame(4), frame(6), frame(7)
    ui(lambda: nb.select(4)); ui(lambda: [w for w in walk(f4) if w.winfo_class() == "TRadiobutton" and "this proxy" in w.cget("text")][0].invoke())
    press(ow, "OK"); time.sleep(0.3)
    check(dialogs[-1][0] == "showerror" and "proxy" in dialogs[-1][1].lower() and ui(ow.winfo_exists), "Options: 'manual proxy' without a host is refused")
    pe, cb_type, cb_theme = entries(f4), combo(f4, "socks5"), combo(f6, "Dark")
    ui(lambda: [(pe[i].delete(0, "end"), pe[i].insert(0, v)) for i, v in enumerate(("127.0.0.1", "1080", "u", "p"))]); ui(lambda: cb_type.set("socks5"))
    ui(lambda: cb_theme.set("Dark"))
    qe = entries(f7); ui(lambda: (qe[-2].delete(0, "end"), qe[-2].insert(0, "99:99"))); press(ow, "OK"); time.sleep(0.3)
    check(dialogs[-1][0] == "showerror" and "22:00" in dialogs[-1][1] and ui(ow.winfo_exists), "Options: impossible quiet hours are refused")
    ui(lambda: (qe[-2].delete(0, "end"), qe[-2].insert(0, "23:00"))); press(ow, "OK"); time.sleep(0.6)
    cfg = json.load(open(os.path.join(home, ".opendm", "settings.json")))
    check(cfg["proxy_mode"] == "manual" and cfg["proxy_type"] == "socks5" and cfg["proxy_host"] == "127.0.0.1" and cfg["proxy_port"] == 1080 and cfg["theme"] == "dark" and cfg["sound_quiet_from"] == "23:00", "Options: proxy, theme and sound settings are saved")
    check(opendm.OPENER.proxy_url == "socks5h://u:p@127.0.0.1:1080" and opendm.PAL["mode"] == "dark", "...and take effect immediately (no restart)")
    if os.name == "posix": check(os.stat(os.path.join(home, ".opendm", "settings.json")).st_mode & 0o777 == 0o600, "the settings file (it holds the proxy password) is readable by you only")
    st.update(proxy_mode="system", proxy_host="", proxy_user="", proxy_pass="", theme="light", accent=opendm.DEFAULT_ACCENT); ui(app.mgr.apply_network); ui(app.apply_theme); time.sleep(0.3)
    check(opendm.PAL["mode"] == "light" and ui(lambda: app.gcv.cget("bg")) == "white" and ui(lambda: app.style.lookup("Treeview", "background")) != opendm.make_palette("dark")["field"], "switching back to light restores the light look")
    # ---- wave 2: antivirus verdict, clipboard history, floating widget, skins, customizable toolbar
    check("Clipboard history..." in labels(menu_of("Tasks")) and "Scan for viruses" in labels(menu_of("File")) and {"Floating widget", "Customize toolbar..."} <= set(labels(menu_of("View"))), "wave 2: menu entries are there")
    ui(lambda: app.set_toolbar(items=["add", "|", "clip", "widget", "scan"], style="icons", size="small")); time.sleep(0.3)
    check(ui(lambda: list(app.tbtn)) == ["add", "clip", "widget", "scan"] and ui(lambda: str(app.tbtn["add"].cget("text"))) == "", "toolbar: a custom layout (icons only, small) replaces the classic one")
    ui(app.update_state); ui(app.update_toolbar)
    ui(lambda: app.set_toolbar(items=None, style="both", size="large")); time.sleep(0.3)
    check(ui(lambda: list(app.tbtn)) == [e[0] for e in opendm.TOOLBAR if e] and ui(lambda: str(app.tbtn["add"].cget("compound"))) == "top", "toolbar: reset brings back the classic one")
    st["skin"] = "nord"; ui(app.apply_theme); time.sleep(0.3)
    check(opendm.PAL["mode"] == "dark" and ui(lambda: app.gcv.cget("bg")) == opendm.SKINS["nord"][1]["graph_bg"], "skin: Nord recolours the window (and forces dark mode)")
    st["skin"] = "default"; ui(app.apply_theme); time.sleep(0.3)
    check(opendm.PAL["mode"] == "light", "skin: back to default")
    ui(lambda: app.toggle_widget(True)); time.sleep(0.4)
    check(ui(lambda: app.widget.shown), "floating widget: shows")
    ui(app.widget.update); ui(lambda: app.toggle_widget(False)); time.sleep(0.2)
    check(not ui(lambda: app.widget.shown) and st["widget_on"] is False, "floating widget: hides and the choice is remembered")
    vd = opendm.Download("http://127.0.0.1:18789/a.jpg", app.folder.get()); vd.status, vd.path, vd.name, vd.size = "Completed", os.path.join(home, "a.jpg"), "a.jpg", 8000
    vd.scan, vd.scan_info = "infected", "WARNING: ClamAV found Eicar-Test-Signature."
    ui(lambda: app.complete_dialog(vd)); time.sleep(0.5)
    cw2 = last_top()
    check(ui(lambda: any(w.winfo_class() == "TLabel" and "Eicar-Test-Signature" in str(w.cget("text")) for w in walk(cw2))), "Download complete dialog shows the antivirus verdict")
    ui(cw2.destroy)
    # ---- screenshot: dress the list with a bit of everything
    for n in ("clip.mp4", "report.pdf", "song.mp3", "data.zip", "setup.exe"): api(f"http://127.0.0.1:18789/{n}")
    api("http://127.0.0.1:18789/slow.bin"); ui(lambda: app.mgr.add("http://127.0.0.1:18789/b.png", app.folder.get(), 1, later=True)); time.sleep(5)
    ui(lambda: app.show_graph.set(False)); ui(app.apply_layout)
    if os.environ.get("OPENDM_SHOT"):
        for m in ("PIL", "PIL.Image", "pystray"): sys.modules.pop(m, None)
        from PIL import ImageGrab
        ui(lambda: (root.lift(), app.side.selection_set("all"))); time.sleep(1.0); ImageGrab.grab(xdisplay=os.environ["DISPLAY"]).save(os.environ["OPENDM_SHOT"])
    print("\nFAILED:" if fails else "\nALL IDM-LAYOUT CHECKS PASSED", fails if fails else "")
    root.after(0, root.destroy)
threading.Thread(target=driver, daemon=True).start()
app.run()
sys.exit(1 if fails else 0)
