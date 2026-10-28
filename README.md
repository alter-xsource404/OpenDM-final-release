# OpenDM

![OpenDM's main window, laid out like a classic download manager](docs/screenshot.png)

A free, open-source download manager for Windows, macOS and Linux, inspired by tools like IDM.
One Python file, no dependencies for the basics.

- **Faster downloads:** splits files across up to 32 connections, and when one connection finishes early it takes over half of the slowest remaining piece (dynamic segmentation).
- **Pause and resume:** survives restarts. Failed connections retry automatically, and a resume first checks (ETag / Last-Modified) that the file on the server is still the same one - if it changed, OpenDM starts over instead of gluing two versions together.
- **Automatic retry:** a download that fails for a temporary reason (network down, busy server, `Retry-After`) is retried after a growing pause (15 s, 30 s, 1 min ...) and waits while the internet is down; wrong passwords and missing files are never retried. *Options > Connection.*
- **Checksums:** give a download an expected MD5 / SHA-1 / SHA-256 / SHA-512 (Add URL, *Properties*, or `--checksum` on the command line). It is checked in the background when the download finishes, shown in the Status column, and a mismatch is flagged loudly. *File > Verify checksum / hashes...* calculates all four and compares against a value you paste.
- **FTP and FTPS:** `ftp://` and `ftps://` links, with resume. Credentials can be in the link (`ftp://name:password@host/file`) or saved per site.
- **Proxies and logins:** system proxy (default), no proxy, or a manual **HTTP** or **SOCKS5** proxy with user name and password and a bypass list; HTTP Basic / Digest logins per site. yt-dlp and ffmpeg (HTTP proxies) use the same proxy. *Options > Proxy / Logins.*
- **Dark mode and accent colours:** light, dark, or follow the system, with seven accent colours or your own. *Options > Appearance.*
- **Sound alerts:** a sound when a download finishes, when the whole queue is done, or when something fails - only one sound per burst, optionally only when OpenDM isn't the window in front, with quiet hours and your own sound files. *Options > Sounds.*
- **Queue, speed limit, scheduler:** global and per-download speed limits you can change mid-download; run only between chosen hours (overnight windows work); optionally exit or shut down when finished.
- **Categories and auto-sorting:** downloads are sorted into `Video`, `Documents`, `Music`, `Compressed`, `Images`, `Programs` and `General` folders by file type (or by website), using the file's real name even when the server only reveals it after the download starts. A sidebar filters the list by category, *Unfinished* and *Finished*, with live counts. Add, rename and edit categories, or move a download with right-click > *Move to category*.
- **System tray:** an icon with a quick menu (show, pause/resume all, speed limit, open folder, quit), a tooltip with the live status, balloon notifications when a download finishes or fails, and *close to tray* so downloads carry on in the background.
- **A classic download-manager window:** menu bar (Tasks, File, Downloads, View, Help, Registration), an icon toolbar, a navigation tree (All Downloads with its categories, Unfinished, Finished, Grabber projects, Queues) and a sortable list with File Name, Q, Size, Status, Time left, Transfer rate, Last Try and Description columns.
- **Queues and a site grabber:** keep downloads in named queues you can start and stop together, and scan any web page for the images, videos, documents or archives it links to.
- **Live speed graph:** a 60-second speed chart (all downloads, or just the one you select) with Now / Peak / Avg, plus a segment map showing which parts of the file each connection has filled.
- **Video downloads:** HLS (`.m3u8`) streams with quality selection, AES-128 decryption and ffmpeg muxing to `.mp4`; DASH (`.mpd`) manifests through ffmpeg; and YouTube, Facebook, Instagram, Vimeo, TikTok and similar sites through yt-dlp.
- **Browser integration:** a Chrome/Edge/Brave/Firefox extension that takes over downloads, adds a right-click menu, and adds an IDM-style **Download this video** button with a quality picker on playing videos.
- **Antivirus check:** finished files are scanned by **Windows Defender** (`MpCmdRun.exe -Scan`) or **ClamAV** (`clamscan`) if one is installed, and the verdict is shown in the *Download complete* window and the Status column. OpenDM bundles no engine, only reports (it never deletes or quarantines), and never auto-opens a flagged file. *File > Scan for viruses* re-checks a file; `--scan` does it on the command line. *Options > Extras.*
- **Smart links:** *Resolve link...* in the Add dialog finds the real file behind a short link, a redirect or a "your download starts soon" page, and picks the best download link on a landing page (asking you when several look right). Redirect wrappers such as `google.com/url?q=...` are removed automatically. It does not get around logins, subscriptions or paywalls: those are reported, and the *Logins* settings / browser extension are the way to use your own account.
- **Clipboard history:** *Tasks > Clipboard history* keeps the web / FTP links you copy (off by default; only addresses are stored, in `clipboard.json`) so you can download them later.
- **Floating widget:** a small always-on-top speed meter with a progress ring. Drag it, double-click to open OpenDM, right-click for a menu. *View > Floating widget.*
- **Skins and a customizable toolbar:** Midnight, Nord, Solarized (light / dark), Forest and High contrast skins (*Options > Appearance*); choose, order and restyle the toolbar buttons (icons / text, large / small) with right-click on the toolbar or *View > Customize toolbar...*
- **GUI and CLI.**

OpenDM is an independent project. It is clean-room code written from public specifications (HTTP/1.1 Range requests, HLS). It contains no code from, and is not affiliated with, any commercial download manager.

## Install

**Option A: download a build** from the [Releases](https://github.com/alter-xsource404/OpenDM-final-release/releases/latest) page (Windows `.exe`, macOS `.app`, Linux binary).

**Option B: run from source** (Python 3.9+, tkinter included with most Python installs):

```
python opendm.py                 # GUI
pip install cryptography         # optional: only for AES-encrypted HLS streams
```

On Debian/Ubuntu you may need `sudo apt install python3-tk`. Install [ffmpeg](https://ffmpeg.org) if you want videos merged into `.mp4`.

## Usage

```
python opendm.py                                  # open the GUI
python opendm.py URL [URL ...] -n 8 -o ~/Downloads   # CLI: 8 connections
python opendm.py STREAM.m3u8 -q 720 -l 500        # video, max 720p, limit 500 KB/s
python opendm.py -p 6801                          # GUI, browser API on another port
```

Other options: `--scan` (CLI: scan each finished file with Defender / ClamAV, exit code 1 on a threat), `--sort` (CLI only: sort into category sub-folders of `-o`), `--minimized` (start in the tray), `--version`, `--checksum sha256:HASH` (CLI, one file: exit code 1 if it doesn't match) and `--proxy http://user:pw@host:3128` / `--proxy socks5://host:1080` (CLI). The CLI exits with 0 when everything downloaded (and matched), 1 otherwise.

### The window

| Part | What it does |
|---|---|
| **Menu bar** | *Tasks*: add a download, add all links from the clipboard, run the site grabber, export/import the list, exit. *File*: open, open folder, move/rename, redownload, properties, copy address. *Downloads*: resume, stop, delete, move to a category or queue, start/stop queue, speed limiter, scheduler, categories, options. *View*: show or hide the toolbar, categories pane, speed graph and status bar; sort. *Help*, and *Registration* (OpenDM is free, so this just says so and shows the MIT license). |
| **Toolbar** | Add URL, Resume, Stop, Stop All, Delete, Delete C. (completed), Options, Scheduler, Start Queue, Stop Queue, Grabber and Browser (extension pairing). Buttons grey out when they don't apply. |
| **Navigation tree** | *All Downloads* with a folder per category, *Unfinished*, *Finished*, *Grabber projects* (one entry per project) and *Queues*. Counts are live. Right-click a queue to start, stop, rename or delete it. Drag the divider to resize. |
| **List** | **File Name**, **Q** (place in its queue), **Size**, **Status** (`Complete`, `45.30%`, `Stopped 12.0%`, `Queued`...), **Time left** (`2 min 15 sec`), **Transfer rate** (`1.5 MBytes/sec`), **Last Try** (`Oct 21 11:03:12 2026`), **Description** (the source site; edit it in Properties). Click a title to sort. |

Add downloads with **Add URL** (`Ctrl+N`): paste links, optionally pick a category and queue, then **Start Download** or **Download Later** (it waits in its queue until you start it). Double-click a finished file to open it; right-click for Open, Resume, Stop, Delete, Move to category/queue, Limit speed, Redownload, Properties and Copy address.

**Queues.** Every download belongs to a queue (`Main download queue` by default; create more with *Downloads > New queue*). *Start Queue* / *Stop Queue* act on the queue selected in the tree. Queues organise and start/stop work; the number of simultaneous downloads and the scheduler window apply to everything.

**Site grabber** (*Tasks > Run site grabber*). Enter a page address, choose what to look for (images, video, documents, archives...) and whether to follow that site's links one level, press *Explore*, tick the files you want and download them. They are grouped as a *Grabber project* in the tree. It reads normal HTML pages; pages that build their links with JavaScript show nothing.

**Keyboard:** `Ctrl+N` add, `Ctrl+R` resume, `Ctrl+S` stop, `Del` delete, `Enter` open, `Alt+Enter` properties, `F2` rename, `F5` refresh, `Ctrl+A` select all, `Ctrl+C` copy address.

### Categories

Open *Downloads > Categories* (or right-click a category in the tree) to edit them. Each category has a name, file types (`mp4, mkv`), an optional save folder (empty means `<download folder>/<name>`; relative folders are relative to the download folder) and optional websites (`school.example`: everything from that site goes here, even `.mp4` files). Rules are checked top to bottom, websites before file types, and **General** catches everything else. Turn auto-sorting off with the checkbox to keep everything in one folder (the category is still shown and filterable).

Right-click a download > **Move to category** to override it: before it starts that changes where it will be saved; once it has finished the file is moved. A half-downloaded file can't be moved. Deleting or renaming a category updates the downloads that used it.

### System tray

Needs the optional add-on: `pip install pystray pillow` (included in the Windows and Linux builds). Turn it on or off in *Downloads > Options*.

- Menu: Show OpenDM (also double-click), Pause all, Resume all, Speed limit (No limit / 256 KB/s / 512 KB/s / 1 MB/s / 5 MB/s), Open download folder, Quit.
- The window's close button hides OpenDM to the tray instead of quitting (switch off in Options). Use *Quit OpenDM* in the tray menu to exit.
- Balloon notifications appear when a download finishes or fails while the window is hidden or not in front.
- Not available on macOS (the library needs the thread the window uses). On GNOME, install the *AppIndicator* extension to see tray icons. If the tray can't start, OpenDM keeps working and Options says why.

### Automatic updates

A few seconds after start-up OpenDM asks GitHub (in the background) for the [latest release](https://github.com/alter-xsource404/OpenDM-final-release/releases/latest). If it is newer than the running version, a window shows the release notes with **Update now** / **Later**. You can also use **Help > Check for updates...**, or turn the start-up check off in Options > General.

- **Portable `.exe`**: the portable file of the release (name contains `portable`) is downloaded next to the running copy and swapped in as soon as OpenDM quits; then it starts again.
- **Installed copy** (has `unins000.exe` beside it): the installer (name contains `setup` or `installer`) is downloaded and run with Inno Setup's `/SILENT` switches; then OpenDM starts again.
- Running from source, or on macOS / Linux: the download page opens instead.
- Downloads are only accepted from GitHub over HTTPS, and are checked against the size and SHA-256 that GitHub lists for the file. Active downloads are paused and can be resumed after the restart.
- To publish an update: raise `__version__` in `opendm.py`, tag the release with a higher version (e.g. `v1.6.1`) and attach both files. Pre-releases and drafts are never offered.

### Configuration (Downloads > Options)

One window with every setting. Tabs:

| Tab | What it holds |
|---|---|
| **General** | Tray, notifications, start minimized; start OpenDM when you sign in; auto-start links copied to the clipboard. |
| **Save to** | Default folder, per-category folders, temporary folder for streaming (HLS) downloads, duplicate links (ask / ignore / add again), existing file (add a number / replace). |
| **Connection** | Connections, simultaneous downloads, speed limit, HLS quality, timeout, retries, automatic retry. |
| **Browser** | Pairing token and the browser integration setup. |
| **Capture** | Capture downloads from browsers on/off; which browsers; the key that lets the browser download (not OpenDM) and the key that forces OpenDM; right-click menu entries and the on-page video button. |
| **File types** | File types OpenDM takes over, file types it never takes over (images and web files by default), unknown types, sites to leave alone, minimum size. |
| **Proxy / Logins** | System / no / manual HTTP or SOCKS5 proxy, per-site logins. |
| **Appearance, Sounds, Extras** | Skins and accent colours; download sounds; antivirus, smart links, clipboard history, floating widget. |

The browser extension reads the capture rules from OpenDM, so there is one place to change them. A browser download is taken over only if it is fresh, you are in that browser window, it follows a real click (or a typed address), and it passes these rules; everything else is left to the browser.

## Browser extension

**Automatic setup.** Every time OpenDM starts it registers itself with your browsers ("native messaging"), so the extension needs no port, no token and no configuration:

1. Run OpenDM once. The **Browser** toolbar button shows what got registered (and lets you repair or remove it).
2. **Chrome / Edge / Brave / Chromium:** open `chrome://extensions` (or `edge://extensions`), enable *Developer mode*, *Load unpacked*, choose the `extension/` folder.
   **Firefox:** in `extension/`, replace `manifest.json` with `manifest.firefox.json`, then `about:debugging` → *This Firefox* → *Load Temporary Add-on*. (The extension id `opendm@alter-xsource404.github.io` must match in that manifest and in `FIREFOX_EXTENSION_ID` in `opendm.py`.)
3. Open the extension's options page: it should say *Connected to OpenDM through the browser integration*.

That is all. If OpenDM isn't running when you click a download, the extension starts it (minimized to the tray) and hands the download over. Turn that off in **Browser** if you prefer to start OpenDM yourself.

**How it works.** The browser looks up a *native messaging host* named `org.opendm.nativehost`:

| Where | What OpenDM writes |
|---|---|
| **Windows** (current user only, no admin rights) | A manifest under `%USERPROFILE%\.opendm\native\` and a registry value pointing at it: `HKCU\Software\Google\Chrome\NativeMessagingHosts\org.opendm.nativehost` and `HKCU\Software\Microsoft\Edge\NativeMessagingHosts\org.opendm.nativehost`. Brave, Chromium and Firefox get the same under their own vendor keys (`BraveSoftware\Brave-Browser`, `Chromium`, `Mozilla`), but only if that browser's key already exists. Chrome and Edge are always registered. |
| **Linux / macOS** | The manifest file in each installed browser's `NativeMessagingHosts` folder (for example `~/.config/google-chrome/NativeMessagingHosts/`). |

When the extension sends a message, the browser starts the host: OpenDM itself in a special mode (`OpenDM.exe`, or a tiny launcher for the Python script). The host forwards the job to OpenDM's local server on `127.0.0.1` (default `6800`; it reads the real port and the pairing token from `~/.opendm`, so a different `-p` port works too) and exits. It is re-registered on every start, so moving the app or upgrading Python repairs itself. To remove everything: **Browser > Remove registration**, or `python opendm.py --unregister-browsers`. To register without opening the window: `python opendm.py --register-browsers`.

**Checking it on Windows.** In a command prompt:

```
reg query "HKCU\Software\Google\Chrome\NativeMessagingHosts\org.opendm.nativehost"
reg query "HKCU\Software\Microsoft\Edge\NativeMessagingHosts\org.opendm.nativehost"
```

Each should print one `(Default)` value: the path of a `org.opendm.nativehost.json` file. If the extension says it isn't connected, open the extension's service worker console from `chrome://extensions` and look for `Specified native messaging host not found` (not registered, or the extension ID doesn't match) or `Access to the specified native messaging host is forbidden` (the ID isn't in the manifest's `allowed_origins`). OpenDM also keeps a log of what the host did in `~/.opendm/native-host.log`.

**Extension ID.** Browsers only let the extensions listed in a host's manifest talk to it. `extension/manifest.json` carries a fixed `key`, so the unpacked extension always gets the ID `jngcdhpgdacflokoombdcimnonfngiff` (`python tools/extension_id.py` prints it). If you publish the extension in a store, the store assigns its own ID: add it under **Browser > Also trust these extension IDs**, or run `python opendm.py --register-browsers --extension-id <id>`.

**Manual pairing** (token and port, as before) still works as a fallback, shown under *Advanced* in the extension's options and in the **Browser** dialog.

Downloads you click are handed to OpenDM (if OpenDM isn't running, the browser keeps them). Right-click a link for *Download link with OpenDM*.

**"Download this video" button.** When a video plays, a small *Download this video* button appears on its top-right corner (drag it, double-click to reset, `×` hides it for that video). Click it to pick a quality:

- **Sites yt-dlp supports (YouTube, Facebook, Instagram, Reels, Vimeo, TikTok ...):** the menu lists every resolution with its size and ETA. OpenDM downloads the best video and the best audio separately and merges them into one `.mp4` with ffmpeg, so the result always has sound. Your browser's cookies, User-Agent and Referer are forwarded, so logged-in and private videos work.
- **Other sites:** the menu falls back to the streams the browser actually loaded (HLS qualities, DASH, direct files). Sites that serve picture and sound as two files are detected as a pair (by content type, `mime=` or Facebook's `efg` tag, small audio files included) and sent together, then merged by ffmpeg. A video whose audio could not be found is labelled *no sound*.
- Names come from the video's caption, in an editable box.
- The toolbar popup is minimal: *Capture browser downloads*, *Show the button*, and the connection status.
- Streams hidden behind `blob:` URLs without a visible network request can't be read; play the video first. The button can't run on browser-internal pages or extension stores. Without ffmpeg OpenDM keeps video and audio as separate files so nothing is lost.

## Security model

- **Native messaging:** the browser starts the host only for the extension IDs in its manifest, and the host checks the caller again before doing anything (a stranger gets exit code 2 and no reply). Registration is per user (`HKCU`), needs no administrator rights, and the host speaks only the browser's framed JSON protocol on stdin/stdout. It forwards only a fixed list of job fields, and only `http(s)` addresses.
- **Local server:** OpenDM's API listens on `127.0.0.1` only. A request must carry the pairing token (stored in `~/.opendm/token`), must not come from a web page (requests with a website `Origin` are rejected), and must have a localhost `Host` header (blocks DNS rebinding). The host never uses a system proxy for these local calls.
- **Proxy passwords and site logins** are stored in `~/.opendm/settings.json` (and logins from a link in `downloads.json`) as plain text, in files only your user account can read (`chmod 600`; on Windows they live in your profile). Logins are given only to the site they were saved for, and are dropped on a redirect to another host.
- **The browser API** still accepts only `http://` and `https://` links; `ftp://` works from the Add URL box, the command line and list import.
- **Cookies** sent by the extension are kept in memory, are sent only to the original host (never forwarded on cross-host redirects), and are never written to disk, so a login-protected download cannot resume after OpenDM restarts unless you send it again from the browser.
- Keep your token private. Anyone who can already read your user profile can read it.

## Limitations

- HLS **live streams** and **DRM-protected** streams (Widevine, FairPlay, SAMPLE-AES) are not supported, and OpenDM does not attempt to circumvent DRM.
- Video+audio merging needs ffmpeg, and pairing relies on both tracks having been loaded by the page (play the video for a few seconds first).
- **DASH** (`.mpd`) is handled by ffmpeg, so it needs an ffmpeg build that can read DASH. The ffmpeg bundled with the Windows installer can; some minimal builds can't, and OpenDM then shows an error instead of a file. DRM-protected DASH is refused.
- **Video sites** (YouTube etc.) rely on yt-dlp, which the release builds include. Sites change often, so if one stops working, update it with `pip install -U yt-dlp` when running from source.
- Automatic browser setup was built and tested with the Windows registry API replaced by a faithful stand-in, and for real on Linux (files, launcher, protocol); it hasn't been run against real Chrome or Edge on Windows yet, so please use the checks above and report anything odd. Each download sent through the host starts a short-lived process (about a second with the one-file `.exe`).
- The scheduler works only while OpenDM is running.
- The tray icon isn't available on macOS, and on GNOME it needs the AppIndicator extension.
- Please respect copyright and each website's terms of service. You are responsible for what you download.

## Development

```
python -m unittest discover -s tests -v      # core app: local servers, no internet needed
xvfb-run -a python tests/gui_smoke.py          # drives the real window (needs a display; skips without one)
(cd tests/js && npm install && npm test)      # extension: background logic, stream pairing, native host
pip install pillow && python tools/make_icons.py   # regenerate all icons from code (assets/, extension/icons/, window + panel icons)
pip install -r requirements-build.txt && python build.py   # standalone app for your OS (dist/)
```

CI runs the tests on Windows, macOS and Linux. Pushing a tag like `v1.2.0` builds all three apps and attaches them, plus the extension zip, to a GitHub Release.

Ideas for contributions: a proper packaged extension for the Chrome/Firefox stores, clipboard history, torrent/magnet hand-off, translations.

## License

MIT, see [LICENSE](LICENSE).


## Video sites, streams and file-type detection

- **Video sites** (YouTube, Facebook, Instagram, Vimeo, TikTok ...): `pip install yt-dlp`. OpenDM asks yt-dlp for the best stream (capped by *Video quality* in Options), then downloads it with its own multi-connection engine and merges video + audio with ffmpeg.
- **ffmpeg** is looked up in `OPENDM_FFMPEG`, next to `opendm.py` (or in `./ffmpeg`, `./bin`), the `imageio-ffmpeg` package, then PATH. It merges HLS/DASH/video+audio into `.mp4` (re-encoding only the audio if needed, else `.mkv`).
- **File names**: Content-Disposition, redirects, `?filename=` parameters, Content-Type and magic bytes decide the extension, so `12345` becomes `12345.pdf`. Google Drive share links work. A link that returns a web page instead of the file is reported as an error.
- **Fallback**: if a server refuses parallel/ranged requests, the file restarts as one plain stream; failed downloads never leave zero-byte files behind.
