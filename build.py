#!/usr/bin/env python3
"""Build a single-file desktop app with PyInstaller:  pip install -r requirements-build.txt && python build.py"""
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
cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--name", "OpenDM", "opendm.py"]
cmd += ["--collect-all", "yt_dlp",          # yt-dlp loads its site extractors lazily: bundle them all (Facebook, Instagram ...)
        "--collect-all", "imageio_ffmpeg"]  # bundle a copy of ffmpeg for merging video + audio
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
if system == "Windows":
    (dist / "OpenDM.exe").replace(dist / "OpenDM-windows.exe")
elif system == "Darwin":
    shutil.make_archive(str(dist / "OpenDM-macos"), "zip", dist, "OpenDM.app")
else:
    (dist / "OpenDM").replace(dist / "OpenDM-linux")
print("Built:", *sorted(p.name for p in dist.iterdir()))
