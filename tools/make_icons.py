#!/usr/bin/env python3
"""Regenerates every icon from code. Needs Pillow:  pip install pillow
Run from the repo root:  python tools/make_icons.py
Writes assets/icon.{png,ico,icns}, extension/icons/icon{16,32,48,128}.png and
refreshes the embedded icons inside opendm.py (window icon + toolbar/tree icons) and extension/content.js."""
import base64, io, re
from pathlib import Path
import math
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
S = 1024  # master canvas; everything is drawn big and scaled down for crisp edges


def master():
    top, bot = (59, 130, 246), (29, 78, 216)  # blue gradient (#3b82f6 -> #1d4ed8)
    g = Image.linear_gradient("L").resize((S, S))
    bg = Image.composite(Image.new("RGB", (S, S), bot), Image.new("RGB", (S, S), top), g).convert("RGBA")
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle((40, 40, S - 40, S - 40), radius=210, fill=255)
    bg.putalpha(mask)

    glyph = Image.new("L", (S, S), 0)  # white download arrow dropping into a tray
    d = ImageDraw.Draw(glyph)
    d.rectangle((442, 190, 582, 480), fill=255)                                  # shaft
    d.polygon([(302, 450), (722, 450), (512, 690)], fill=255)                    # head
    d.rounded_rectangle((252, 770, 772, 840), radius=35, fill=255)               # tray bottom
    d.rounded_rectangle((252, 640, 322, 840), radius=35, fill=255)               # tray left
    d.rounded_rectangle((702, 640, 772, 840), radius=35, fill=255)               # tray right

    shadow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    shadow.putalpha(glyph.point(lambda v: v * 70 // 255).transform((S, S), Image.AFFINE, (1, 0, 0, 0, 1, -16)))
    shadow = shadow.filter(ImageFilter.GaussianBlur(14))
    out = Image.alpha_composite(bg, shadow)
    white = Image.new("RGBA", (S, S), (255, 255, 255, 255))
    white.putalpha(glyph)
    return Image.alpha_composite(out, white)


# ---------------- toolbar + tree icons (drawn on 256 px, shipped at 32 px / 16 px) ----------------
BLUE, GREEN, RED, ORANGE, GREY = ((96, 165, 250), (29, 78, 216)), ((74, 222, 128), (21, 128, 61)), ((248, 113, 113), (185, 28, 28)), ((251, 191, 36), (217, 119, 6)), ((156, 163, 175), (75, 85, 99))


def disc(colors):
    top, bot = colors
    g = Image.linear_gradient("L").resize((256, 256))
    im = Image.composite(Image.new("RGB", (256, 256), bot), Image.new("RGB", (256, 256), top), g).convert("RGBA")
    mask = Image.new("L", (256, 256), 0)
    ImageDraw.Draw(mask).ellipse((10, 10, 246, 246), fill=255)
    im.putalpha(mask)
    return im


def glyph(im, fn):
    """Draw white shapes (with a soft shadow) on top of `im`."""
    layer = Image.new("L", (256, 256), 0)
    fn(ImageDraw.Draw(layer))
    shadow = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    shadow.putalpha(layer.point(lambda v: v * 80 // 255).transform((256, 256), Image.AFFINE, (1, 0, 0, 0, 1, -8)).filter(ImageFilter.GaussianBlur(5)))
    white = Image.new("RGBA", (256, 256), (255, 255, 255, 255))
    white.putalpha(layer)
    return Image.alpha_composite(Image.alpha_composite(im, shadow), white)


def blank():
    return Image.new("RGBA", (256, 256), (0, 0, 0, 0))


def gear_points(cx, cy, r_out, r_in, teeth=8):
    pts, step = [], 360 / teeth
    for i in range(teeth):
        a = i * step
        for ang, r in ((a - 15, r_in), (a - 9, r_out), (a + 9, r_out), (a + 15, r_in)):
            pts.append((cx + r * math.cos(math.radians(ang)), cy + r * math.sin(math.radians(ang))))
    return pts


def tray_bin(d, fill="#f87171", dx=0, dy=0):
    d.rounded_rectangle((52 + dx, 62 + dy, 204 + dx, 88 + dy), radius=10, fill=fill)       # lid
    d.rounded_rectangle((100 + dx, 40 + dy, 156 + dx, 66 + dy), radius=10, fill=fill)       # handle
    d.polygon([(70 + dx, 96 + dy), (186 + dx, 96 + dy), (174 + dx, 216 + dy), (82 + dx, 216 + dy)], fill=fill)


def draw_ui_icons():
    out = {}
    out["add"] = glyph(disc(BLUE), lambda d: (d.rounded_rectangle((108, 52, 148, 204), radius=14, fill=255), d.rounded_rectangle((52, 108, 204, 148), radius=14, fill=255)))
    out["resume"] = glyph(disc(GREEN), lambda d: d.polygon([(98, 62), (98, 194), (200, 128)], fill=255))
    out["stop"] = glyph(disc(RED), lambda d: d.rounded_rectangle((72, 72, 184, 184), radius=18, fill=255))
    out["stopall"] = glyph(disc(RED), lambda d: (d.rounded_rectangle((54, 54, 150, 150), radius=14, outline=255, width=16),
                                                 d.rounded_rectangle((100, 100, 200, 200), radius=14, fill=255)))
    out["startq"] = glyph(disc(GREEN), lambda d: (d.polygon([(54, 70), (54, 186), (124, 128)], fill=255), d.polygon([(120, 70), (120, 186), (194, 128)], fill=255)))
    out["stopq"] = glyph(disc(RED), lambda d: (d.rounded_rectangle((58, 72, 88, 184), radius=8, fill=255), d.rounded_rectangle((112, 72, 198, 184), radius=14, fill=255)))
    # delete: a red bin with white ribs
    im = blank(); d = ImageDraw.Draw(im); tray_bin(d)
    for x in (112, 140):
        d.rounded_rectangle((x - 6, 112, x + 6, 196), radius=6, fill="#ffffff")
    out["delete"] = im
    # delete completed: bin + green check badge
    im = blank(); d = ImageDraw.Draw(im); tray_bin(d, "#f87171", -18, -10)
    for x in (94, 122):
        d.rounded_rectangle((x - 6, 102, x + 6, 178), radius=6, fill="#ffffff")
    badge = glyph(disc(GREEN).resize((130, 130)).resize((256, 256)), lambda dd: dd.line([(70, 132), (114, 176), (192, 82)], fill=255, width=30, joint="curve"))
    badge = badge.resize((120, 120), Image.LANCZOS)
    im.alpha_composite(badge, (128, 128))
    out["delc"] = im
    # options: gear
    im = blank(); d = ImageDraw.Draw(im)
    d.polygon(gear_points(128, 128, 116, 88), fill="#6b7280")
    d.ellipse((38, 38, 218, 218), fill="#6b7280")
    d.ellipse((84, 84, 172, 172), fill="#f3f4f6")
    d.ellipse((106, 106, 150, 150), fill="#6b7280")
    out["options"] = im
    # scheduler: clock
    im = blank(); d = ImageDraw.Draw(im)
    d.ellipse((14, 14, 242, 242), fill="#ffffff", outline="#2563eb", width=18)
    for k in range(12):
        a = math.radians(k * 30)
        d.line([(128 + 82 * math.sin(a), 128 - 82 * math.cos(a)), (128 + 96 * math.sin(a), 128 - 96 * math.cos(a))], fill="#9ca3af", width=8)
    d.line([(128, 128), (128, 54)], fill="#1f2937", width=16)
    d.line([(128, 128), (180, 156)], fill="#1f2937", width=16)
    d.ellipse((112, 112, 144, 144), fill="#dc2626")
    out["scheduler"] = im
    # grabber: magnifying glass over a page
    im = blank(); d = ImageDraw.Draw(im)
    d.rounded_rectangle((120, 26, 232, 150), radius=14, fill="#e5e7eb", outline="#9ca3af", width=8)
    for y in (58, 86, 114):
        d.line([(142, y), (210, y)], fill="#9ca3af", width=8)
    d.ellipse((24, 84, 150, 210), fill="#dbeafe", outline="#2563eb", width=20)
    d.line([(132, 192), (212, 238)], fill="#1d4ed8", width=34)
    d.ellipse((196, 220, 230, 254), fill="#1d4ed8")
    out["grabber"] = im
    # browser: globe
    im = glyph(disc(BLUE), lambda d: (d.ellipse((46, 46, 210, 210), outline=255, width=14), d.ellipse((92, 46, 164, 210), outline=255, width=12),
                                      d.line([(46, 128), (210, 128)], fill=255, width=12), d.arc((60, 70, 196, 186), 0, 180, fill=255, width=10)))
    out["browser"] = im
    # tree icons
    out["t_all"] = glyph(disc(BLUE), lambda d: (d.rounded_rectangle((108, 52, 148, 130), radius=10, fill=255), d.polygon([(64, 124), (192, 124), (128, 196)], fill=255)))
    im = blank(); d = ImageDraw.Draw(im)
    d.rounded_rectangle((20, 52, 112, 100), radius=14, fill="#f5b942")
    d.rounded_rectangle((20, 74, 236, 206), radius=16, fill="#fbd160", outline="#d89a1d", width=8)
    out["t_folder"] = im
    out["t_unfinished"] = glyph(disc(ORANGE), lambda d: (d.polygon([(76, 58), (180, 58), (128, 126)], fill=255), d.polygon([(128, 130), (76, 198), (180, 198)], fill=255)))
    out["t_finished"] = glyph(disc(GREEN), lambda d: d.line([(62, 132), (110, 182), (196, 80)], fill=255, width=34, joint="curve"))
    out["t_grabber"] = out["grabber"]
    im = blank(); d = ImageDraw.Draw(im)
    d.rounded_rectangle((26, 26, 230, 230), radius=36, fill="#3b82f6")
    for y in (70, 114, 158):
        d.ellipse((54, y - 12, 78, y + 12), fill="#ffffff")
        d.rounded_rectangle((96, y - 10, 202, y + 10), radius=10, fill="#ffffff")
    out["t_queue"] = im
    return out


def sized(img, n):
    return img.resize((n, n), Image.LANCZOS)


def main():
    m = master()
    (ROOT / "assets").mkdir(exist_ok=True)
    (ROOT / "extension" / "icons").mkdir(parents=True, exist_ok=True)
    sized(m, 512).save(ROOT / "assets" / "icon.png", optimize=True)
    m.save(ROOT / "assets" / "icon.ico", sizes=[(n, n) for n in (16, 24, 32, 48, 64, 128, 256)])
    sized(m, 512).save(ROOT / "assets" / "icon.icns")
    for n in (16, 32, 48, 128):
        sized(m, n).save(ROOT / "extension" / "icons" / f"icon{n}.png", optimize=True)

    buf = io.BytesIO()
    sized(m, 128).save(buf, "PNG", optimize=True)
    b64 = base64.b64encode(buf.getvalue()).decode()
    lines = "\n".join(f'    "{b64[i:i + 100]}"' for i in range(0, len(b64), 100))
    src = (ROOT / "opendm.py").read_text(encoding="utf-8")
    new, n = re.subn(r"(# --- window icon.*?\n)ICON_B64 = \(.*?\n\)\n(# --- end window icon ---)",
                     lambda mo: f"{mo.group(1)}ICON_B64 = (\n{lines}\n)\n{mo.group(2)}", src, flags=re.S)
    if n != 1:
        raise SystemExit("icon markers not found in opendm.py")
    (ROOT / "opendm.py").write_text(new, encoding="utf-8")

    # floating panel icon (48 px, inlined so web pages can never request it)
    buf48 = io.BytesIO()
    sized(m, 48).save(buf48, "PNG", optimize=True)
    uri = "data:image/png;base64," + base64.b64encode(buf48.getvalue()).decode()
    # toolbar (32 px) + tree (16 px) icons for the main window
    ui = {}
    for name, im in draw_ui_icons().items():
        b = io.BytesIO()
        sized(im, 16 if name.startswith("t_") else 32).save(b, "PNG", optimize=True)
        ui[name] = base64.b64encode(b.getvalue()).decode()
    body = "\n".join(f'    "{k}": (\n' + "\n".join(f'        "{v[i:i + 96]}"' for i in range(0, len(v), 96)) + "\n    )," for k, v in ui.items())
    src2 = (ROOT / "opendm.py").read_text(encoding="utf-8")
    new2, n3 = re.subn(r"(# --- ui icons.*?\n)UI_ICONS = \{.*?\}\n(# --- end ui icons ---)", lambda mo: f"{mo.group(1)}UI_ICONS = {{\n{body}\n}}\n{mo.group(2)}", src2, flags=re.S)
    if n3 != 1:
        raise SystemExit("ui icon markers not found in opendm.py")
    (ROOT / "opendm.py").write_text(new2, encoding="utf-8")
    sheet = Image.new("RGBA", (12 * 80 + 20, 220), (240, 240, 240, 255))
    for i, (name, im) in enumerate(draw_ui_icons().items()):
        n = 16 if name.startswith("t_") else 32
        big = sized(im, n).resize((n * 2, n * 2), Image.NEAREST)
        sheet.alpha_composite(big, (10 + (i % 12) * 80, 10 + (i // 12) * 90))
    sheet.save(ROOT / "assets" / "ui_icons_preview.png")

    cp = ROOT / "extension" / "content.js"
    js, n2 = re.subn(r"/\* ICON-BEGIN \*/.*?/\* ICON-END \*/", lambda mo: f'/* ICON-BEGIN */ const ICON = "{uri}"; /* ICON-END */',
                     cp.read_text(encoding="utf-8"), flags=re.S)
    if n2 != 1:
        raise SystemExit("icon markers not found in extension/content.js")
    cp.write_text(js, encoding="utf-8")
    print("icons written; embedded window icon refreshed")


if __name__ == "__main__":
    main()
