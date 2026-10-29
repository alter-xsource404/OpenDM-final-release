# Changelog

## 1.7.0
Focus: faster browser capture, faster download dialog, real file names, a leaner build. (Versions: app 1.7.0, extension 1.7.0, installer 1.7.0, Windows file version 1.7.0.0.)

### Browser capture
- **One persistent native-messaging connection** (`connectNative`) replaces a new host process for every message. With the packaged one-file exe, every `ping` / `config` / `add` / `formats` used to unpack and start the whole program (seconds). The connection is opened when the browser starts, so the first capture finds a running host. Replies are matched by id and a slow yt-dlp `formats` lookup runs on its own thread, so a download hand-over is never queued behind it. If the host dies, the next call reconnects once.
- The host now tries `/add` first and starts OpenDM only if nothing answers (was: ping, then add).
- The content script runs at `document_start` (was `document_idle`), so players created early are seen immediately.
- When a video starts playing on a yt-dlp-supported site, the extension asks OpenDM for the qualities in the background (only if OpenDM is already running; it never launches OpenDM), so the "Download this video" menu is filled when opened.
- Duplicate sniffed streams (e.g. Facebook byte-range pieces) are dropped in memory before any storage or tab lookup.

### Download dialog
- The capture dialog is polled every 100 ms (was 500 ms with the main tick); yt-dlp and ffmpeg lookup are warmed up in the background at start-up.
- *Start Download* starts the transfer immediately (`Manager.kick()`), not at the next tick.

### File names
- New `extension/names.js` + `pick_title()` in OpenDM: site title -> post caption -> structured data / Open Graph / page metadata -> `Content-Disposition` / URL name -> `<Site> video <id>`. Titles that only name the site ("Facebook", "Reels", "(3) Facebook", "Reel by ...") are rejected, which fixes names like `facebook 1920p.mp4`. The tab title is used only when it is not generic.
- The page caption is read from the post around the video (Facebook/Instagram etc.) on a best-effort basis; when a site exposes nothing usable the descriptive fallback is used.
- `clean_name()` now also strips zero-width/bidi characters, avoids Windows reserved names (CON, NUL, COM1 ...), limits the stem to 120 characters at a word boundary and keeps the extension. Existing duplicate handling still adds `(1)`, `(2)`.

### Size / packaging
- The old build bundled **two ffmpegs** (imageio-ffmpeg's ~80 MB inside the exe, plus the installer's separate 107 MB `ffmpeg.exe`). ffmpeg now ships once, beside `OpenDM.exe`.
- The installer packs a program **folder** (`--onedir`) instead of a one-file exe: no unpacking on every start, and the native host starts quickly. `python build.py --portable` still produces the single exe.
- Unused stdlib modules excluded (pydoc, idle, turtle, ...). Generated `build/`, stale `dist/*.exe` and `opendm.py.patch` are no longer in the source ZIP.

### Compatibility
- Settings, history and the installer `AppId` are unchanged, so upgrading in place keeps them. The native-host name and extension ID are unchanged. The extension must be reloaded after upgrading (it is updated together with the app).
