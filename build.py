#!/usr/bin/env python3
"""Build the desktop app with PyInstaller:  pip install -r requirements-build.txt && python build.py   (add --portable for a single .exe)"""
import platform, re, shutil, subprocess, sys
from pathlib import Path

# ===================== EDIT THESE: shown in the exe's Properties > Details, the installer and Windows prompts =====================
BRAND = {
    "publisher": "NovaTorrent Forge",
    "url": "https://github.com/alter-xsource404/OpenDM-final-release",
    "support_url": "https://github.com/alter-xsource404/OpenDM-final-release",
    "copyright": "Copyright (C) 2026 Rifat Howlader",
    "description": "OpenDM - fast, lightweight, open-source download manager",
}
# ====================================================================================================================================
VERSION = re.search(r'__version__\s*=\s*"([\d.]+)"', Path("opendm.py").read_text(encoding="utf-8")).group(1)


def write_branding():
    """Single source of truth: generates the Windows version resource for the exe and installer/branding.iss for Inno Setup."""
    v = tuple((list(map(int, VERSION.split("."))) + [0, 0, 0, 0])[:4])
    q = lambda t: str(t).replace("'", "")
    Path("version_info.txt").write_text(f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={v}, prodvers={v}, mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[StringFileInfo([StringTable('040904B0', [
    StringStruct('CompanyName', '{q(BRAND["publisher"])}'), StringStruct('FileDescription', '{q(BRAND["description"])}'),
    StringStruct('FileVersion', '{VERSION}'), StringStruct('InternalName', 'OpenDM'), StringStruct('LegalCopyright', '{q(BRAND["copyright"])}'),
    StringStruct('OriginalFilename', 'OpenDM.exe'), StringStruct('ProductName', 'OpenDM'), StringStruct('ProductVersion', '{VERSION}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])])
""", encoding="utf-8")
    Path("installer/branding.iss").write_text(
        f'#define AppVersion "{VERSION}"\n#define AppPublisher "{q(BRAND["publisher"])}"\n#define AppURL "{BRAND["url"]}"\n'
        f'#define AppSupportURL "{BRAND["support_url"]}"\n#define AppCopyright "{q(BRAND["copyright"])}"\n#define AppDescription "{q(BRAND["description"])}"\n',
        encoding="utf-8")


write_branding()

system = platform.system()
# v1.7 build modes (the old build was ONE 68 MB exe that carried a second, 80 MB copy of ffmpeg - the installer shipped another one):
#   python build.py              -> dist/OpenDM/ (a folder: no unpacking on every start, no unpacking when the browser starts the native host). The installer packs this folder.
#   python build.py --portable   -> dist/OpenDM-windows.exe (one file; needs ffmpeg next to it, in PATH or OPENDM_FFMPEG for merging) - add --bundle-ffmpeg to embed ./ffmpeg/ffmpeg.exe
PORTABLE = "--portable" in sys.argv
# NOTE: do not exclude "distutils", "setuptools", "pkg_resources", "wheel" or "pip": PyInstaller's own hooks alias them and fail with "already imported as ExcludedModule".
EXCLUDES = ["pydoc", "lib2to3", "test", "tkinter.test", "idlelib", "turtle", "turtledemo",
            "imageio_ffmpeg",   # ffmpeg ships ONCE, as ffmpeg.exe beside the program (find_ffmpeg looks there first)
            "PIL.ImageQt", "PIL.SpiderImagePlugin"]
cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile" if PORTABLE else "--onedir", "--name", "OpenDM", "opendm.py"]
cmd += ["--collect-all", "yt_dlp"]          # yt-dlp loads its site extractors lazily: bundle them all (Facebook, Instagram ...)
for m in EXCLUDES:
    cmd += ["--exclude-module", m]
if "--bundle-ffmpeg" in sys.argv and PORTABLE and system == "Windows" and Path("ffmpeg/ffmpeg.exe").is_file():
    cmd += ["--add-binary", "ffmpeg/ffmpeg.exe;."]
if system != "Darwin":
    cmd += ["--collect-submodules", "pystray"]  # the tray backends are imported dynamically
if system in ("Windows", "Darwin"):
    cmd.append("--windowed")  # no console window (GUI only; use `python opendm.py` for the CLI)
if system == "Windows":
    cmd += ["--icon", "assets/icon.ico", "--version-file", "version_info.txt"]
elif system == "Darwin":
    cmd += ["--icon", "assets/icon.icns"]
# Linux binaries can't carry an icon; the window icon is embedded in opendm.py instead.
subprocess.check_call(cmd)

dist = Path("dist")
if PORTABLE:
    if system == "Windows":
        (dist / "OpenDM.exe").replace(dist / "OpenDM-windows.exe")
    elif system == "Darwin":
        shutil.make_archive(str(dist / "OpenDM-macos"), "zip", dist, "OpenDM.app")
    else:
        (dist / "OpenDM").replace(dist / "OpenDM-linux")
elif system == "Windows" and Path("ffmpeg/ffmpeg.exe").is_file():
    shutil.copy2("ffmpeg/ffmpeg.exe", dist / "OpenDM" / "ffmpeg.exe")  # beside OpenDM.exe: where OpenDM looks first
total = sum(f.stat().st_size for f in dist.rglob("*") if f.is_file())
print(f"Built: {total / 1048576:.1f} MB in dist/ ->", *sorted(p.name for p in dist.iterdir()))
