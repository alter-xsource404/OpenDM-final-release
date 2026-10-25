#!/usr/bin/env python3
"""
OpenDM - a free, open-source download manager (MIT License)

Features: multi-connection segmented downloads with dynamic splitting, pause/resume
(even after restart), queue, speed limiter, scheduler, HLS (.m3u8) video downloads,
browser extension integration, categories with auto-sorting, system tray, GUI (tkinter) and CLI.
Standard library only (optional: `cryptography` for AES-encrypted HLS, `pystray`+`pillow` for the tray icon,
`ffmpeg` for mp4 muxing and HLS/DASH merging - found via OPENDM_FFMPEG, next to this file, `imageio-ffmpeg`, or PATH; `yt-dlp` for YouTube/Facebook/Instagram/... pages).

GUI:  python opendm.py
CLI:  python opendm.py URL [URL ...] [-n 8] [-o ~/Downloads]
"""
import os, sys, json, time, threading, argparse, subprocess, platform, secrets, re, shutil
import http.server, html.parser, math, copy, queue, io, base64, shlex, struct
import urllib.error, mimetypes
from collections import deque
import urllib.request, urllib.parse
from email.message import Message

__version__ = "1.5.0"
UA = f"Mozilla/5.0 (compatible; OpenDM/{__version__})"
CHUNK = 64 * 1024
MAIN_QUEUE = "Main download queue"
HIST = 120  # seconds of speed history kept for the graph
MIN_SPLIT = 1024 * 1024  # only steal work when >= 1 MiB remains in a segment
CFG_DIR = os.environ.get("OPENDM_HOME") or os.path.join(os.path.expanduser("~"), ".opendm")  # OPENDM_HOME: keep settings elsewhere (portable install, tests)
DB_FILE = os.path.join(CFG_DIR, "downloads.json")
API_PORT = 6800
# --- window icon (regenerate with tools/make_icons.py) ---
ICON_B64 = (
    "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"
)
# --- end window icon ---
# --- ui icons (regenerate with tools/make_icons.py) ---
UI_ICONS = {
    "add": (
        "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"
    ),
    "resume": (
        "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"
    ),
    "stop": (
        "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"
        "RU5ErkJggg=="
    ),
    "stopall": (
        "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"
    ),
    "startq": (
        "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"
    ),
    "stopq": (
        "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"
    ),
    "delete": (
        "iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAYAAABzenr0AAAD+klEQVR42u1XPW8cVRQ9987H7mxsrYItgTBEwuWmCxIFBQXK"
        "PyB2iYQUpUBKtJbSj7dKabZJkRaJIoYCkYLKXURLk22sSMhCGxs7GH/J8/XuoZjZXTsk9q4TGsiTppjd9+4977x7z3kD/N+H"
        "XGQRAQH5QiSBAPzXETOO9SL/vVEGNhYWog+vXavvbWwAzSaaAP7Y38/fvX//8I0CYBwrer1yzuXLiuvXLX/8+BMNw+/MuWkz"
        "k4p++kGQFWn6da3f/wmtlodezw2TrK66iQEQkJedadJux7Xp6eX04AC+5wEACjPUpqaQHh5+W19Z+XISBvwzkDG7c+fjIIqa"
        "SZYRIj7MHETec2lqBCx3zqumO5emnpBTx+3251D1fLKAqrAojsNu95exGeDDh54sLrpkaemLWhh+D7NTle6cQ+4cRUQwYkhI"
        "0lOVwPcx7BASCEOkx8dL9ZWVbwaxT+b7Z9U+eSLlWn4K30eS51laFEiKgkme05nBUxUVgYpI9cBTFZJI8pxJUbBak5W45bOT"
        "sc8G0OuV8M1+LrLsUESUZAagAFAYkDvypY8B+WAeyVxExJxLYfYjAODqVU7UBTu3b38wU6u9kzvXmKSwcgBBEIBmieX5X1G3"
        "+9vERcg49qXT+T1tt5ue5/1QOEcBQBFhdcZlGQA0g6gOz14BF6h6SZZ9FXW7v/LWrUAePMgnAgDAGMea7u5mVH2/5vtlxbFq"
        "UBHArHyPIiDLgKotOSrCrNISe1WSV0vn8jKl07Fao7HjzJ4XJFMzS4+O6G7coN28yeTggNnsLHn3LvP5eaZHR8zMLDdjmiQm"
        "wDPpdAytFicGMKAXT5/um8ieryogIaqic3OiV66Iqoo2m6IzM6KzsyJmQhHxVIXAUa3R+HOwmckZAEhSZHXVKbBd0V4GyvOS"
        "8rJbymMoiuEqTwQisosw3Du1mQkBAIuLWrXKFlRPCRJOBn3hXVRB8rl0OhnP6bSzAbRaUvnCZpXgfL8XYXU32AIAxLGctW48"
        "/yb7Q2k9fy6hCohsjpNjLAAEng2pHt/n++PMOxtAJctGblamNDYCG4B+LQCjsWXOAaQOj+KkS5qd3jxZgn5tAJWANES2M+dc"
        "5XhErQY0GiNVVAVUwZIioXMIVDdPmduFAAwEpF7fBbknZYXTra3RPXpEqtL6fRZra3Tr65QwNAEkLQqac9snN3HRS6kAIBcW"
        "vOO5ufUoCD5KioKSpqUqRhHoHJCmQBgCngdfFZlzh1EUzcu9e9skRQYCdoEaGKmhyEALDPU60GiUpqMKXLoEeB5IWnVR2RlH"
        "Bc9zw4EnEABqwALIKbGXGFv1m1QJaZZKp5ONuvi/8GkWx7EuTxK40zG8HWOMvwEVfkMcu2R4iAAAAABJRU5ErkJggg=="
    ),
    "delc": (
        "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"
    ),
    "options": (
        "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"
    ),
    "scheduler": (
        "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"
    ),
    "grabber": (
        "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"
        "gg=="
    ),
    "browser": (
        "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"
        "At57fvY3s3njzWMcOl6hLptg7QvvUQspVCF4tXG5SKy19QCmu1vtpifb3wvevSQ2p7U4+Hwuw8adJV7Y9D6fuvYStuwd4Znn"
        "97Lm3rmkUxHXzcsxtSDENU8cexoySteVOawxrPrKb7Bp2xH+7aUjdC+dxRtvDfIfrw1RqMsRx96LzeBr5e1bGtu3oirRB1og"
        "q3BuWfBBUEM628Q3n3iT3+ws8O0/u5KVf7eV5fe+zDe+OI9FV01l/ffqCGpQwKDUZYQd+wZ58Okd5OsyfP8vr6ZUiVm5ZgfB"
        "NoFYvAsqUVJ8qKymV0IXGtndu3uVHjXHHykcaLnyyzfYZOEyVyv5RCJphsccGzbv51PXtnLzknaCCj/86X4+s+hSBja/z5of"
        "7mb9pvcYG69y5WWNPPDUdj5yeQvf/cpHiJ3nSw9s4o13kzQ0NOO8ehPlIlcZ2R3R/hdHl8O7vYuDOaeSRRPmy65aKqomJK6F"
        "kK+fwltHM3z23g28+Isj3P57s3juO4tIRIZr5reQTqVxIeKTC9swRnj8r6/ja1+Yy+adJ1j+1QFe2wWNja3UYtUQjPrYaQj8"
        "yetPSdy9e74A+qGW7Io79q2I0k3/6mtjDg3GGjXF0dNUi8f49McL3L6sg48vaKMumzyvma1UHdvePMXan+7nPzeeQhMtFJpa"
        "8cEoiIsyUxKufHLl7n+ZveqMrw81pV1dA9Grry52l9+27z6bbloV4jE0OG+M2ODKDJ4+DvEIM1stsy/N0dqUQQROD1d458g4"
        "B446vMnTOKWNRDKHVzyIRKkmE1dOrd777Jyvn/Fx4bZ88oPLbt13h7HpfxCbzIZ41INgjdrgapRLRSqVEs7FgGJtgnQmSyZT"
        "h02k8EECEEyUjVRDwNfu37u285Hu7j7b378iTIwSv24wmYTo7N6zwCZya8SmbkQ9wY0D4gQQoyJnejsRnVRmRbEmyoqYBN6V"
        "t4mv3LOvb+4Guvss/Sv8xY9m59zTnFve+byqvRsNi0wij2oAnRCcCf8WxCJiCK4EhNdFePztfS/8gNfvjH857BcFcKZdpxcF"
        "UYDO7kMLQnCLBb06aJgpGppBQGQIOIKxW8VEAwf62jefb+PCw+nFrW6151bM+fy/+gxdXQPRr95z/vp/zj9JD0F9FlwAAAAA"
        "SUVORK5CYII="
    ),
    "t_all": (
        "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAADIklEQVR42k2TTYjVZRjFz/O+/4/7MZPz5VCaH+k4UQuxsrDJ"
        "CAraGEGLaRshYVCBq2j350IQwQRGSBBCtIiYhlBbhKtECAs0oiCLHG/kOJGDjjP33v/X+7zv87QYpvytzuKczTkcwiaqBCIF"
        "gNkvtdkOOCgcpgyBNLLdwuLywss0AIAsU9PpkAAA3R1+Jjsfbd/11HEyeI2A6SiOAQDBM1TRFeDTWJfnPnv1gQqZGnRIaFPM"
        "ftjbalvpV3EredpXAXVVgYMKAMSWTJqmiJoRXFH/CJe/NP/G+FKWqaEsU3MFv0Z+fNf5dHhopu73HQdE20dgXn+2CUPAqQsV"
        "uiuiSUyctoeTush/4aT95GN/ozKdDkk9vONN2xiaGdxec+I1KctgJhoOB3ZG2L8jwn1th6ISkqDJ4M6as2l7vxn03ul0SMwL"
        "2XKLnX+r7JUSWCPhAA0KZoEoIAo4J4BXKAcEr1Gxngu7cOzIe2ujUY34IIndzXmuREQDp+iXinxrgNmoGEUZcHtd4ZnQSMio"
        "Fmrj1qRndzhij32RjeDZCSD2iakGylrw0Dbz38LT22L0asI9TYvLizWCQmCMYccPRsELKYmqV+QVYzIp8PYru3E3R58fw1EA"
        "J09fx7d9i1YjgieBOCFTO77mqopc7U3DRvjkXIET838AAHxQ+KAAgFNfX8OJMz0kNoKrArnKEXtZNM06ueTK6kaQROuKZWJ0"
        "DB+dLfH5uT8RWUJkCWcvLOH9+R7GRibgatYghuoiX618/p3969Kcm3z0eMvEI89xnbMEsY1GG99cXMEjewi37pQ49sEy2lvu"
        "hYYAH8TbeNz6Oj/588d7zxAyNYeuLKWDIblo05EDvlp1xlDMgSjVWzCkKHQCSQQVAdt0SyLcv1r0/ePdh/f0DQD8sLCzLAt+"
        "sS76P6kdT5gtUfBahtEw4LFgJCizIbWjiSvz30PJR7oLe9cBwKBDgiwz1+b3La2v3jzsitV3meUG+4RUmxbUtBwS8qz/uGJ9"
        "zpU3D/32xdTV/8+0SZYZdDoCAPfPXh+LRWZEedoApJQsGuHvu6enVja8G2EA+BcuNdVpchzQYQAAAABJRU5ErkJggg=="
    ),
    "t_folder": (
        "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAABbElEQVR42qWTvU4bURCFv5m73t3wI6H0CBQKWnoKLEhegSoN"
        "oqPIKzg8QF4hL0CDUoKETOqUCCUSKEqJFEUBO1nW3juTwoDxImIjTjl3dHR+5sIzIQDuLX3wsncqsrkXJyJ4DN5C2801pT06"
        "bzbhffvYdncxASgOXm/ls8nbohNNFbJUtSjt29Sbw51xChKAsiy285xV61eICr0Ise/r5x+XznpV71cQl+jiACr4dAo/L3uf"
        "V95dfE8Afne73Xx+OXoSY4WHgTnh1fziB7Tm0hxmG9iXkyO42EgAQiPVbO5lSEIfgXC7W0EUwUcIAjFIGpI0m7mzAA5VhVlV"
        "TzV4PViQEDXgxHsEA8ljSqmXJwD63ENKbggNdwM39zEyBruCYEMCZ5qpTBt90Qep12GmvMjAfBhi+afz6errycJ14Y77/22J"
        "WJ6rln87+yOn3IJ8cWFy71s/uL73mRAR8aeE5+4igstwMHGHt607wD/kuopaCvZpAQAAAABJRU5ErkJggg=="
    ),
    "t_unfinished": (
        "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAC9klEQVR42l2Ty2udVRTFf/t8537ffeRxNcZGTUttYxQHtkIc"
        "mFbRiSKl0v4DovgAoaBDRegl4ETQuSLWBzoQ7UCEdiIUQSpiBZFUCmlTNE1NG9ukubm5937nnL0dNCnFNdqTvdhrr7WETZgh"
        "IhiAnR6vobWpFNIE4iTLbJ5YnJGn/1wHsBZOZlAAuX35VAu/78ndb4q4VzEmfUUASMEwkXmz+Oni3+n9+1/6q7dFIlvD2omx"
        "0cJVj+cDPJFWVukFABQDBFdUwDebhA1+ixvl4frhywvWwokZ7uw3D/udeftUY5DpdmeoLHYc8BqDE5FNeYZkhZWLJ8NgcS3f"
        "6Lg/6i48zsF/el4EvfHt6pFGw0+3V7Tsdq/kvWI/o3sOcjuuzf8ocfaznKovB5vyyNqKe2tYOCqLH91Trw3I2VrBjm4QnAW3"
        "dD2y7dAPNO/bA6a0ly+wePwpxoYiZIXm3igD/4r5h1ylsKnMdGeno2IhOU0V7qonFk++TAgBxbNw4hVG8g5QoCG5bkclF7tb"
        "U3+/J8UHvM8oo6lBBorLGgyvz3Lx+9cRX2dg7Rf88CixH7YsV1cRF0p90GtE1KlpsE1TQZOSC2S+CxlkYoRSwXSLgBQEooq3"
        "nl3oqUpKOAGQDIttaOxi7LmPEV9l6YvfsdVzSD4AmjCQUIrEYOedy9yv/Z5eyjFL0VTLPrEfaD7zCWR1zIQ7nj1GjBmp1yVF"
        "LFOVTidd72j5k9t2ZHk9Bf2w4c1psJh6fUYOfE5t+z7EOcRlFGN7GT30NRqUVKY4lCMp6rHJN9aXxVq4hSEKKwdPN6tp73Jo"
        "lr3dL1RiDCLiNjUr3hdWvfhVGHFX83ZZmQtkj+3qrrRvRXnuner2eiP7rlGxRy8vb9CPmHCzMAYuz5B7R2t0kzu3EcLzE0fL"
        "OWtt/q3Vws3MoGdeoz46XnvbO/+iCOP+5gFEBTWWTPXLK53Ou1PvceNWmbaiukUCMNsaunOA3nSITDpBvHA+bFR+nvigc/X/"
        "df4PznCTYY1+rJoAAAAASUVORK5CYII="
    ),
    "t_finished": (
        "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAADPElEQVR42l2TTWhcZRSG3/N99yd30vw2aSVETdM0DVoktrHS"
        "mFJECAjF0kpBFOOqQqGUuJEWK5dxa3AhCq783QhRrEs1UgYh3TRdhBpKkwbR2iZpMpPxzp079/s7LpIU8cALZ3POeXg5L2Gn"
        "mAlEDABn/3wnqnP7iNN2gIlIBt5yrWpulA4VawCAOBYoFh0A0H+HT1yLvbDHTILoHBiDIpAgEJw2YMIyO/5C3b83VXrxq8bO"
        "Etppxm5e7g59/t5vazpuajlcbsDMbguPhAw9hK0RGtVsTtXz078d/egvcCwo5lhMTy94XU/2Xgs6CqOqnCoQeQDENh8IBDBz"
        "YjLdvrsjsEk+X6OWYyePoCGKVHSdPY9dkC3BaH2lqqyxgdVGWG1g1ZaM0shzRae7RgO9lipXkM9EjfKlIhUdHbnxdsGvyt8p"
        "lE+43ECSEA78yFuPJNbzKi7ufxXnB05hduOWm7z1CaST657PQ0KsmBFrbZ9OGgTDIslSmO3LpBmryQbO7B3D+f2nAACzizdF"
        "vZISCHsadTsmtLUHHBjOWLeRVPB0cx+cMnDaYiPdxPNtQ7hy6C2AgC/nruLj298h9ANnjGGTq4PCGkOsLSdpijf2jePr41cw"
        "efAs7lVW0evvxtTIBUReiJk71/HB3OfobOuAaWgYpWGVJs9l+q5xRDrLRVQj+MLDm4MvI9cKw10HsLfQiYUHS7j464cI2yPY"
        "3MCxJQFHUHZJdr/21LpOzUTYFLb8fGeWOTU01n8Yh/cMoWdXNx4mZbw+fQnlIENIPozWDCIyua5ohXflw+kF1X5yoECh91Ik"
        "Qv3T4qwMcoFj/cNQWmPi28uYz/5Aa9gMpQ2cdUYUfOnq+adL5364Sohj0du6EPpN2awo+MMuMyopV/0zfSdoPdtEqTyPjtZ2"
        "GGsYgBYFP3ANuyj+yZ5bzl5ICDEEinA9U+OPy0D+KCP/WTQsKpsV9jzpWqJdsNYJ8gRR5MHl5raz+pW/J2cWEUNIlMCIIZL3"
        "7labj7Z9wxywtba/0BS1+UEgLDvBzOSsXWFlP0sf2Im192fub2Wo5OjRy22TAEBvPN6pC3aUrB0Eg8iXSy4V11eLv6z9P87/"
        "AkRrwk7jiuQVAAAAAElFTkSuQmCC"
    ),
    "t_grabber": (
        "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAACvUlEQVR42qWTT0jUURDHv/Pe29+ureuKm2bGSmFFB1Po0KEC"
        "Aysk7K8JQVFBVERFZB3qEIsdoi5BRYe6dIkig8ro/9+tIOpkkJShUbFF6brquuu6u773psPa9s9bc5yZ7wdm5jvAfwZNlGRm"
        "IiI+f/5aMbvkcm2tgjWAyNUd5bYZtnd3bFjZryYChMNhCUDLArWzYVn9UaMzIBLjcAtPgRd37j46BuDQn4DmNlnXV0rhaKlA"
        "HSsl73vBWkciX7Vl/tmrZ1bNUI7b8QDAL0CIBVrJPAXw4hkABrwtNxPGkiopLoLl8V4CAFJsrfkFyInt7K29CwdHPVtAZvpw"
        "gjvf9HaXL6Q0ooPDBLZ5vd9fDBBRDtDMEq1kqjZ/366p8GzjgkmYWQG8i2DJuRdzEAyOor7aJ+MphhQ5nZQCbHNAhStkanYP"
        "zhhK8JmWVS7evBQ6MwbhuMCnrzsidCktKrYlTMAHHjMAEemSQABCCMqP8K0v2zivukw1LbI6GmeXtoBLApuWenD1+SgiqUq5"
        "eL7AQJIgyCq3uwDZbFbnAYa52F8IK4SAtgwlAG0AR1lbXlokLtzuap+U7AkPp6RwFBnHcdn4SPJqHuD3qpfvPhkRibKumqo4"
        "nmIKFJF9/YHtp29p+z5avfdx09zPE3lGIMTi+PLA44FY7MHhi8p5/maMYnHDDzuMaL3IaiSeSFehZ93G/fe8BCDU1unsOXnb"
        "zcy5g4KZQEBDKObr/ChPCaKmIi8VDiX1EOvMfZlKrhVOmTLZWAezPfKlfdb1CX6BCSAGgNp9/dMGR3xTpnqyX1+d8vUGV3Tt"
        "hHQdlO7JlayTYD1yw5r0iS83a54CTL89ExNCILSS/cudtmL124Bi9wEm3iVdfh9IwGSi6yPtcy7/u5UQCzSzxPiMqHuSt/u0"
        "Ne9rgyu7b1WujXwPNnYtAoAfgZI8aInDPDkAAAAASUVORK5CYII="
    ),
    "t_queue": (
        "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAACIUlEQVR42p2TPWgUURSFv/tmJjOb3UwSRQ1BhChCwGChxYKF"
        "ESSSTiEgYmsrlrb+FQmJWAiWCdpbRSVgsPCHgAoWEhvBCIqiG4mJuruz8/OuxYYxZrTQ17zXnO+de7gHAFDhn09b47YfosMX"
        "NHA601G1NmwmCSVjihqvQ1W0ES+v3l+Yku+oiqAqh85/qUhYmVc/qMYxVAJoxGDt5k/B90Fa0WKrHh95Ph6uuIioe7k+kgVB"
        "daDcjLeFxiy8zti/y1AJBFUQIb8/rNjss1Ma6tDsOCIzLoDvmbDWwJ4e8czwoOOOTkZcGfPp6ylGM/si4dIctseVcD0DaKaa"
        "dZcwE3dje21OiDMYux7hOsUYWqkSVjwTNclygCdIPYWjex12bzfMPEo5WXXpLf8awSoYgZfvMxbetTU5wDiQJLBvp6G6x+Hm"
        "45TDgw79PUWAojx8C/66IxcgSiAswdS9BCTFd+HUjQjzh+0QlL4dHtGPDYDAg68RnDvmcWDA4eytFtNn2iFudvDgVcr0Uyg7"
        "GwA2A0fg05qyVLNkFt7UlLUmBcDHVcURUDGaA2JFyiXs7WcJqRW6AuHqXIxqcQTXwJat2KhuTQ4QSwPBlH1JxEBmld7yXxqg"
        "pAiBiGm0AariXGQ+qUeLHV2dQzZtW5XiFoOCcXCTeryUmXQ27wIienBCuzttdkI1Ca21qP2dIQY1GIzr1e232p0n4/3LaN7i"
        "/6jzuvgn6Db1/EKzIN8AAAAASUVORK5CYII="
    ),
}
# --- end ui icons ---
ACTIVE = ("Connecting", "Downloading")


def human(n):
    if n is None or n < 0:
        return "?"
    for u in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.0f} {u}" if u == "B" else f"{n:.1f} {u}"
        n /= 1024
    return f"{n:.1f} PB"


def size_mb_bytes(n):
    """'12.34 MB (12,939,264 Bytes)': the size line of the Download complete dialog."""
    if n is None or n < 0:
        return "unknown size"
    return f"{n / 1048576:.2f} MB ({n:,} Bytes)"


def clean_name(s):
    s = "".join("_" if c in '<>:"/\\|?*' or ord(c) < 32 else c for c in s).strip(" .")
    return s or "download"


# ============================ speed graph helpers ============================
def nice_max(v):
    """Round a peak speed up to a tidy axis maximum (e.g. 300 KB -> 400 KB) so grid lines read cleanly."""
    if v <= 0:
        return 1024.0
    unit = 1
    while v / unit >= 1000 and unit < 1024 ** 4:
        unit *= 1024
    x = v / unit
    e = 10 ** math.floor(math.log10(x))
    for m in (1, 2, 4, 8, 10):
        if x <= m * e:
            return max(m * e * unit, 1024.0)
    return max(10 * e * unit, 1024.0)


def graph_stats(samples, window=60):
    data = list(samples)[-window:]
    return (data[-1] if data else 0.0, max(data, default=0.0), sum(data) / len(data) if data else 0.0)


def draw_graph(cv, samples, window=60):
    """Filled line chart of the last `window` seconds, newest at the right edge. `cv` is a tk Canvas."""
    cv.delete("all")
    W, H = max(cv.winfo_width(), 200), max(cv.winfo_height(), 60)
    L, R, T, B = 66, 10, 8, 18
    pw, ph = W - L - R, H - T - B
    data = list(samples)[-window:]
    ymax = nice_max(max(data, default=0.0) * 1.15)
    grey, font = "#6b7280", ("TkDefaultFont", 8)
    for i in range(5):
        y = T + ph * i / 4
        cv.create_line(L, y, W - R, y, fill="#e5e7eb")
        cv.create_text(L - 6, y, text=human(ymax * (4 - i) / 4) + "/s", anchor="e", fill=grey, font=font)
    for frac, label, anchor in ((0, f"{window}s ago", "w"), (0.5, f"{window // 2}s", "center"), (1, "now", "e")):
        cv.create_text(L + pw * frac, H - 8, text=label, anchor=anchor, fill=grey, font=font)
    if not data:
        return
    pts = [(L + pw * (window - len(data) + i) / (window - 1), T + ph * (1 - min(v / ymax, 1.0)))
           for i, v in enumerate(data)]
    poly = [(pts[0][0], T + ph)] + pts + [(pts[-1][0], T + ph)]
    cv.create_polygon([c for p in poly for c in p], fill="#bfdbfe", outline="")
    if len(pts) > 1:
        cv.create_line([c for p in pts for c in p], fill="#2563eb", width=2)
    x, y = pts[-1]
    cv.create_oval(x - 3, y - 3, x + 3, y + 3, fill="#2563eb", outline="white")


def draw_segmap(cv, cells):
    """Bar showing which parts of the file are downloaded. cells = [(x0, x1, filled_to)] in 0..1."""
    cv.delete("all")
    W, H = max(cv.winfo_width(), 100), max(cv.winfo_height(), 10)
    if not cells:
        cv.create_text(6, H / 2, text="Select a single download to see its segments", anchor="w",
                       fill="#6b7280", font=("TkDefaultFont", 8))
        return
    for x0, x1, xf in cells:
        cv.create_rectangle(x0 * W, 1, x1 * W, H - 1, fill="#e5e7eb", outline="#9ca3af")
        if xf > x0:
            cv.create_rectangle(x0 * W, 1, xf * W, H - 1, fill="#2563eb", outline="")



# ============================ categories & auto-sorting ============================
def _cat(name, exts="", folder="", sites=""):
    return {"name": name, "exts": exts.split(), "folder": folder, "sites": sites.split()}


DEFAULT_CATEGORIES = [
    _cat("General"),  # catch-all: saved straight into the download folder
    _cat("Compressed", "zip rar 7z tar gz tgz bz2 xz zst lz lzma cab z"),
    _cat("Documents", "pdf doc docx xls xlsx ppt pptx odt ods odp txt rtf csv epub mobi md odf pages"),
    _cat("Music", "mp3 flac wav aac m4a ogg opus wma aiff mka weba amr mid midi"),
    _cat("Video", "mp4 mkv avi mov webm flv wmv m4v ts mpg mpeg 3gp m2ts vob ogv mts rm rmvb asf"),
    _cat("Images", "jpg jpeg png gif webp bmp svg tif tiff ico heic avif"),
    _cat("Programs", "exe msi dmg pkg deb rpm apk appimage iso bat sh msix msp appx jar whl"),
]


def classify(cats, name, url=""):
    """Category for a file: a website rule wins, then the file extension, else General."""
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    for c in cats:
        if any(host == s or host.endswith("." + s) for s in c.get("sites", []) if s):
            return c["name"]
    ext = os.path.splitext(name or "")[1].lower().lstrip(".")
    if ext:
        for c in cats:
            if ext in c.get("exts", []):
                return c["name"]
    return "General"


def category_folder(cats, name, base):
    """Where a category's files go: its own folder (absolute, or relative to `base`), else <base>/<name>."""
    c = next((c for c in cats if c["name"] == name), None)
    f = os.path.expanduser((c or {}).get("folder") or "")
    if f:
        return f if os.path.isabs(f) else os.path.join(base, f)
    return base if c is None or name == "General" else os.path.join(base, clean_name(name))


def matches_filter(d, flt):
    kind, _, val = flt.partition(":")
    if kind == "unfinished":
        return d.status != "Completed"
    if kind == "finished":
        return d.status == "Completed"
    if kind == "cat":
        return d.category == val
    if kind == "queue":
        return d.queue == val and d.status != "Completed"
    if kind == "queues":
        return d.status != "Completed"
    if kind == "project":
        return d.project == val
    if kind == "projects":
        return bool(d.project)
    return True


def unique_path(folder, name):
    stem, ext = os.path.splitext(name)
    path, n = os.path.join(folder, name), 0
    while os.path.exists(path):
        n += 1
        path = os.path.join(folder, f"{stem} ({n}){ext}")
    return path



# ============================ list-view formatting (IDM style) ============================
def fmt_left(sec):
    """Time left, IDM style: '12 sec', '2 min 15 sec', '1 h 03 min'."""
    if sec is None or sec < 0:
        return ""
    sec = int(sec)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h} h {m:02d} min" if h else f"{m} min {s:02d} sec" if m else f"{s} sec"


def fmt_rate(bps):
    if not bps or bps < 1:
        return ""
    n, i = float(bps), 0
    while n >= 1024 and i < 3:
        n /= 1024
        i += 1
    return (f"{n:.0f}" if i == 0 else f"{n:.1f}") + f" {('Bytes', 'KBytes', 'MBytes', 'GBytes')[i]}/sec"


def fmt_when(ts):
    return time.strftime("%b %d %H:%M:%S %Y", time.localtime(ts)) if ts else ""


def status_text(d):
    if d.status == "Completed":
        return "Complete"
    if d.status == "Error":
        return "Error" + (f": {d.error[:40]}" if d.error else "")
    note = f" ({d.note[:30]})" if getattr(d, "note", "") else ""
    if d.status == "Connecting":
        return "Connecting..."
    if d.status == "Downloading":
        return (f"{d.percent:.2f}%" if d.size > 0 else "Receiving...") + note
    if d.status == "Queued":
        return "Queued"
    return (f"Stopped {d.percent:.1f}%" if d.size > 0 and d.done else "Stopped") + note


def queue_positions(items):
    """Q column: each unfinished download's place (1, 2, 3...) in its queue."""
    count, out = {}, {}
    for d in items:
        if d.status != "Completed":
            count[d.queue] = count.get(d.queue, 0) + 1
            out[id(d)] = count[d.queue]
    return out


COLUMNS = (("name", "File Name", 250), ("q", "Q", 36), ("size", "Size", 75), ("status", "Status", 112),
           ("left", "Time left", 82), ("rate", "Transfer rate", 118), ("last", "Last Try", 168), ("desc", "Description", 150))


def sort_key(d, col, qpos):
    if col == "name":
        return d.label.lower()
    if col == "q":
        return qpos.get(id(d), 10 ** 9)
    if col == "size":
        return d.size
    if col == "status":
        return (d.status == "Completed", d.percent)
    if col == "left":
        return d.eta_sec if d.eta_sec is not None else float("inf")
    if col == "rate":
        return d.speed
    if col == "last":
        return d.last_try
    return (d.desc or "").lower()


# ============================ site grabber (find downloadable files on a web page) ============================
PAGE_EXTS = {"", "html", "htm", "php", "asp", "aspx", "jsp", "shtml", "xhtml"}
NOISE_EXTS = {"css", "js", "json", "xml", "map", "woff", "woff2", "ttf", "otf", "eot", "rss", "atom", "ico"}


class _LinkParser(html.parser.HTMLParser):
    def __init__(self, base):
        super().__init__(convert_charrefs=True)
        self.base, self.links, self.title, self._in_title = base, [], "", False

    def _add(self, tag, value):
        value = (value or "").strip()
        if value and not value.lower().startswith(("javascript:", "mailto:", "data:", "tel:", "#", "blob:")):
            u = urllib.parse.urldefrag(urllib.parse.urljoin(self.base, value))[0]
            if u.lower().startswith(("http://", "https://")):
                self.links.append((tag, u))

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        self._in_title = self._in_title or tag == "title"
        for k in ("href", "src", "data-src", "data-original", "poster"):
            self._add(tag, a.get(k))
        for part in (a.get("srcset") or "").split(","):
            self._add(tag, part.strip().split(" ")[0])

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data


def extract_links(html_text, base):
    """All absolute http(s) links on a page as [(tag, url)], plus the page title."""
    p = _LinkParser(base)
    try:
        p.feed(html_text)
    except Exception:
        pass
    return p.links, " ".join(p.title.split())


def url_ext(u):
    return os.path.splitext(urllib.parse.urlparse(u).path)[1].lower().lstrip(".")


def default_fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,*/*;q=0.5"})
    with OPENER.open(req, timeout=20) as r:
        if "html" not in (r.headers.get("Content-Type") or "text/html").lower():
            return "", r.geturl()
        charset = r.headers.get_content_charset() or "utf-8"
        return r.read(2 << 20).decode(charset, "replace"), r.geturl()


def grab_site(start, wanted, depth=0, any_file=False, max_pages=20, fetch=default_fetch):
    """Look for downloadable files on a page (and, with depth=1, on pages of the same site it links to).
    wanted: set of extensions; any_file: also accept any other file-looking link.
    Returns (files, title) where files = [{"url", "name", "ext", "page"}]."""
    host = urllib.parse.urlparse(start).netloc
    todo, seen, files, found, title = [start], {start}, [], set(), ""
    while todo and len(seen) <= max_pages:
        page = todo.pop(0)
        try:
            text, final = fetch(page)
        except Exception:
            continue
        links, t = extract_links(text, final)
        title = title or t
        for tag, u in links:
            ext = url_ext(u)
            if ext in wanted or (any_file and ext and ext not in PAGE_EXTS and ext not in NOISE_EXTS):
                if u not in found:
                    found.add(u)
                    name = urllib.parse.unquote(os.path.basename(urllib.parse.urlparse(u).path)) or urllib.parse.urlparse(u).netloc
                    files.append({"url": u, "name": name, "ext": ext, "page": page})
            elif depth > 0 and tag == "a" and ext in PAGE_EXTS and urllib.parse.urlparse(u).netloc == host and u not in seen and len(seen) < max_pages:
                seen.add(u)
                todo.append(u)
    return files, title


def tray_tooltip(items, speed):
    active = sum(d.status in ACTIVE for d in items)
    queued = sum(d.status == "Queued" for d in items)
    if not active and not queued:
        return "OpenDM - idle"
    return f"OpenDM - {active} downloading, {human(speed)}/s" + (f", {queued} queued" if queued else "")


class _Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None and urllib.parse.urlparse(newurl).netloc != urllib.parse.urlparse(req.full_url).netloc:
            for k in [k for k in new.headers if k.lower() == "cookie"]:
                del new.headers[k]
        return new


OPENER = urllib.request.build_opener(_Redirect())


class Limiter:
    """Smooth bandwidth limiter shared by every connection that uses it (bytes/s, 0 = off)."""
    def __init__(self, rate=0):
        self.rate, self.next, self.lock = rate, 0.0, threading.Lock()

    def set_rate(self, rate):
        with self.lock:
            self.rate, self.next = max(0, int(rate)), 0.0

    def wait(self, n, stop=None):
        with self.lock:
            if self.rate <= 0:
                return
            now = time.monotonic()
            start = max(self.next, now)
            self.next = start + n / self.rate  # reserve this chunk's time slot
            delay = start - now
        if delay > 0:
            stop.wait(delay) if stop is not None else time.sleep(delay)


GLOBAL_LIMIT = Limiter()


def _chunk_for(*limiters):
    """Smaller reads under a tight limit keep the speed smooth and pausing responsive."""
    rates = [l.rate for l in limiters if l.rate > 0]
    return CHUNK if not rates else max(2048, min(CHUNK, int(min(rates) // 8)))


def power_off():
    try:
        sysname = platform.system()
        if sysname == "Windows":
            subprocess.Popen(["shutdown", "/s", "/t", "5"])
        elif sysname == "Darwin":
            subprocess.Popen(["osascript", "-e", 'tell application "System Events" to shut down'])
        else:
            subprocess.Popen(["systemctl", "poweroff"])
    except OSError:
        pass


def parse_hm(text):
    t = time.strptime(text.strip(), "%H:%M")
    return t.tm_hour * 60 + t.tm_min


# ============================ universal engine helpers ============================
def find_ffmpeg():
    """ffmpeg to use: $OPENDM_FFMPEG, a copy bundled with OpenDM (next to the program, in ./ffmpeg or ./bin, inside a
    PyInstaller build, or in ~/.opendm), the imageio-ffmpeg package, else whatever is on PATH."""
    exe = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    here = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__))
    spots = [os.environ.get("OPENDM_FFMPEG") or "", os.path.join(getattr(sys, "_MEIPASS", here), exe)]
    spots += [os.path.join(here, *p, exe) for p in ((), ("ffmpeg",), ("bin",))] + [os.path.join(CFG_DIR, exe)]
    for p in spots:
        if p and os.path.isdir(p):
            p = os.path.join(p, exe)
        if p and os.path.isfile(p):
            return p
    try:
        import imageio_ffmpeg
        p = imageio_ffmpeg.get_ffmpeg_exe()
        if p and os.path.isfile(p):
            return p
    except Exception:
        pass
    return shutil.which("ffmpeg")


def _ff_flags():
    return {"creationflags": 0x08000000} if os.name == "nt" else {}


def run_ff(ff, args, timeout=None):
    try:
        return subprocess.run([ff, "-y", "-loglevel", "error", *args], capture_output=True, timeout=timeout, **_ff_flags()).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def merge_streams(ff, inputs, base, maps=False):
    """Mux (video + audio) or remux (one file) with stream copy into base.mp4. If the codecs don't fit MP4 (VP9/Opus...),
    re-encode only the audio to AAC, and as a last resort write base.mkv. Returns the file written, or None."""
    ins = [x for p in inputs for x in ("-i", p)]
    mp = ["-map", "0:v:0", "-map", "1:a:0"] if maps and len(inputs) == 2 else []
    for ext, codec in ((".mp4", ["-c", "copy", "-movflags", "+faststart"]),
                       (".mp4", ["-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart"]),
                       (".mkv", ["-c", "copy"])):
        dst = base + ext
        if run_ff(ff, [*ins, *mp, *codec, dst]) and os.path.isfile(dst) and os.path.getsize(dst) > 0:
            return dst
        try:
            os.remove(dst)
        except OSError:
            pass
    return None


# ---- addresses, file names, MIME types, magic bytes
_DRIVE = re.compile(r"^https?://drive\.google\.com/(?:file/(?:u/\d+/)?d/([\w-]+)|(?:open|uc)\?(?:[^#]*&)?id=([\w-]+))", re.I)


def normalize_url(u):
    """Google Drive share links (/file/d/ID/view, open?id=ID) become direct-download links."""
    m = _DRIVE.match((u or "").strip())
    if m and "export=download" not in u:
        return "https://drive.google.com/uc?export=download&id=" + (m.group(1) or m.group(2))
    return u


def is_drive_host(host):
    host = (host or "").lower()
    return host in ("drive.google.com", "docs.google.com") or host.endswith("usercontent.google.com")


def drive_confirm_url(page, base):
    """Drive answers big files with a web page ('can't scan for viruses'); the real link is in its form."""
    f = re.search(r'<form[^>]+id="download-form"[^>]*action="([^"]+)"', page) or re.search(r'<form[^>]+action="([^"]*download[^"]*)"', page)
    if f:
        q = dict(re.findall(r'<input[^>]+type="hidden"[^>]+name="([^"]+)"[^>]+value="([^"]*)"', page))
        act = html.unescape(f.group(1))
        return act + ("&" if "?" in act else "?") + urllib.parse.urlencode({k: html.unescape(v) for k, v in q.items()})
    m = re.search(r'href="(/uc\?export=download[^"]+)"', page)
    if m:
        return urllib.parse.urljoin(base, html.unescape(m.group(1)))
    return None


def name_from_url(u):
    """File name hidden in a link: the path's last part, else ?filename=... / S3's response-content-disposition."""
    p = urllib.parse.urlparse(u)
    n = urllib.parse.unquote(os.path.basename(p.path))
    if os.path.splitext(n)[1]:
        return n
    q = urllib.parse.parse_qs(p.query)
    for v in q.get("response-content-disposition", []):
        m = Message()
        m["content-disposition"] = v
        if m.get_filename():
            return m.get_filename()
    for k in ("filename", "file", "fname", "name", "download", "title"):
        for v in q.get(k, []):
            v = os.path.basename(v.replace("\\", "/"))
            if 1 < len(os.path.splitext(v)[1]) <= 6:
                return v
    return n


CT_EXT = {
    "application/pdf": ".pdf", "application/x-pdf": ".pdf",
    "application/x-msdownload": ".exe", "application/x-dosexec": ".exe", "application/vnd.microsoft.portable-executable": ".exe",
    "application/x-msdos-program": ".exe", "application/exe": ".exe", "application/x-msi": ".msi", "application/x-ms-installer": ".msi",
    "application/zip": ".zip", "application/x-zip-compressed": ".zip", "application/x-zip": ".zip",
    "application/x-rar-compressed": ".rar", "application/vnd.rar": ".rar", "application/x-rar": ".rar", "application/x-7z-compressed": ".7z",
    "application/gzip": ".gz", "application/x-gzip": ".gz", "application/x-tar": ".tar", "application/x-bzip2": ".bz2", "application/x-xz": ".xz",
    "audio/mpeg": ".mp3", "audio/mp3": ".mp3", "audio/mp4": ".m4a", "audio/x-m4a": ".m4a", "audio/aac": ".aac", "audio/wav": ".wav",
    "audio/x-wav": ".wav", "audio/wave": ".wav", "audio/ogg": ".ogg", "audio/flac": ".flac", "audio/x-flac": ".flac", "audio/opus": ".opus",
    "video/mp4": ".mp4", "video/webm": ".webm", "video/x-matroska": ".mkv", "video/quicktime": ".mov", "video/x-msvideo": ".avi",
    "video/mpeg": ".mpg", "video/x-flv": ".flv", "video/3gpp": ".3gp", "video/mp2t": ".ts",
    "application/vnd.android.package-archive": ".apk", "application/x-apple-diskimage": ".dmg", "application/x-iso9660-image": ".iso",
    "application/x-debian-package": ".deb", "application/x-rpm": ".rpm", "application/epub+zip": ".epub",
    "application/msword": ".doc", "application/vnd.ms-excel": ".xls", "application/vnd.ms-powerpoint": ".ppt",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
    "application/rtf": ".rtf", "application/json": ".json", "text/plain": ".txt", "text/csv": ".csv", "text/html": ".html", "application/xhtml+xml": ".html",
    "image/jpeg": ".jpg", "image/png": ".png", "image/gif": ".gif", "image/webp": ".webp", "image/svg+xml": ".svg", "image/bmp": ".bmp",
    "image/tiff": ".tif", "image/heic": ".heic", "image/avif": ".avif", "image/x-icon": ".ico", "image/vnd.microsoft.icon": ".ico",
}
GENERIC_CT = {"", "application/octet-stream", "binary/octet-stream", "application/force-download", "application/x-download",
              "application/download", "application/unknown", "application/x-unknown", "application/save", "application/x-www-form-urlencoded"}
DYNAMIC_EXT = {".php", ".php3", ".php4", ".asp", ".aspx", ".ashx", ".axd", ".jsp", ".jspx", ".cgi", ".pl", ".do", ".action"}  # scripts that hand out files
BINARY_EXT = {e for c in DEFAULT_CATEGORIES for e in c["exts"]} - {"txt", "csv", "sh", "bat", "svg"}  # a name like this must not turn out to be a web page


def magic_ext(head):
    """Extension from the first bytes of a file ('ole' for old Office/MSI containers, '' when unknown)."""
    h = head or b""
    if h.startswith(b"%PDF-"):
        return ".pdf"
    if h.startswith((b"PK\x03\x04", b"PK\x05\x06")):
        return ".zip"
    if h.startswith(b"Rar!\x1a\x07"):
        return ".rar"
    if h.startswith(b"7z\xbc\xaf\x27\x1c"):
        return ".7z"
    if h.startswith(b"\x1f\x8b\x08"):
        return ".gz"
    if h.startswith(b"BZh") and h[4:10] == b"1AY&SY":
        return ".bz2"
    if h.startswith(b"\xfd7zXZ\x00"):
        return ".xz"
    if h[257:262] == b"ustar":
        return ".tar"
    if h.startswith(b"MZ") and len(h) >= 0x40:
        pe = int.from_bytes(h[0x3C:0x40], "little")
        if (pe + 4 <= len(h) and h[pe:pe + 4] == b"PE\0\0") or (pe + 4 > len(h) and pe < 4096):
            return ".exe"
    if h.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        return "ole"
    if h.startswith(b"ID3"):
        return ".mp3"
    if len(h) >= 3 and h[0] == 0xFF and h[1] in (0xFB, 0xF3, 0xF2) and (h[2] >> 4) not in (0, 15) and ((h[2] >> 2) & 3) != 3:
        return ".mp3"
    if h.startswith(b"fLaC"):
        return ".flac"
    if h.startswith(b"OggS"):
        return ".ogg"
    if h[:4] == b"RIFF" and h[8:12] == b"WAVE":
        return ".wav"
    if h[:4] == b"RIFF" and h[8:12] == b"AVI ":
        return ".avi"
    if h[:4] == b"RIFF" and h[8:12] == b"WEBP":
        return ".webp"
    if h[4:8] == b"ftyp":
        brand = h[8:12]
        return ".m4a" if brand in (b"M4A ", b"M4B ") else ".mov" if brand == b"qt  " else ".mp4"
    if h.startswith(b"\x1aE\xdf\xa3"):
        return ".webm" if b"webm" in h[:64] else ".mkv"
    if h.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if h.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if h.startswith((b"GIF87a", b"GIF89a")):
        return ".gif"
    if h.startswith(b"{\\rtf"):
        return ".rtf"
    return ""


def sniff_ext(head, ct="", where=""):
    """Best extension from Content-Type and the file's first bytes ('' if neither says)."""
    base = (ct or "").split(";")[0].strip().lower()
    byct = CT_EXT.get(base)
    if byct is None and base and base not in GENERIC_CT and not base.startswith("text/"):
        g = mimetypes.guess_extension(base)
        byct = {".jpe": ".jpg", ".jpeg": ".jpg", ".htm": ".html"}.get(g, g)
    if byct and byct not in (".txt", ".html"):
        return byct
    m = magic_ext(head)
    if m == "ole":  # old Office files and MSI installers share one container: only the name or type can tell
        return ".msi" if re.search(r"(?i)(^|[^a-z])msi([^a-z]|$)", where or "") else ""
    return m or byct or ""


def fix_name(name, ct="", head=b"", where=""):
    """Give a file a proper extension when the server's name has none (or a script's: download.php): '12345' -> '12345.pdf'."""
    stem, ext = os.path.splitext(name)
    e = ext.lower()
    if e and e not in DYNAMIC_EXT:
        return name
    guess = sniff_ext(head, ct, where)
    if not guess:
        return name
    return (stem if e else name) + guess


def looks_like_page(head, ct=""):
    """True when the bytes are a web page (an error / login / expired-link page) rather than a file."""
    if magic_ext(head):
        return False
    h = (head or b"").lstrip()[:20].lower()
    return h.startswith((b"<!doctype html", b"<html", b"<head", b"<body")) or (ct or "").split(";")[0].strip().lower() in ("text/html", "application/xhtml+xml")


# ---- yt-dlp (optional): finds the real streams behind YouTube, Facebook, Instagram, Vimeo, TikTok ...
YT_MISSING = "yt-dlp is not installed - run:  pip install yt-dlp   (needed for YouTube, Facebook, Instagram and other video sites)"
MEDIA_HOSTS = ("youtube.com", "youtu.be", "youtube-nocookie.com", "facebook.com", "fb.watch", "instagram.com", "vimeo.com", "dailymotion.com",
               "twitter.com", "x.com", "tiktok.com", "twitch.tv", "reddit.com", "v.redd.it", "soundcloud.com", "bilibili.com", "streamable.com",
               "rumble.com", "ok.ru", "vk.com", "bandcamp.com", "odysee.com")
_IES = {}


def _ytdlp():
    for n in ("stdout", "stderr"):  # a --noconsole / --windowed build has no stdout or stderr, and yt-dlp writes to them
        if getattr(sys, n, None) is None:
            setattr(sys, n, open(os.devnull, "w"))
    try:
        import yt_dlp
        return yt_dlp
    except ImportError:
        return None


def media_site(url):
    """True for video/audio pages that need yt-dlp to find the actual file (never for direct file links)."""
    p = urllib.parse.urlparse(url or "")
    host = (p.hostname or "").lower()
    if p.scheme not in ("http", "https") or not host or is_drive_host(host):
        return False
    if os.path.splitext(p.path)[1].lower().lstrip(".") in BINARY_EXT:
        return False
    if any(host == h or host.endswith("." + h) for h in MEDIA_HOSTS):
        return True
    y = _ytdlp()
    if y is None:
        return False
    try:  # yt-dlp's own site list: a local pattern match, no network
        if "ies" not in _IES:
            _IES["ies"] = [ie for ie in y.extractor.gen_extractor_classes() if not str(getattr(ie, "IE_NAME", "")).lower().startswith(("generic", "googledrive"))]
        return any(ie.suitable(url) for ie in _IES["ies"])
    except Exception:
        return False


def detect_kind(url):
    """Which engine a link needs: 'hls' (.m3u8), 'dash' (.mpd), 'ytdlp' (video sites), or None (plain file)."""
    low = (url or "").lower()
    if ".m3u8" in low:
        return "hls"
    if urllib.parse.urlparse(low).path.endswith(".mpd"):
        return "dash"
    return "ytdlp" if media_site(url) else None


def apply_cookies(ydl, cookie, url):
    """FIX: hand the browser's cookies to yt-dlp through its cookiejar, scoped to the page's domain, instead of a raw
    'Cookie' header (yt-dlp does not reliably forward that header, which broke logged-in / private Facebook videos)."""
    jar = getattr(ydl, "cookiejar", None)
    if not cookie or jar is None:
        return
    import http.cookiejar as cj
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    if not host:
        return
    dom = "." + (host[4:] if host.startswith("www.") else host)
    for part in str(cookie).split(";"):
        name, eq, value = part.strip().partition("=")
        if not eq or not name:
            continue
        jar.set_cookie(cj.Cookie(0, name, value, None, False, dom, True, True, "/", True, True, None, True, None, None, {}))


def ytdlp_opts(quality=0, referer=None, cookie=None, ua=None):
    """Options shared by every yt-dlp call. FIX: separate best video + best audio, always merged by ffmpeg into one .mp4,
    so DASH sites (Facebook / Instagram / Reels) never end up silent. Cookies are applied with apply_cookies()."""
    q = int(quality or 0)
    h = f"[height<={q}]" if q > 0 else ""
    o = {"quiet": True, "no_warnings": True, "noplaylist": True, "socket_timeout": 30, "retries": 5,
         "merge_output_format": "mp4",
         "format": "ba[ext=m4a]/ba/b" if q < 0 else f"bv*{h}[ext=mp4]+ba[ext=m4a]/bv*{h}+ba/b{h}/b"}  # quality -1 = audio only
    ff = find_ffmpeg()
    if ff:
        o["ffmpeg_location"] = ff
    hdr = {k: v for k, v in (("User-Agent", ua), ("Referer", referer)) if v}
    if hdr:
        o["http_headers"] = hdr
    return o


def summarize_formats(info):
    """What the browser's 'Download this video' menu shows: one entry per resolution (video + the best audio, sizes added up) and an audio-only entry."""
    dur = float(info.get("duration") or 0)

    def size(f):
        n = f.get("filesize") or 0
        if n:
            return int(n), False
        n = f.get("filesize_approx") or 0
        if n:
            return int(n), True
        tbr = f.get("tbr") or ((f.get("vbr") or 0) + (f.get("abr") or 0))
        return (int(tbr * 1000 / 8 * dur), True) if tbr and dur else (0, True)
    fl = [f for f in (info.get("formats") or [info]) if isinstance(f, dict) and f.get("ext") != "mhtml"
          and (f.get("protocol") or "") != "mhtml" and f.get("format_note") != "storyboard"]
    video = [f for f in fl if (f.get("height") or 0) > 0 and f.get("vcodec") != "none"]
    audio = [f for f in fl if f.get("vcodec") == "none" and f.get("acodec") not in (None, "none")]
    a = max(audio, key=lambda f: (f.get("ext") == "m4a", f.get("abr") or 0, size(f)[0]), default=None)
    asz, aap = size(a) if a else (0, False)
    best = {}
    for f in video:
        key = (bool(f.get("filesize") or f.get("filesize_approx")), f.get("ext") == "mp4", f.get("tbr") or 0)
        h = int(f["height"])
        if h not in best or key > best[h][0]:
            best[h] = (key, f)
    out = []
    for h in sorted(best, reverse=True):
        f = best[h][1]
        sz, ap = size(f)
        mux = f.get("acodec") in (None, "none")  # picture only: the audio is fetched separately and merged
        out.append({"height": h, "fps": int(f.get("fps") or 0), "ext": "mp4" if mux else (f.get("ext") or "mp4"),
                    "size": sz + (asz if mux else 0), "approx": bool(ap or (mux and aap))})
    return {"title": str(info.get("title") or ""), "duration": dur, "formats": out,
            "audio": {"ext": a.get("ext") or "m4a", "size": asz, "approx": aap} if a else None}


def ytdlp_formats(url, referer=None, cookie=None, ua=None):
    y = _ytdlp()
    if y is None:
        raise IOError(YT_MISSING)
    opts = dict(ytdlp_opts(0, referer, cookie, ua), skip_download=True)
    opts.pop("format")
    with y.YoutubeDL(opts) as ydl:
        apply_cookies(ydl, cookie, url)  # FIX: cookies via cookiejar
        info = ydl.extract_info(url, download=False)
    if info and info.get("entries"):
        info = next((e for e in info["entries"] if e), None)
    if not info:
        raise IOError("yt-dlp found no video at this address")
    return summarize_formats(info)


def ytdlp_resolve(url, quality=0, referer=None, cookie=None, ua=None):
    """Ask yt-dlp for the best stream(s). Returns {kind: direct|mux|hls|native, url, audio, name, title, referer, ua}."""
    y = _ytdlp()
    if y is None:
        raise IOError(YT_MISSING)
    with y.YoutubeDL(dict(ytdlp_opts(quality, referer, cookie, ua), skip_download=True)) as ydl:
        apply_cookies(ydl, cookie, url)  # FIX: cookies via cookiejar
        info = ydl.extract_info(url, download=False)
    if info and info.get("entries"):  # a playlist link: take its first video
        info = next((e for e in info["entries"] if e), None)
    if not info:
        raise IOError("yt-dlp found no downloadable media at this address")
    fmts = info.get("requested_formats") or [info]
    kinds = ["http" if (f.get("protocol") or "https").lower() in ("http", "https") else "hls" if (f.get("protocol") or "").lower().startswith("m3u8") else "other" for f in fmts]
    title = clean_name(str(info.get("title") or info.get("id") or "video"))[:150]
    hdr = fmts[0].get("http_headers") or info.get("http_headers") or {}
    plan = {"title": title, "referer": hdr.get("Referer") or referer, "ua": hdr.get("User-Agent") or ua, "url": "", "audio": "",
            "kind": "native", "name": title + ".mp4"}
    if len(fmts) == 1 and kinds[0] == "http" and fmts[0].get("url"):
        plan.update(kind="direct", url=fmts[0]["url"], name=f"{title}.{fmts[0].get('ext') or 'mp4'}")
    elif len(fmts) == 2 and kinds == ["http", "http"] and all(f.get("url") for f in fmts):
        v = next((f for f in fmts if f.get("vcodec") not in (None, "none")), fmts[0])
        a = next(f for f in fmts if f is not v)
        plan.update(kind="mux", url=v["url"], audio=a["url"])
    elif len(fmts) == 1 and kinds[0] == "hls" and fmts[0].get("url"):
        plan.update(kind="hls", url=fmts[0]["url"])
    return plan


class Download:
    def __init__(self, url, folder, connections=8, referer=None, cookie=None, ua=None, hint=None):
        self.url, self.folder, self.connections = normalize_url(url), folder, connections
        self.referer, self.cookie, self.ua, self.hint = referer, cookie, ua, hint  # cookie is never saved to disk
        self.name = self.path = None
        self.size, self.ranges = -1, False
        self.segs = []  # each: [start, end_or_None, next_byte_pos]
        self.status, self.error = "Queued", ""
        self.speed, self._last = 0.0, (time.time(), 0)
        self.lock = threading.Lock()
        self.limit_kb, self.limiter = 0, Limiter()
        self.hist = deque(maxlen=HIST)  # one speed sample per second, for the graph
        self.base, self.category, self.auto_cat, self.router = folder, "General", True, None  # router: set by the Manager
        self.queue, self.project, self.desc, self.last_try = MAIN_QUEUE, "", "", time.time()
        self.force = self.auto_paused = False  # runtime only
        self.show_complete, self.open_when_done, self.announced = None, False, False  # runtime only; show_complete None = follow the global setting
        self.restart, self.downgraded, self.note = threading.Event(), False, ""  # restart: ask the workers to stop so the transfer can start again as one plain stream
        self.stop = threading.Event()
        self.failed = threading.Event()
        self.thread = None

    # ---------- persistence ----------
    def to_dict(self):
        keys = ("url", "folder", "base", "category", "auto_cat", "queue", "project", "desc", "last_try", "connections", "limit_kb", "referer", "ua", "hint", "name", "path", "size", "ranges", "segs", "status", "error")
        d = {k: getattr(self, k) for k in keys}
        d["segs"] = [list(s) for s in self.segs]
        return d

    @classmethod
    def from_dict(cls, d):
        cls = {"hls": HlsDownload, "mux": MuxDownload, "dash": DashDownload, "ytdlp": ExtractDownload, "ytnative": NativeYt}.get(d.get("kind"), cls)
        o = cls(d["url"], d["folder"], d.get("connections", 8))
        for k, v in d.items():
            setattr(o, k, v)
        o.limiter.set_rate(o.limit_kb * 1024)
        if o.status in ACTIVE or o.status == "Queued":
            o.status = "Paused"
        getattr(o, "_loaded", lambda: None)()
        o._last = (time.time(), o.done)  # otherwise the first speed reading after a restart is a huge spike
        return o

    # ---------- helpers ----------
    @property
    def done(self):
        return sum((min(s[2], s[1] + 1) if s[1] is not None else s[2]) - s[0] for s in list(self.segs))

    @property
    def percent(self):
        return 100.0 * self.done / self.size if self.size > 0 else 0.0

    def _open(self, headers=None, url=None):
        url = url or self.url
        h = {"User-Agent": self.ua or UA}
        if self.referer:
            h["Referer"] = self.referer
        if self.cookie and urllib.parse.urlparse(url).netloc == urllib.parse.urlparse(self.url).netloc:
            h["Cookie"] = self.cookie  # only ever sent to the host the browser gave us
        req = urllib.request.Request(url, headers={**h, **(headers or {})})
        return OPENER.open(req, timeout=30)

    def _fetch_head(self):
        """First KB of the file (ranged; plain GET if the server rejects Range). A web page is read further, for Google Drive's confirm form."""
        err = None
        for attempt in range(2):
            for rng in (True, False):
                try:
                    with self._open({"Range": "bytes=0-1023"} if rng else None) as r:
                        n = 1 << 19 if "text/html" in (r.headers.get("Content-Type") or "").lower() else 1024
                        return r.status, r.headers, r.geturl(), r.read(n)
                except urllib.error.HTTPError as e:
                    if rng and e.code in (400, 403, 405, 416, 501):
                        err = e
                        continue  # some servers reject Range outright: ask again without it
                    raise
                except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                    err = e
                    break
            time.sleep(1.0)
        raise err

    def _probe(self):
        """Learn size, range support and the real file name: Content-Disposition, redirects, the link itself, then Content-Type and magic bytes."""
        status, hdrs, final, head = self._fetch_head()
        ct = (hdrs.get("Content-Type") or "").split(";")[0].strip().lower()
        if ct == "text/html" and is_drive_host(urllib.parse.urlparse(final).hostname):
            nxt = drive_confirm_url(head.decode("utf-8", "replace"), final)
            if nxt and nxt != self.url:
                self.url = nxt  # Google Drive's "can't scan this file for viruses" step
                status, hdrs, final, head = self._fetch_head()
                ct = (hdrs.get("Content-Type") or "").split(";")[0].strip().lower()
            if ct == "text/html":
                raise IOError("Google Drive refused the download (private file, or its download quota is used up)")
        cr = hdrs.get("Content-Range")
        if status == 206 and cr and cr.split("/")[-1].isdigit():
            self.size, self.ranges = int(cr.split("/")[-1]), True
        else:
            cl = hdrs.get("Content-Length")
            self.size, self.ranges = (int(cl) if cl and cl.isdigit() else -1), False
        name, cd = None, hdrs.get("Content-Disposition")
        if cd:
            m = Message()
            m["content-disposition"] = cd
            name = m.get_filename()
        raw = clean_name(self.hint or name or name_from_url(final) or name_from_url(self.url))
        if os.path.splitext(raw)[1].lower().lstrip(".") in BINARY_EXT and looks_like_page(head, ct):
            raise IOError("the server sent a web page instead of the file (the link may have expired, or it needs a login)")
        self.name = clean_name(fix_name(raw, ct, head, f"{self.url} {self.hint or ''}"))

    def _route(self):
        """Pick the category folder now that the real file name is known."""
        if self.router:
            self.router(self)

    def _plan(self):
        self._route()
        os.makedirs(self.folder, exist_ok=True)
        base, ext = os.path.splitext(self.name)
        path, i = os.path.join(self.folder, self.name), 1
        while os.path.exists(path):
            path = os.path.join(self.folder, f"{base} ({i}){ext}")
            i += 1
        self.path = path
        if self.ranges and self.size > 2 * 1024 * 1024:
            n = max(1, self.connections)
            step = -(-self.size // n)
            self.segs = [[i * step, min((i + 1) * step, self.size) - 1, i * step]
                         for i in range(n) if i * step < self.size]
        else:
            self.segs = [[0, self.size - 1 if self.size > 0 else None, 0]]
        with open(self.path, "wb") as f:
            if self.size > 0:
                f.truncate(self.size)

    def segment_map(self):
        """[(x0, x1, filled_to)] in 0..1: the byte range of every connection's segment and how far it got."""
        if self.size <= 0 or not self.segs:
            return []
        n, out = float(self.size), []
        for x in sorted(list(self.segs), key=lambda z: z[0]):
            end = x[1] if x[1] is not None else self.size - 1
            out.append((x[0] / n, (end + 1) / n, min(max(x[2], x[0]), end + 1) / n))
        return out

    def segment_rows(self):
        """[(n, 'downloaded', 'info')] - one row per connection, for the progress window's N. / Downloaded / Info table."""
        rows, live = [], self.status in ACTIVE
        for i, x in enumerate(sorted(list(self.segs), key=lambda z: z[0]), 1):
            end = x[1]
            got = max(0, (min(x[2], end + 1) if end is not None else x[2]) - x[0])
            if (end is not None and x[2] > end) or self.status == "Completed":
                info = "Complete"
            elif live:
                info = "Receiving data..." if self.status == "Downloading" else "Connecting..."
            else:
                info = "Stopped"
            rows.append((i, human(got), info))
        return rows

    def set_limit(self, kb):
        self.limit_kb = max(0, int(kb))
        self.limiter.set_rate(self.limit_kb * 1024)

    # ---------- control ----------
    def start(self):
        if self.status in ACTIVE:
            return
        self.stop.clear()
        self.failed.clear()
        self.error = ""
        self.last_try = time.time()
        self.status = "Connecting"
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def pause(self):
        self.stop.set()

    def _run(self):
        try:
            if not self.segs:
                self._probe()
                self._plan()
            elif not self.ranges:  # server can't resume: restart from zero
                for x in self.segs:
                    x[2] = x[0]
                open(self.path, "wb").close()
            if not os.path.exists(self.path):
                raise IOError("partial file missing")
            self.status = "Downloading"
            self._last = (time.time(), self.done)
            while True:
                self.restart.clear()
                todo = [x for x in self.segs if x[1] is None or x[2] <= x[1]]
                workers = [threading.Thread(target=self._worker, args=(x,), daemon=True) for x in todo]
                if self.ranges:  # spare connections start idle and steal work from busy ones
                    workers += [threading.Thread(target=self._worker, daemon=True)
                                for _ in range(max(0, self.connections - len(todo)))]
                for w in workers:
                    w.start()
                for w in workers:
                    w.join()
                if self.restart.is_set() and not self.stop.is_set():
                    self._single_stream()  # the server won't do parallel / ranged transfers: carry on as one plain stream
                    continue
                break
            if self.failed.is_set():
                self.status = "Error"
            elif all(x[1] is not None and x[2] > x[1] for x in self.segs):
                if os.path.getsize(self.path) == 0:
                    self.error, self.status = "the server returned an empty file", "Error"
                else:
                    self.status = "Completed"
            else:
                self.status = "Paused"
        except Exception as e:
            self.error, self.status = str(e), "Error"
        if self.status == "Error" and self.path and self.done == 0:
            self._scrap()
        self.speed = 0

    def _halted(self):
        return self.stop.is_set() or self.failed.is_set() or self.restart.is_set()

    def _downgrade(self, why):
        """Ranged / multi-connection transfer is not working: ask every worker to stop so the file restarts as one plain stream."""
        if self.downgraded or not self.ranges:
            return False
        self.note = "single connection (" + why[:40] + ")"
        self.restart.set()
        return True

    def _single_stream(self):
        self.ranges, self.connections, self.downgraded = False, 1, True
        self.segs = [[0, self.size - 1 if self.size > 0 else None, 0]]
        with open(self.path, "wb") as f:
            if self.size > 0:
                f.truncate(self.size)

    def _scrap(self):
        """Nothing was received: don't leave a zero-filled placeholder behind. The next try plans from scratch."""
        try:
            os.remove(self.path)
        except OSError:
            pass
        self.path, self.segs = None, []

    def _steal(self):
        """Split the largest unfinished segment in two and return the new second half."""
        if not self.ranges:
            return None
        with self.lock:
            best, rem = None, 0
            for x in self.segs:
                if x[1] is not None and x[1] - x[2] + 1 > rem:
                    best, rem = x, x[1] - x[2] + 1
            if best is None or rem < MIN_SPLIT:
                return None
            mid = best[2] + rem // 2
            new = [mid, best[1], mid]
            best[1] = mid - 1  # the victim notices this before its next read
            self.segs.append(new)
            return new

    def _worker(self, seg=None):
        while not self._halted():
            if seg is None or (seg[1] is not None and seg[2] > seg[1]):
                seg = self._steal()
                if seg is None:
                    return
            self._fetch(seg)
            if seg[1] is None:
                return

    def _fetch(self, seg):
        tries = 0
        while not self._halted():
            end = seg[1]
            if end is not None and seg[2] > end:
                return
            try:
                hdr = {}
                if self.ranges:
                    hdr["Range"] = f"bytes={seg[2]}-{'' if end is None else end}"
                with self._open(hdr) as r, open(self.path, "r+b") as f:
                    if self.ranges and r.status != 206:
                        if self._downgrade("server ignored Range"):
                            return
                        raise IOError("server ignored Range request")
                    f.seek(seg[2])
                    while not self._halted():
                        end = seg[1]  # may shrink when another connection steals our tail
                        ck = _chunk_for(GLOBAL_LIMIT, self.limiter)
                        want = ck if end is None else min(ck, end - seg[2] + 1)
                        if want <= 0:
                            return
                        buf = r.read(want)
                        if not buf:
                            if end is None:  # unknown length: EOF means finished
                                seg[1] = seg[2] - 1
                                return
                            raise IOError("connection closed early")
                        f.write(buf)
                        seg[2] += len(buf)
                        tries = 0
                        GLOBAL_LIMIT.wait(len(buf), self.stop)
                        self.limiter.wait(len(buf), self.stop)
            except Exception as e:
                code = getattr(e, "code", None)
                if self.ranges and code in (400, 403, 405, 416, 429, 501) and self._downgrade(f"HTTP {code}"):
                    return
                tries = 99 if code in (401, 403, 404, 410) else tries + 1  # permanent refusals aren't worth retrying
                if tries > 6:
                    if self._downgrade(str(e)):
                        return
                    self.error = str(e)
                    self.failed.set()
                    return
                if not self.ranges:
                    seg[2] = seg[0]  # a plain stream can't resume mid-file: begin again
                time.sleep(min(2 * tries, 15))

    def update_speed(self):
        now, d = time.time(), self.done
        t0, d0 = self._last
        if now - t0 >= 1:
            self.speed = max(0, (d - d0) / (now - t0))
            self._last = (now, d)
            self.hist.append(self.speed)

    @property
    def label(self):
        """What the File Name column shows: the real name once known, else a guess from the address (like IDM)."""
        if self.name:
            return self.name
        guess = self.hint or urllib.parse.unquote(os.path.basename(urllib.parse.urlparse(self.url).path))
        return clean_name(guess) if guess else self.url

    @property
    def eta_sec(self):
        if self.status != "Downloading" or self.speed <= 0 or self.size <= 0:
            return None
        return max(0.0, (self.size - self.done) / self.speed)

    @property
    def eta(self):
        if self.status != "Downloading" or self.speed <= 0 or self.size <= 0:
            return ""
        s = int((self.size - self.done) / self.speed)
        return f"{s // 3600:d}:{s % 3600 // 60:02d}:{s % 60:02d}"


# ============================ HLS video downloads ============================
class Fatal(Exception):
    """An error that retrying cannot fix."""


def parse_attrs(s):
    return {k: v.strip('"') for k, v in re.findall(r'([A-Z0-9-]+)=("[^"]*"|[^,]*)', s)}


def aes_decrypt(data, key, iv):
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        dec = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
        out = dec.update(data) + dec.finalize()
    except ImportError:
        try:
            from Crypto.Cipher import AES
            out = AES.new(key, AES.MODE_CBC, iv).decrypt(data)
        except ImportError:
            raise Fatal("This stream is AES-encrypted. Install a decryption library:  pip install cryptography")
    pad = out[-1] if out else 0
    return out[:-pad] if 1 <= pad <= 16 and out.endswith(bytes([pad]) * pad) else out


class HlsDownload(Download):
    """HLS (.m3u8) on-demand streams: parallel segments, AES-128, resume, ffmpeg mux/remux if installed.
    Live streams and DRM (SAMPLE-AES, Widevine, FairPlay) are not supported."""
    kind = "hls"

    def __init__(self, url, folder, connections=8, quality=0, pick_bw=0, **kw):
        super().__init__(url, folder, connections, **kw)
        self.pick_bw = pick_bw  # exact variant bitrate chosen in the browser (0 = just use the height cap)
        self.quality, self.total, self.segs_done, self.bytes_done, self.note = quality, 0, 0, 0, ""
        self.plan, self._keys = None, {}
        self.flags, self._off = bytearray(), {}  # one byte per segment: 1 = downloaded (for the segment map)

    def to_dict(self):
        d = super().to_dict()
        d.update(kind="hls", quality=self.quality, pick_bw=self.pick_bw, total=self.total, segs_done=self.segs_done,
                 bytes_done=self.bytes_done, note=self.note)
        return d

    @property
    def done(self):
        return self.bytes_done

    @property
    def percent(self):
        return 100.0 * self.segs_done / self.total if self.total else 0.0

    def discard(self):
        if self.path:
            shutil.rmtree(self.path + ".parts", ignore_errors=True)

    def segment_map(self):
        f, out, i = self.flags, [], 0
        n = len(f)
        while i < n:
            j = i
            while j < n and f[j] == f[i]:
                j += 1
            out.append((i / n, j / n, j / n if f[i] else i / n))
            i = j
        return out

    def segment_rows(self):
        if self.status == "Completed":
            info = "Complete"
        elif self.status in ACTIVE:
            info = f"{self.segs_done}/{self.total} parts"
        else:
            info = f"Stopped ({self.segs_done}/{self.total} parts)"
        return [(1, human(self.bytes_done), info)]

    def _open(self, headers=None, url=None):
        h = dict(headers or {})
        if self.referer:
            p = urllib.parse.urlparse(self.referer)
            h.setdefault("Origin", f"{p.scheme}://{p.netloc}")
        return super()._open(h, url)

    # ---------- playlist parsing ----------
    def _text(self, url):
        with self._open(url=url) as r:
            return r.read(8 << 20).decode("utf-8", "replace"), r.geturl()

    def _choose(self, text, base):
        """Master playlist -> (video playlist url, separate audio playlist url or None)."""
        lines, variants, audio = text.splitlines(), [], []
        for i, l in enumerate(lines):
            if l.startswith("#EXT-X-STREAM-INF:"):
                a = parse_attrs(l.split(":", 1)[1])
                uri = next((x for x in lines[i + 1:] if x.strip() and not x.startswith("#")), None)
                if uri:
                    res = a.get("RESOLUTION", "")
                    variants.append({"bw": int(a.get("BANDWIDTH", 0) or 0), "aud": a.get("AUDIO"),
                                     "h": int(res.split("x")[1]) if "x" in res else 0,
                                     "u": urllib.parse.urljoin(base, uri.strip())})
            elif l.startswith("#EXT-X-MEDIA:"):
                a = parse_attrs(l.split(":", 1)[1])
                if a.get("TYPE") == "AUDIO" and a.get("URI"):
                    audio.append(dict(a, URI=urllib.parse.urljoin(base, a["URI"])))
        if not variants:
            raise Fatal("No playable variants in the playlist")
        q = self.quality
        pool = [v for v in variants if q <= 0 or 0 < v["h"] <= q]
        if not pool:
            pool = [min(variants, key=lambda v: (v["h"], v["bw"]))]
        best = max(pool, key=lambda v: (v["h"], v["bw"]))
        exact = [v for v in pool if self.pick_bw and v["bw"] == self.pick_bw]
        if exact:  # the user picked this exact rendition in the browser
            best = max(exact, key=lambda v: v["h"])
        aud = None
        if best["aud"]:
            grp = [a for a in audio if a.get("GROUP-ID") == best["aud"]]
            if grp:
                aud = next((a for a in grp if a.get("DEFAULT") == "YES"), grp[0])["URI"]
        return best["u"], aud

    @staticmethod
    def _br(spec, url, last_end):
        if not spec:
            return None
        n, _, o = spec.partition("@")
        start = int(o) if o else last_end.get(url, 0)
        last_end[url] = start + int(n)
        return f"{int(n)}@{start}"

    def _parse_media(self, text, base):
        if "#EXT-X-ENDLIST" not in text:
            raise Fatal("Live streams are not supported")
        m = re.search(r"#EXT-X-MEDIA-SEQUENCE:(\d+)", text)
        seq, key, parts, last_end, pending = (int(m.group(1)) if m else 0), None, [], {}, None
        for l in (x.strip() for x in text.splitlines()):
            if l.startswith("#EXT-X-KEY:"):
                a = parse_attrs(l.split(":", 1)[1])
                meth = a.get("METHOD", "NONE")
                if meth == "NONE":
                    key = None
                elif meth == "AES-128" and a.get("URI"):
                    key = {"u": urllib.parse.urljoin(base, a["URI"]), "iv": a.get("IV")}
                else:
                    raise Fatal(f"Unsupported encryption ({meth}). DRM-protected streams can't be downloaded")
            elif l.startswith("#EXT-X-MAP:"):
                a = parse_attrs(l.split(":", 1)[1])
                u = urllib.parse.urljoin(base, a["URI"])
                parts.append({"u": u, "br": self._br(a.get("BYTERANGE"), u, last_end), "key": None, "init": True})
            elif l.startswith("#EXT-X-BYTERANGE:"):
                pending = l.split(":", 1)[1]
            elif l and not l.startswith("#"):
                u = urllib.parse.urljoin(base, l)
                parts.append({"u": u, "br": self._br(pending, u, last_end), "key": key, "seq": seq})
                seq, pending = seq + 1, None
        if not parts:
            raise Fatal("The playlist has no segments")
        return parts

    def _plan_hls(self):
        text, base = self._text(self.url)
        sources = [("v", text, base)]
        if "#EXT-X-STREAM-INF" in text:
            vu, au = self._choose(text, base)
            sources = [("v",) + self._text(vu)]
            if au:
                sources.append(("a",) + self._text(au))
        tracks = [{"name": n, "parts": self._parse_media(t, b)} for n, t, b in sources]
        ext = ".mp4" if any(p.get("init") for p in tracks[0]["parts"]) else ".ts"
        stem = self.hint or urllib.parse.unquote(os.path.basename(urllib.parse.urlparse(self.url).path))
        stem = clean_name(re.sub(r"\.(m3u8?|mp4|ts|mkv|webm)$", "", stem, flags=re.I))
        if stem.lower() in ("index", "playlist", "master", "manifest", "chunklist", "download"):
            stem = clean_name(urllib.parse.urlparse(self.url).netloc + " video")
        self.name = stem + ext
        self._route()
        os.makedirs(self.folder, exist_ok=True)
        n, name = 0, stem
        while any(os.path.exists(os.path.join(self.folder, name + e)) for e in (ext, ".mp4", ext + ".parts")):
            n += 1
            name = f"{stem} ({n})"
        self.name, self.path = name + ext, os.path.join(self.folder, name + ext)
        os.makedirs(self.path + ".parts", exist_ok=True)
        self.plan = {"tracks": tracks}
        with open(os.path.join(self.path + ".parts", "plan.json"), "w") as f:
            json.dump(self.plan, f)

    def _fn(self, track, i):
        return os.path.join(self.path + ".parts", f"{track['name']}_{i:06d}.part")

    # ---------- downloading ----------
    def _get(self, url, br=None):
        hdr = {}
        if br:
            n, _, o = br.partition("@")
            hdr["Range"] = f"bytes={int(o)}-{int(o) + int(n) - 1}"
        chunks = []
        with self._open(hdr, url) as r:
            while not self.stop.is_set():
                b = r.read(_chunk_for(GLOBAL_LIMIT, self.limiter))
                if not b:
                    return b"".join(chunks)
                chunks.append(b)
                with self.lock:
                    self.bytes_done += len(b)
                GLOBAL_LIMIT.wait(len(b), self.stop)
                self.limiter.wait(len(b), self.stop)
        return None  # stopped

    def _key(self, url):
        with self.lock:
            k = self._keys.get(url)
        if k is None:
            k = self._get(url)
            if k is None:
                return None
            if len(k) != 16:
                raise Fatal("The encryption key could not be fetched (login or referer required?)")
            with self.lock:
                self._keys[url] = k
        return k

    def _hls_worker(self, todo):
        while not self.stop.is_set() and not self.failed.is_set():
            with self.lock:
                job = next(todo, None)
            if job is None:
                return
            t, i = job
            p, fn = t["parts"][i], self._fn(t, i)
            for attempt in range(4):
                try:
                    data = self._get(p["u"], p.get("br"))
                    if data is None:
                        return
                    if p.get("key"):
                        kb = self._key(p["key"]["u"])
                        if kb is None:
                            return
                        iv = int(p["key"]["iv"], 16).to_bytes(16, "big") if p["key"].get("iv") else p["seq"].to_bytes(16, "big")
                        data = aes_decrypt(data, kb, iv)
                    with open(fn + ".tmp", "wb") as f:
                        f.write(data)
                    os.replace(fn + ".tmp", fn)
                    with self.lock:
                        self.segs_done += 1
                        self.flags[self._off[t["name"]] + i] = 1
                        self.size = int(self.bytes_done / self.segs_done * self.total)
                    break
                except Fatal as e:
                    self.error = str(e)
                    self.failed.set()
                    return
                except Exception as e:
                    if attempt == 3:
                        self.error = f"segment {i + 1}: {e}"
                        self.failed.set()
                        return
                    if self.stop.wait(1 + attempt * 2):
                        return

    def _run(self):
        try:
            pf = os.path.join(self.path + ".parts", "plan.json") if self.path else None
            if pf and os.path.exists(pf):
                with open(pf) as f:
                    self.plan = json.load(f)
            else:
                self._plan_hls()
            tracks = self.plan["tracks"]
            self.total = sum(len(t["parts"]) for t in tracks)
            self.segs_done = self.bytes_done = 0
            self.flags, self._off, off = bytearray(self.total), {}, 0
            for t in tracks:
                self._off[t["name"]] = off
                for i in range(len(t["parts"])):
                    if os.path.exists(self._fn(t, i)):
                        self.segs_done += 1
                        self.flags[off + i] = 1
                        self.bytes_done += os.path.getsize(self._fn(t, i))
                off += len(t["parts"])
            self.status, self.note = "Downloading", ""
            self._last = (time.time(), self.done)
            todo = iter([(t, i) for t in tracks for i in range(len(t["parts"])) if not os.path.exists(self._fn(t, i))])
            workers = [threading.Thread(target=self._hls_worker, args=(todo,), daemon=True)
                       for _ in range(max(1, self.connections))]
            for w in workers:
                w.start()
            for w in workers:
                w.join()
            if self.failed.is_set():
                self.status = "Error"
            elif all(os.path.exists(self._fn(t, i)) for t in tracks for i in range(len(t["parts"]))):
                self.note = "merging..."
                self.note = self._finish()
                self.status = "Completed"
            else:
                self.status = "Paused"
        except Fatal as e:
            self.error, self.status = str(e), "Error"
        except Exception as e:
            self.error, self.status = str(e), "Error"
        self.speed = 0

    def _finish(self):
        pd = self.path + ".parts"
        base, ext = os.path.splitext(self.path)
        outs = []
        for t in self.plan["tracks"]:
            out = os.path.join(pd, t["name"] + ".merged")
            with open(out, "wb") as o:
                for i in range(len(t["parts"])):
                    with open(self._fn(t, i), "rb") as f:
                        shutil.copyfileobj(f, o, 1 << 20)
            outs.append(out)
        ff, note, final = find_ffmpeg(), "", self.path
        merged = merge_streams(ff, outs, base) if ff and (len(outs) == 2 or ext == ".ts") else None
        if merged:
            final = merged
        elif len(outs) == 2:  # separate video + audio renditions, and no way to merge them
            shutil.move(outs[0], self.path)
            shutil.move(outs[1], base + ".audio" + ext)
            note = "audio saved as a separate file (install ffmpeg to merge)"
        else:
            shutil.move(outs[0], self.path)
        self.path, self.name = final, os.path.basename(final)
        shutil.rmtree(pd, ignore_errors=True)
        return note


class MuxDownload(Download):
    """A silent video file + a separate audio file (how Facebook, Instagram and other DASH sites serve video).
    Both download in parallel into a temp folder, then are merged into one .mp4 with ffmpeg
    (without ffmpeg they are kept side by side, so nothing is lost)."""
    kind = "mux"

    def __init__(self, url, folder, connections=8, audio_url="", **kw):
        super().__init__(url, folder, connections, **kw)
        self.audio_url, self.note = audio_url, ""
        tmp = os.path.join(folder, ".opendm-" + secrets.token_hex(4))
        common = dict(referer=self.referer, cookie=self.cookie, ua=self.ua)
        self.children = [Download(url, tmp, connections, hint="video.mp4", **common),
                         Download(audio_url, tmp, max(2, connections // 2), hint="audio.m4a", **common)]
        if self.hint:
            self.name = clean_name(re.sub(r"\.(mp4|m4a|m4v|webm|mkv)$", "", self.hint, flags=re.I)) + ".mp4"

    def to_dict(self):
        d = super().to_dict()
        d.update(kind="mux", audio_url=self.audio_url, note=self.note, children=[c.to_dict() for c in self.children])
        return d

    def _loaded(self):
        self.children = [Download.from_dict(c) if isinstance(c, dict) else c for c in self.children]

    @property
    def done(self):
        return sum(c.done for c in self.children)

    def _sync(self):
        sizes = [c.size for c in self.children]
        self.size = sum(sizes) if all(z > 0 for z in sizes) else -1

    def set_limit(self, kb):
        super().set_limit(kb)
        for c in self.children:
            c.set_limit(kb)

    def pause(self):
        super().pause()
        for c in self.children:
            c.pause()

    def discard(self):
        if self.status != "Completed":
            shutil.rmtree(self.children[0].folder, ignore_errors=True)

    def segment_rows(self):
        out = []
        for label, c in zip(("Video", "Audio"), self.children):
            for _, got, info in c.segment_rows():
                out.append((len(out) + 1, got, f"{label}: {info}"))
        return out

    def segment_map(self):
        sizes = [max(c.size, 0) for c in self.children]
        total, out, off = sum(sizes), [], 0.0
        for c, z in zip(self.children, sizes):
            for x0, x1, xf in (c.segment_map() if total else []):
                out.append((off + x0 * z / total, off + x1 * z / total, off + xf * z / total))
            off += z / total if total else 0
        return out

    def _join_children(self):
        for c in self.children:
            if c.thread:
                c.thread.join(timeout=10)

    def _run(self):
        try:
            self.note = ""
            for c in self.children:
                if c.status != "Completed":
                    c.start()
            self.status = "Downloading"
            self._last = (time.time(), self.done)
            while not self.stop.is_set():
                self._sync()
                bad = next((c for c in self.children if c.status == "Error"), None)
                if bad or all(c.status == "Completed" for c in self.children):
                    if bad:
                        self.error = bad.error or "download failed"
                        for c in self.children:
                            c.pause()
                    break
                time.sleep(0.2)
            self._join_children()
            self._sync()
            if any(c.status == "Error" for c in self.children):
                self.status = "Error"
            elif all(c.status == "Completed" for c in self.children):
                self.note = "merging..."
                self.note = self._merge()
                self.status = "Completed"
            else:
                self.status = "Paused"
        except Exception as e:
            self.error, self.status = str(e), "Error"
        self.speed = 0

    def _merge(self):
        v, a = self.children
        stem = clean_name(re.sub(r"\.(mp4|m4a|m4v|webm|mkv)$", "", self.hint or v.name or "video", flags=re.I))
        self.name = stem + ".mp4"
        self._route()
        os.makedirs(self.folder, exist_ok=True)
        n, name = 0, stem
        while any(os.path.exists(os.path.join(self.folder, name + e)) for e in (".mp4", ".mkv", " (video only).mp4", " (audio only).m4a")):
            n += 1
            name = f"{stem} ({n})"
        ff, note = find_ffmpeg(), ""
        merged = merge_streams(ff, [v.path, a.path], os.path.join(self.folder, name), maps=True) if ff else None
        if merged:
            self.path = merged
        else:
            self.path = os.path.join(self.folder, name + " (video only).mp4")
            shutil.move(v.path, self.path)
            shutil.move(a.path, os.path.join(self.folder, name + " (audio only).m4a"))
            note = ("ffmpeg not found" if not ff else "merge failed") + ": saved video and audio as separate files"
        self.name = os.path.basename(self.path)
        shutil.rmtree(v.folder, ignore_errors=True)
        return note


class DashDownload(Download):
    """MPEG-DASH (.mpd): ffmpeg reads the manifest, fetches every segment and writes one clean .mp4 (or .mkv when MP4 can't hold the codecs)."""
    kind = "dash"

    def __init__(self, url, folder, connections=8, quality=0, **kw):
        super().__init__(url, folder, connections, **kw)
        self.quality, self.note, self.bytes_done, self.out_us, self.dur_us = quality, "", 0, 0, 0

    def to_dict(self):
        d = super().to_dict()
        d.update(kind="dash", quality=self.quality, note=self.note)
        return d

    @property
    def done(self):
        return self.bytes_done

    @property
    def percent(self):
        if self.status == "Completed":
            return 100.0
        return min(99.9, 100.0 * self.out_us / self.dur_us) if self.dur_us else 0.0

    def segment_map(self):
        return []

    def segment_rows(self):
        return [(1, human(self.bytes_done), "Complete" if self.status == "Completed" else "Receiving data..." if self.status in ACTIVE else "Stopped")]

    def _manifest(self):
        with self._open() as r:
            text = r.read(4_000_000).decode("utf-8", "replace")
        if "<MPD" not in text:
            raise IOError("this address is not a DASH manifest")
        if re.search(r"<ContentProtection[^>]+(widevine|playready|edef8ba9|9a04f079)", text, re.I):
            raise IOError("this stream is DRM-protected (Widevine/PlayReady) and can't be downloaded")
        m = re.search(r'mediaPresentationDuration="PT(?:(\d+)H)?(?:(\d+)M)?(?:([\d.]+)S)?"', text)
        if m:
            h, mi, s = (float(x or 0) for x in m.groups())
            self.dur_us = int((h * 3600 + mi * 60 + s) * 1e6)

    def _run(self):
        proc = None
        try:
            self.note, self.bytes_done, self.out_us = "", 0, 0
            ff = find_ffmpeg()
            if not ff:
                raise IOError("ffmpeg is needed for DASH (.mpd) streams: put ffmpeg next to opendm.py, or set OPENDM_FFMPEG")
            self._manifest()
            stem = os.path.splitext(clean_name(self.hint or name_from_url(self.url) or "video"))[0]
            if not self.path:
                self.name = stem + ".mp4"
                self._route()
                os.makedirs(self.folder, exist_ok=True)
                n, base = 0, stem
                while any(os.path.exists(os.path.join(self.folder, base + e)) for e in (".mp4", ".mkv")):
                    n += 1
                    base = f"{stem} ({n})"
                self.path = os.path.join(self.folder, base + ".mp4")
            base = os.path.splitext(self.path)[0]
            hdr = f"User-Agent: {self.ua or UA}\r\n" + (f"Referer: {self.referer}\r\n" if self.referer else "") + (f"Cookie: {self.cookie}\r\n" if self.cookie else "")
            self.status, err = "Downloading", ""
            self._last = (time.time(), 0)
            for ext, codec in ((".mp4", ["-c", "copy", "-movflags", "+faststart"]), (".mkv", ["-c", "copy"])):
                tmp = base + ".opendm-part" + ext
                proc = subprocess.Popen([ff, "-y", "-loglevel", "error", "-nostats", "-progress", "pipe:1", "-headers", hdr, "-i", self.url, *codec, tmp],
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, errors="replace", **_ff_flags())
                errs = []
                threading.Thread(target=lambda p=proc, e=errs: e.extend(p.stderr.read().splitlines()), daemon=True).start()
                threading.Thread(target=self._watch, args=(proc,), daemon=True).start()
                for line in proc.stdout:
                    k, _, v = line.strip().partition("=")
                    if k in ("out_time_us", "out_time_ms") and v.lstrip("-").isdigit():
                        self.out_us = max(self.out_us, int(v))
                    elif k == "total_size" and v.isdigit():
                        self.bytes_done = int(v)
                rc = proc.wait()
                if self.stop.is_set():
                    self._rm(tmp)
                    self.status, self.speed = "Paused", 0
                    return
                if rc == 0 and os.path.isfile(tmp) and os.path.getsize(tmp) > 0:
                    final = base + ext
                    self._rm(final)
                    os.replace(tmp, final)
                    self.path, self.name, self.bytes_done = final, os.path.basename(final), os.path.getsize(final)
                    self.size, self.status = self.bytes_done, "Completed"
                    self.speed = 0
                    return
                self._rm(tmp)
                err = " ".join(errs[-2:])[:200]
            raise IOError("ffmpeg could not download this stream" + (f": {err}" if err else ""))
        except Exception as e:
            self.error, self.status = str(e), "Error"
        self.speed = 0

    def _watch(self, proc):
        if self._wait_stop(proc):
            proc.terminate()

    def _wait_stop(self, proc):
        while proc.poll() is None:
            if self.stop.wait(0.3):
                return True
        return False

    @staticmethod
    def _rm(p):
        try:
            os.remove(p)
        except OSError:
            pass


class NativeYt(Download):
    """yt-dlp's own downloader, for streams OpenDM's engine can't fetch directly (fragmented DASH and the like)."""
    kind = "ytnative"

    def __init__(self, url, folder, connections=8, quality=0, **kw):
        super().__init__(url, folder, connections, **kw)
        self.quality = quality

    def to_dict(self):
        d = super().to_dict()
        d.update(kind="ytnative", quality=self.quality)
        return d

    def _run(self):
        try:
            y = _ytdlp()
            if y is None:
                raise IOError(YT_MISSING)
            os.makedirs(self.folder, exist_ok=True)
            stem = os.path.splitext(clean_name(self.hint or "video.mp4"))[0]
            n, base = 0, stem
            while any(os.path.exists(os.path.join(self.folder, base + e)) for e in (".mp4", ".mkv", ".webm", ".m4a")):
                n += 1
                base = f"{stem} ({n})"
            self.status = "Downloading"

            def hook(h):
                if self.stop.is_set():
                    raise IOError("stopped")
                if h.get("status") == "downloading":
                    got, tot = int(h.get("downloaded_bytes") or 0), int(h.get("total_bytes") or h.get("total_bytes_estimate") or 0)
                    self.size = tot if tot > 0 else -1
                    self.segs = [[0, tot - 1 if tot > 0 else None, got]]
            opts = dict(ytdlp_opts(self.quality, self.referer, self.cookie, self.ua), outtmpl=os.path.join(self.folder, base + ".%(ext)s"),
                        progress_hooks=[hook], noprogress=True)
            with y.YoutubeDL(opts) as ydl:
                apply_cookies(ydl, self.cookie, self.url)  # FIX: cookies via cookiejar
                info = ydl.extract_info(self.url, download=True)
                if info and info.get("entries"):
                    info = next((e for e in info["entries"] if e), None)
                path = ((info or {}).get("requested_downloads") or [{}])[0].get("filepath") or (ydl.prepare_filename(info) if info else "")
            if not path or not os.path.isfile(path):
                path = next((os.path.join(self.folder, f) for f in sorted(os.listdir(self.folder)) if f.startswith(base + ".") and not f.endswith((".part", ".ytdl"))), "")
            if not path or not os.path.isfile(path) or os.path.getsize(path) == 0:
                raise IOError("yt-dlp finished but no file was written")
            self.path, self.name, self.size = path, os.path.basename(path), os.path.getsize(path)
            self.segs, self.status = [[0, self.size - 1, self.size]], "Completed"
        except Exception as e:
            if self.stop.is_set():
                self.status = "Paused"
            else:
                self.error, self.status = str(e), "Error"
        self.speed = 0


class ExtractDownload(Download):
    """A video page (YouTube, Facebook, Instagram, Vimeo, TikTok ...): yt-dlp finds the real stream links, OpenDM's own engine downloads
    them (multi-connection, resumable) and ffmpeg merges video + audio into one file."""
    kind = "ytdlp"

    def __init__(self, url, folder, connections=8, quality=0, **kw):
        super().__init__(url, folder, connections, **kw)
        self.quality, self.note, self.title, self.inner = quality, "", "", None

    def to_dict(self):
        d = super().to_dict()
        d.update(kind="ytdlp", quality=self.quality, note=self.note, title=self.title, inner=self.inner.to_dict() if self.inner else None)
        return d

    def _loaded(self):
        if isinstance(self.inner, dict):
            self.inner = Download.from_dict(self.inner)

    @property
    def label(self):
        return self.name or self.hint or self.title or self.url

    @property
    def done(self):
        return self.inner.done if self.inner else 0

    @property
    def percent(self):
        return self.inner.percent if self.inner else 0.0

    def segment_map(self):
        return self.inner.segment_map() if self.inner else []

    def segment_rows(self):
        return self.inner.segment_rows() if self.inner else []

    def set_limit(self, kb):
        super().set_limit(kb)
        if self.inner:
            self.inner.set_limit(kb)

    def pause(self):
        super().pause()
        if self.inner:
            self.inner.pause()

    def discard(self):
        self._drop_inner()

    def _drop_inner(self):
        i, self.inner = self.inner, None
        if not i:
            return
        if hasattr(i, "discard"):
            i.discard()
        if i.status != "Completed" and i.path and os.path.exists(i.path):
            try:
                os.remove(i.path)
            except OSError:
                pass

    def _sync(self):
        i = self.inner
        if i:
            self.size, self.ranges = i.size, i.ranges
            if i.name:
                self.name = i.name
            if i.path:
                self.path = i.path
            self.note = i.note if getattr(i, "note", "") else self.note

    def _build(self, plan):
        self.title = plan["title"]
        ext = os.path.splitext(plan["name"])[1]
        h = clean_name(self.hint) if self.hint else ""
        self.name = h if h and os.path.splitext(h)[1].lower().lstrip(".") in BINARY_EXT else (h + ext if h else plan["name"])
        self._route()  # category folder, now that the real name is known
        common = dict(referer=plan.get("referer") or self.referer, cookie=self.cookie, ua=plan.get("ua") or self.ua)
        k, c = plan["kind"], self.connections
        if k == "direct":
            inner = Download(plan["url"], self.folder, c, hint=self.name, **common)
        elif k == "mux":
            inner = MuxDownload(plan["url"], self.folder, c, audio_url=plan["audio"], hint=self.name, **common)
        elif k == "hls":
            inner = HlsDownload(plan["url"], self.folder, c, quality=self.quality, hint=self.name, **common)
        else:
            inner = NativeYt(self.url, self.folder, c, quality=self.quality, hint=self.name, **common)
        inner.set_limit(self.limit_kb)
        self.inner = inner

    def _run(self):
        try:
            for attempt in (0, 1):
                if self.inner is None:
                    self.note = "extracting stream links..."
                    plan = ytdlp_resolve(self.url, self.quality, self.referer, self.cookie, self.ua)
                    if self.stop.is_set():
                        self.status, self.note, self.speed = "Paused", "", 0
                        return
                    self._build(plan)
                    self.note = ""
                inner = self.inner
                if inner.status != "Completed":
                    inner.start()
                self.status = "Downloading"
                self._last = (time.time(), self.done)
                while not self.stop.is_set():
                    self._sync()
                    if inner.status in ("Completed", "Error"):
                        break
                    time.sleep(0.2)
                if inner.thread:
                    inner.thread.join(timeout=15)
                self._sync()
                if inner.status == "Completed":
                    self.name, self.path = inner.name or self.name, inner.path
                    self.status = "Completed"
                elif inner.status == "Error":
                    if attempt == 0 and re.search(r"\b(401|403|404|410)\b|expired|forbidden", inner.error or "", re.I):
                        self._drop_inner()  # signed stream links expire: ask yt-dlp for fresh ones
                        continue
                    self.error, self.status = inner.error or "download failed", "Error"
                else:
                    self.status = "Paused"
                break
        except Exception as e:
            self.error, self.status = str(e), "Error"
        self.speed = 0


SETTINGS_FILE = os.path.join(CFG_DIR, "settings.json")
DEFAULT_SETTINGS = {"limit_kb": 0, "sched_on": False, "start": "01:00", "stop": "07:00", "after": "none", "quality": 0,
                    "folder": "", "auto_sort": True, "categories": DEFAULT_CATEGORIES, "queues": [MAIN_QUEUE], "connections": 8, "max_active": 0,
                    "tray": True, "close_to_tray": True, "notify": True, "start_minimized": False,
                    "native_register": True, "autostart_from_browser": True, "extension_ids": [],
                    "show_complete_dialog": True, "confirm_captured": True}


class Manager:
    def __init__(self, max_active=3, persist=True):
        self.items, self.max_active, self.persist = [], max_active, persist
        self.settings = copy.deepcopy(DEFAULT_SETTINGS)
        self._busy, self._base = False, 0
        self.hist, self._hist_t = deque(maxlen=HIST), 0.0  # total speed, one sample per second
        if persist:
            self.load_settings()
            self.load()
        self._fix_categories()
        self._fix_queues()
        if int(self.settings.get("max_active") or 0) > 0:
            self.max_active = int(self.settings["max_active"])
        for d in self.items:
            d.router = self.route
            d.queue = d.queue if d.queue in self.settings["queues"] else MAIN_QUEUE
        GLOBAL_LIMIT.set_rate(self.settings["limit_kb"] * 1024)

    def add(self, url, folder, connections=8, kind=None, **extra):
        url = url.strip()
        if kind is None:
            kind = detect_kind(url)  # hls (.m3u8) / dash (.mpd) / ytdlp (YouTube, Facebook, Instagram ...) / plain file
        queue_name = extra.pop("queue", None) or MAIN_QUEUE
        project, later, desc = extra.pop("project", ""), extra.pop("later", False), extra.pop("desc", "")
        if kind == "mux":
            d = MuxDownload(url, folder, connections, **extra)
        elif kind == "dash":
            d = DashDownload(url, folder, connections, quality=extra.pop("quality", None) or self.settings.get("quality", 0), **extra)
        elif kind == "ytdlp":
            q = extra.pop("quality", None)
            d = ExtractDownload(url, folder, connections, quality=self.settings.get("quality", 0) if q is None else q, **extra)
        elif kind == "hls":
            q = extra.pop("quality", None)
            d = HlsDownload(url, folder, connections, quality=self.settings.get("quality", 0) if q is None else q, **extra)
        else:
            d = Download(url, folder, connections, **extra)
        d.router = self.route
        guess = d.hint or urllib.parse.unquote(os.path.basename(urllib.parse.urlparse(url).path))
        if kind == "ytdlp" and not d.hint:
            guess = "video.mp4"  # the real title comes from the video page
        if kind in ("hls", "mux", "dash", "ytdlp") and not os.path.splitext(guess)[1]:
            guess += ".mp4"
        d.category = classify(self.settings["categories"], guess, url)  # provisional: refined once the real file name is known
        d.queue = queue_name if queue_name in self.settings["queues"] else MAIN_QUEUE
        d.project = project
        d.desc = desc or urllib.parse.urlparse(d.referer or url).netloc
        if later:
            d.status = "Paused"  # "Download later": waits in its queue until you start it
        self.items.append(d)
        return d

    # ----- settings -----
    def load_settings(self):
        try:
            with open(SETTINGS_FILE) as f:
                self.settings.update(json.load(f))
        except (OSError, ValueError):
            pass

    def _fix_categories(self):
        """Keep the list sane even if settings.json was edited by hand: General always exists and comes first."""
        good = []
        for c in self.settings.get("categories") or []:
            if isinstance(c, dict) and isinstance(c.get("name"), str) and c["name"].strip():
                good.append({"name": c["name"].strip(), "folder": str(c.get("folder") or ""),
                             "exts": [str(x).lower().lstrip(".") for x in c.get("exts", [])],
                             "sites": [str(x).lower() for x in c.get("sites", [])]})
        if not any(c["name"] == "General" for c in good):
            good.insert(0, _cat("General"))
        good.sort(key=lambda c: c["name"] != "General")
        self.settings["categories"] = good

    def _fix_queues(self):
        names = []
        for q in [MAIN_QUEUE] + [x for x in (self.settings.get("queues") or []) if isinstance(x, str)]:
            q = q.strip()[:40]
            if q and q.lower() not in [n.lower() for n in names]:
                names.append(q)
        self.settings["queues"] = names

    # ----- queues, projects -----
    def _queue_name(self, name, exclude=None):
        name = (name or "").strip()
        if not name or len(name) > 40 or any(ch in name for ch in '/\\:*?"<>|'):
            raise ValueError("Give the queue a short name without  / \\ : * ? \" < > |")
        if any(q.lower() == name.lower() and q != exclude for q in self.settings["queues"]):
            raise ValueError(f"There is already a queue called {name!r}.")
        return name

    def add_queue(self, name):
        name = self._queue_name(name)
        self.settings["queues"].append(name)
        self.save_settings()
        return name

    def rename_queue(self, old, new):
        if old == MAIN_QUEUE:
            raise ValueError("The main queue can't be renamed.")
        new = self._queue_name(new, exclude=old)
        self.settings["queues"] = [new if q == old else q for q in self.settings["queues"]]
        for d in self.items:
            if d.queue == old:
                d.queue = new
        self.save_settings()
        return new

    def delete_queue(self, name):
        if name == MAIN_QUEUE:
            raise ValueError("The main queue can't be deleted.")
        self.settings["queues"] = [q for q in self.settings["queues"] if q != name]
        for d in self.items:
            if d.queue == name:
                d.queue = MAIN_QUEUE
        self.save_settings()

    def move_to_queue(self, d, name):
        if name not in self.settings["queues"]:
            raise ValueError(f"There is no queue called {name!r}")
        d.queue = name

    def start_queue(self, name):
        """Queue every stopped/failed download of the queue (the scheduler window still applies)."""
        n = 0
        for d in self.items:
            if d.queue == name and d.status in ("Paused", "Error"):
                d.status, d.auto_paused = "Queued", False
                n += 1
        return n

    def stop_queue(self, name):
        n = 0
        for d in self.items:
            if d.queue == name and (d.status in ACTIVE or d.status == "Queued"):
                d.auto_paused = d.force = False
                if d.status in ACTIVE:
                    d.pause()
                else:
                    d.status = "Paused"
                n += 1
        return n

    def projects(self):
        return sorted({d.project for d in self.items if d.project}, key=str.lower)

    # ----- export / import -----
    def export_list(self, path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"opendm": __version__, "downloads": [d.to_dict() for d in self.items]}, f, indent=1)
        return len(self.items)

    def import_list(self, path, folder):
        """Import an OpenDM export (.json) or any text file containing links. Imported items start stopped."""
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
        added = 0
        try:
            data = json.loads(text)
            rows = data["downloads"] if isinstance(data, dict) else data
            for x in rows:
                if not isinstance(x, dict) or not str(x.get("url", "")).startswith(("http://", "https://")):
                    continue
                if any(d.url == x["url"] and d.name == x.get("name") for d in self.items):
                    continue
                d = Download.from_dict(x)
                d.router = self.route
                d.queue = d.queue if d.queue in self.settings["queues"] else MAIN_QUEUE
                self.items.append(d)
                added += 1
            return added
        except (ValueError, KeyError, TypeError):
            pass
        for u in dict.fromkeys(re.findall(r"https?://[^\s<>\"']+", text)):
            self.add(u, folder, later=True)
            added += 1
        return added

    def route(self, d):
        """Called when a download learns its real file name: set its category and, if auto-sort is on, its folder."""
        if not d.auto_cat:
            return
        cats = self.settings["categories"]
        d.category = classify(cats, d.name or "", d.url)
        if self.settings.get("auto_sort", True):
            d.folder = category_folder(cats, d.category, d.base)

    def move_to_category(self, d, name):
        """Pin a download to a category: before it starts that changes where it will be saved; once finished the file is moved."""
        cats = self.settings["categories"]
        if not any(c["name"] == name for c in cats):
            raise ValueError(f"There is no category called {name!r}")
        if d.path and d.status != "Completed":
            raise ValueError("Pause and remove it, or wait until it finishes: a partly downloaded file can't be moved.")
        dest = category_folder(cats, name, d.base)
        if d.path and os.path.exists(d.path):
            os.makedirs(dest, exist_ok=True)
            target = unique_path(dest, os.path.basename(d.path))
            shutil.move(d.path, target)
            d.path, d.name = target, os.path.basename(target)
        d.category, d.auto_cat, d.folder = name, False, dest

    def save_settings(self):
        if not self.persist:
            return
        os.makedirs(CFG_DIR, exist_ok=True)
        with open(SETTINGS_FILE, "w") as f:
            json.dump(self.settings, f)

    def set_limit_kb(self, kb):
        self.settings["limit_kb"] = max(0, int(kb))
        GLOBAL_LIMIT.set_rate(self.settings["limit_kb"] * 1024)
        self.save_settings()

    def in_window(self, now_min=None):
        """True when downloads may run (always, unless the scheduler is on). Handles overnight windows."""
        st = self.settings
        if not st["sched_on"]:
            return True
        if now_min is None:
            t = time.localtime()
            now_min = t.tm_hour * 60 + t.tm_min
        try:
            a, b = parse_hm(st["start"]), parse_hm(st["stop"])
        except ValueError:
            return True
        if a == b:
            return True
        return a <= now_min < b if a < b else (now_min >= a or now_min < b)

    # ----- queue + scheduler; returns True once when a batch of downloads has just finished -----
    def schedule(self):
        allowed = self.in_window()
        for d in self.items:
            if allowed and d.auto_paused and d.status == "Paused":
                d.auto_paused, d.status = False, "Queued"
            elif not allowed and d.status in ACTIVE and not d.force:
                d.auto_paused = True
                d.pause()
        active = sum(d.status in ACTIVE for d in self.items)
        cur = sum(d.speed for d in self.items if d.status in ACTIVE)
        if cur > 0:
            self.speed_seen = cur if not getattr(self, "speed_seen", 0) else 0.9 * self.speed_seen + 0.1 * cur
        for d in self.items:
            if active >= self.max_active:
                break
            if d.status == "Queued" and (allowed or d.force):
                d.start()
                active += 1
        for d in self.items:
            d.update_speed()
        if time.time() - self._hist_t >= 1:
            self._hist_t = time.time()
            self.hist.append(sum(d.speed for d in self.items))
        pending = any(d.status in ACTIVE or d.status == "Queued" or (d.auto_paused and d.status == "Paused")
                      for d in self.items)
        done = sum(d.status == "Completed" for d in self.items)
        if pending:
            if not self._busy:
                self._busy, self._base = True, done
        elif self._busy:
            self._busy = False
            return done > self._base
        return False

    def remove(self, d, delete_file=False, delete_completed=False):
        d.pause()
        if d.thread:
            d.thread.join(timeout=3)
        if delete_file and d.status != "Completed":
            getattr(d, "discard", lambda: None)()  # temp folders of HLS / video+audio downloads
        if delete_completed and d.status == "Completed" and d.path and os.path.exists(d.path):
            try:
                os.remove(d.path)
            except OSError:
                pass
        if delete_file and d.path and d.status != "Completed" and os.path.exists(d.path):
            try:
                os.remove(d.path)
            except OSError:
                pass
        self.items.remove(d)

    def save(self):
        os.makedirs(CFG_DIR, exist_ok=True)
        tmp = DB_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump([d.to_dict() for d in self.items], f)
        os.replace(tmp, DB_FILE)

    def load(self):
        try:
            with open(DB_FILE) as f:
                self.items = [Download.from_dict(x) for x in json.load(f)]
        except (OSError, ValueError, KeyError):
            self.items = []

    def shutdown(self):
        for d in self.items:
            d.pause()
        for d in self.items:
            if d.thread:
                d.thread.join(timeout=3)
        self.save()


# ====================== Browser integration API ======================
def get_token(state_dir=None):
    state_dir = state_dir or CFG_DIR
    os.makedirs(state_dir, exist_ok=True)
    p = os.path.join(state_dir, "token")
    try:
        with open(p) as f:
            return f.read().strip()
    except OSError:
        t = secrets.token_urlsafe(24)
        with open(p, "w") as f:
            f.write(t)
        try:
            os.chmod(p, 0o600)
        except OSError:
            pass
        return t


STALE_CAPTURE_SECS = 90      # a browser request older than this is ignored
CAPTURE_DEDUPE_SECS = 30     # the same link offered again within this time is ignored
CAPTURE_EXPIRE_SECS = 300    # a confirmation that waited this long unanswered is dropped
CAPTURE_MAX_QUEUE = 10


def start_api(mgr, defaults, port=API_PORT, token=None, state_dir=None, confirm=None):
    """Local-only API for the browser extension. Needs the pairing token AND an
    extension Origin (web pages cannot forge Origin) AND a localhost Host header
    (blocks DNS rebinding).
    confirm(job): when given (the GUI), captured links are handed to it instead of being added -
    nothing downloads until the user clicks Start. job = {url, folder, connections, kind, kw}."""
    token = token or get_token(state_dir)
    fcache, fcache_lock = {}, threading.Lock()  # url -> (time, stream list): extraction takes seconds, so repeat opens of the menu reuse it

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _origin_ok(self):
            o, host = self.headers.get("Origin", ""), self.headers.get("Host", "")
            # Chrome omits Origin on some extension requests, so allow none; but a web page's
            # Origin is always sent on cross-origin POST/preflight and is rejected here.
            return (o == "" or o.startswith(("chrome-extension://", "moz-extension://"))) and \
                host in (f"127.0.0.1:{port}", f"localhost:{port}")

        def _send(self, code, obj=None):
            body = json.dumps(obj or {}).encode()
            self.send_response(code)
            self.send_header("Access-Control-Allow-Origin", self.headers.get("Origin", ""))
            self.send_header("Access-Control-Allow-Headers", "Content-Type, X-OpenDM-Token")
            self.send_header("Vary", "Origin")
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _auth(self):
            if not self._origin_ok():
                self._send(403, {"error": "forbidden origin"})
            elif not secrets.compare_digest(self.headers.get("X-OpenDM-Token", ""), token):
                self._send(401, {"error": "bad token"})
            else:
                return True
            return False

        def do_OPTIONS(self):
            self._send(200 if self._origin_ok() else 403)

        def do_GET(self):
            if self.path == "/ping" and self._auth():
                self._send(200, {"app": "OpenDM", "version": 1})

        def _body(self):
            try:
                n = int(self.headers.get("Content-Length", 0))
                d = json.loads(self.rfile.read(min(n, 1 << 20)))
                url = str(d["url"])
                if not url.startswith(("http://", "https://")):
                    raise ValueError("unsupported scheme")
                return d, url
            except (ValueError, KeyError, TypeError):
                self._send(400, {"error": "bad request"})
                return None, None

        def _formats(self):
            """The video menu in the browser: which qualities does this page offer (via yt-dlp), their sizes, and how fast is this machine's connection."""
            d, url = self._body()
            if d is None:
                return
            speed = getattr(mgr, "speed_seen", 0.0)
            if not media_site(url):
                return self._send(200, {"ok": False, "error": "not a video page", "speed": speed})
            with fcache_lock:
                hit = fcache.get(url)
            if hit and time.time() - hit[0] < 300:
                return self._send(200, dict(hit[1], speed=speed))
            try:
                info = ytdlp_formats(url, d.get("referer") or None, d.get("cookie") or None, d.get("userAgent") or None)
            except IOError as e:
                return self._send(200, {"ok": False, "error": str(e), "missing": str(e) == YT_MISSING, "speed": speed})
            except Exception as e:
                return self._send(200, {"ok": False, "error": "yt-dlp could not read this video: " + re.sub(r"\s+", " ", str(e))[:160], "speed": speed})
            info["ok"] = True
            with fcache_lock:
                if len(fcache) > 50:
                    fcache.clear()
                fcache[url] = (time.time(), info)
            self._send(200, dict(info, speed=speed))

        def do_POST(self):
            if self.path == "/formats":
                if self._auth():
                    self._formats()
                return
            if self.path != "/add" or not self._auth():
                return
            d, url = self._body()
            if d is None:
                return
            ts = d.get("ts")  # when the browser says the user started it (ms); old requests are never shown
            if isinstance(ts, (int, float)) and not isinstance(ts, bool) and abs(time.time() - ts / 1000.0) > STALE_CAPTURE_SECS:
                return self._send(409, {"error": "stale request ignored"})
            folder, conns = defaults()
            kind_in = d.get("kind")
            hls, yt, dash = kind_in == "hls", kind_in == "ytdlp", kind_in == "dash"
            pick = {}
            for src, dst in (("quality", "quality"), ("bandwidth", "pick_bw")):
                if hls and type(d.get(src)) is int and d[src] > 0:
                    pick[dst] = d[src]
            if yt and type(d.get("quality")) is int and (0 < d["quality"] <= 8640 or d["quality"] == -1):
                pick["quality"] = d["quality"]  # height cap, or -1 = audio only
            audio = d.get("audioUrl")
            mux = not (hls or yt or dash) and isinstance(audio, str) and audio.startswith(("http://", "https://"))
            if mux:
                pick["audio_url"] = audio
            kw = dict(pick, referer=d.get("referer") or None, cookie=d.get("cookie") or None,
                      ua=d.get("userAgent") or None, hint=clean_name(d["filename"]) if d.get("filename") else None)
            job = {"url": url, "folder": folder, "connections": conns, "kind": "hls" if hls else "ytdlp" if yt else "dash" if dash else "mux" if mux else None, "kw": kw}
            if confirm is not None:
                confirm(job)
            else:
                mgr.add(job["url"], job["folder"], job["connections"], kind=job["kind"], **kw)
            self._send(200, {"ok": True})

    try:
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), H)
    except OSError:
        return None
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    write_api_hint(port, state_dir)
    return srv


def write_api_hint(port, state_dir=None):
    """Tell the native-messaging host which port this instance listens on (it falls back to 6800)."""
    try:
        d = state_dir or CFG_DIR
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "api.json"), "w") as f:
            json.dump({"port": port, "pid": os.getpid()}, f)
    except OSError:
        pass


# ============================ browser integration: native messaging ============================
# The browser extension talks to OpenDM through a "native messaging host": a program the *browser* starts on demand,
# but only for extension IDs listed in the host's manifest. Browsers find the manifest through the Windows Registry
# (HKCU\Software\<vendor>\NativeMessagingHosts\<name>) or, on Linux/macOS, a per-browser folder. The host is simply
# OpenDM started in a special mode (`--native-host`); it forwards each message to OpenDM's local server and, if
# OpenDM isn't running, starts it first. The extension therefore needs no port and no pairing token.
NATIVE_HOST_NAME = "org.opendm.nativehost"
DEFAULT_EXTENSION_IDS = ("jngcdhpgdacflokoombdcimnonfngiff",)  # fixed by the "key" in extension/manifest.json (tools/extension_id.py)
FIREFOX_EXTENSION_ID = "opendm@alter-xsource404.github.io"                    # the gecko id in extension/manifest.firefox.json
HOST_JOB_KEYS = ("url", "referer", "filename", "kind", "quality", "bandwidth", "audioUrl", "cookie", "userAgent", "ts")
MAX_NATIVE_MESSAGE = 1 << 20

# key, label, Windows registry path under HKCU, Linux folder, macOS folder, manifest flavour
BROWSERS = (
    ("chrome", "Google Chrome", r"Software\Google\Chrome\NativeMessagingHosts", "~/.config/google-chrome/NativeMessagingHosts",
     "~/Library/Application Support/Google/Chrome/NativeMessagingHosts", "chromium"),
    ("edge", "Microsoft Edge", r"Software\Microsoft\Edge\NativeMessagingHosts", "~/.config/microsoft-edge/NativeMessagingHosts",
     "~/Library/Application Support/Microsoft Edge/NativeMessagingHosts", "chromium"),
    ("brave", "Brave", r"Software\BraveSoftware\Brave-Browser\NativeMessagingHosts", "~/.config/BraveSoftware/Brave-Browser/NativeMessagingHosts",
     "~/Library/Application Support/BraveSoftware/Brave-Browser/NativeMessagingHosts", "chromium"),
    ("chromium", "Chromium", r"Software\Chromium\NativeMessagingHosts", "~/.config/chromium/NativeMessagingHosts",
     "~/Library/Application Support/Chromium/NativeMessagingHosts", "chromium"),
    ("firefox", "Mozilla Firefox", r"Software\Mozilla\NativeMessagingHosts", "~/.mozilla/native-messaging-hosts",
     "~/Library/Application Support/Mozilla/NativeMessagingHosts", "firefox"),
)
ALWAYS_REGISTER = ("chrome", "edge")  # on Windows these are registered even before any trace of the browser exists


def read_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def extension_ids(extra=()):
    """The built-in extension ID plus any the user added (e.g. a Chrome Web Store ID), validated."""
    ids = list(DEFAULT_EXTENSION_IDS) + [str(i).strip().lower() for i in extra]
    return tuple(dict.fromkeys(i for i in ids if re.fullmatch(r"[a-p]{32}", i)))


class NativeIntegration:
    """Registers (and removes) OpenDM's native-messaging host for the installed browsers.
    Windows: manifest files under <state>/native plus a value in HKCU\\Software\\<vendor>\\NativeMessagingHosts\\<name>.
    Linux/macOS: the manifest is written into each browser's NativeMessagingHosts folder."""

    def __init__(self, extra_ids=(), state_dir=None, home=None, system=None, winreg_module=None, frozen=None, executable=None, script=None):
        self.ids = extension_ids(extra_ids)
        self.state_dir = state_dir or CFG_DIR
        self.native_dir = os.path.join(self.state_dir, "native")
        self.home = home or os.path.expanduser("~")
        self.system = system or platform.system()
        self._winreg = winreg_module
        self.frozen = getattr(sys, "frozen", False) if frozen is None else frozen
        self.executable = executable or sys.executable
        self.script = script or os.path.abspath(__file__)

    # ---- what the browser should start
    def _launcher(self):
        """(path, body) of the wrapper the browser should start; body is None when OpenDM.exe itself is the host. Writes nothing."""
        if self.frozen:
            return self.executable, None
        if self.system == "Windows":
            exe = self.executable
            if os.path.basename(exe).lower() == "pythonw.exe" and os.path.exists(os.path.join(os.path.dirname(exe), "python.exe")):
                exe = os.path.join(os.path.dirname(exe), "python.exe")  # the host needs a real console process for stdin/stdout
            return os.path.join(self.native_dir, "opendm-host.bat"), f'@echo off\r\n"{exe}" "{self.script}" %*\r\n'
        return os.path.join(self.native_dir, "opendm-host.sh"), f'#!/bin/sh\nexec {shlex.quote(self.executable)} {shlex.quote(self.script)} "$@"\n'

    def host_command(self):
        """A program the browser can start with no arguments of ours: OpenDM.exe itself when frozen, else a tiny wrapper (created here)."""
        path, body = self._launcher()
        if body is not None:
            os.makedirs(self.native_dir, exist_ok=True)
            if read_text(path) != body:
                with open(path, "w", newline="") as f:
                    f.write(body)
            if self.system != "Windows":
                os.chmod(path, 0o755)
        return path

    def manifest(self, kind, command):
        m = {"name": NATIVE_HOST_NAME, "description": "OpenDM - hands browser downloads and videos to the OpenDM download manager",
             "path": command, "type": "stdio"}
        if kind == "firefox":
            m["allowed_extensions"] = [FIREFOX_EXTENSION_ID]
        else:
            m["allowed_origins"] = [f"chrome-extension://{i}/" for i in self.ids]
        return m

    # ---- Windows registry (injectable for tests)
    @property
    def winreg(self):
        if self._winreg is None:
            import winreg
            self._winreg = winreg
        return self._winreg

    def reg_key(self, row):
        return row[2] + "\\" + NATIVE_HOST_NAME

    def _reg_get(self, subkey):
        w = self.winreg
        try:
            with w.OpenKey(w.HKEY_CURRENT_USER, subkey, 0, w.KEY_READ) as k:
                return w.QueryValueEx(k, "")[0]
        except OSError:
            return None

    def _reg_set(self, subkey, value):
        w = self.winreg
        with w.CreateKey(w.HKEY_CURRENT_USER, subkey) as k:
            w.SetValueEx(k, "", 0, w.REG_SZ, value)

    def _reg_delete(self, subkey):
        try:
            self.winreg.DeleteKey(self.winreg.HKEY_CURRENT_USER, subkey)
        except OSError:
            pass

    def _reg_exists(self, subkey):
        w = self.winreg
        try:
            with w.OpenKey(w.HKEY_CURRENT_USER, subkey, 0, w.KEY_READ):
                return True
        except OSError:
            return False

    # ---- per-browser helpers
    def manifest_path(self, row):
        if self.system == "Windows":
            return os.path.join(self.native_dir, row[5], NATIVE_HOST_NAME + ".json")
        d = row[4] if self.system == "Darwin" else row[3]
        return os.path.join(self.home, d[2:], NATIVE_HOST_NAME + ".json")

    def detected(self, row):
        if self.system == "Windows":
            return self._reg_exists(row[2].rsplit("\\", 1)[0])  # the vendor key, e.g. Software\Google\Chrome
        return os.path.isdir(os.path.dirname(os.path.dirname(self.manifest_path(row))))

    def _write_manifest(self, path, data):
        text = json.dumps(data, indent=2) + "\n"
        if read_text(path) != text:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="") as f:  # newline="": Windows must not turn \n into \r\n, or status() sees it as outdated
                f.write(text)

    def register(self, only=None):
        """Create/refresh the registration for every installed browser. Safe to run on every start (it only writes what changed)."""
        out, command = [], self.host_command()
        for row in BROWSERS:
            key, label, kind = row[0], row[1], row[5]
            if only and key not in only:
                continue
            found = self.detected(row)
            e = {"key": key, "label": label, "detected": found, "registered": False, "detail": ""}
            if not found and not (self.system == "Windows" and key in ALWAYS_REGISTER):
                e["detail"] = "browser not found"
            else:
                try:
                    mp = self.manifest_path(row)
                    self._write_manifest(mp, self.manifest(kind, command))
                    if self.system == "Windows":
                        self._reg_set(self.reg_key(row), mp)
                    e["registered"], e["detail"] = True, (f"HKCU\\{self.reg_key(row)}" if self.system == "Windows" else mp)
                except OSError as ex:
                    e["detail"] = f"failed: {ex}"
            out.append(e)
        return out

    def status(self):
        """Per browser: registered / outdated / not registered / browser not found. Read-only."""
        out = []
        command, body = self._launcher()
        wrapper_ok = body is None or read_text(command) == body
        for row in BROWSERS:
            key, label, kind = row[0], row[1], row[5]
            mp, found = self.manifest_path(row), self.detected(row)
            have = read_text(mp)
            linked = have is not None and (self.system != "Windows" or self._reg_get(self.reg_key(row)) == mp)
            current = linked and have == json.dumps(self.manifest(kind, command), indent=2) + "\n" and wrapper_ok
            state = "registered" if current else "outdated" if linked else "not registered"
            if state == "not registered" and not found and not (self.system == "Windows" and key in ALWAYS_REGISTER):
                state = "browser not found"
            out.append({"key": key, "label": label, "detected": found, "state": state, "registered": state == "registered"})
        return out

    def unregister(self):
        for row in BROWSERS:
            if self.system == "Windows":
                self._reg_delete(self.reg_key(row))
            try:
                os.remove(self.manifest_path(row))
            except OSError:
                pass


def _basename(p):
    return re.split(r"[\\/]", p)[-1]


def read_text(path):
    try:
        with open(path, encoding="utf-8", newline="") as f:
            return f.read()
    except OSError:
        return None


def is_native_host_launch(argv):
    """True when a browser (not a person) started us: Chrome passes the extension origin, Firefox the manifest path + add-on id."""
    a = argv[1:]
    return ("--native-host" in a or any(x.startswith(("chrome-extension://", "moz-extension://")) for x in a)
            or (len(a) >= 2 and _basename(a[0]) == NATIVE_HOST_NAME + ".json"))


def nm_read(stream):
    """One native-messaging message (4-byte length in native byte order + UTF-8 JSON), or None at end of input."""
    raw = stream.read(4)
    if len(raw) < 4:
        return None
    (n,) = struct.unpack("=I", raw)
    if n > MAX_NATIVE_MESSAGE:
        raise ValueError("message too large")
    data = stream.read(n)
    if len(data) < n:
        raise ValueError("truncated message")
    return json.loads(data.decode("utf-8"))


def nm_write(stream, obj):
    data = json.dumps(obj).encode("utf-8")
    stream.write(struct.pack("=I", len(data)) + data)
    stream.flush()


def _std_binary_streams():
    """stdin/stdout as raw binary streams, also for a windowed (no-console) Windows exe where sys.stdin is None."""
    if os.name == "nt":
        import msvcrt
        for fd in (0, 1):
            try:
                msvcrt.setmode(fd, os.O_BINARY)
            except (OSError, ValueError):
                pass
        if getattr(sys, "stdin", None) is None or getattr(sys, "stdout", None) is None:
            import ctypes
            k32 = ctypes.windll.kernel32
            k32.GetStdHandle.restype = ctypes.c_void_p
            hin, hout = k32.GetStdHandle(-10), k32.GetStdHandle(-11)
            return (os.fdopen(msvcrt.open_osfhandle(hin, os.O_RDONLY | os.O_BINARY), "rb", 0),
                    os.fdopen(msvcrt.open_osfhandle(hout, os.O_WRONLY | os.O_BINARY), "wb", 0))
    if getattr(sys, "stdin", None) is not None and getattr(sys, "stdout", None) is not None:
        return sys.stdin.buffer, sys.stdout.buffer
    return os.fdopen(0, "rb", 0), os.fdopen(1, "wb", 0)


def launch_command(frozen=None, executable=None, script=None):
    frozen = getattr(sys, "frozen", False) if frozen is None else frozen
    exe = executable or sys.executable
    if frozen:
        return [exe, "--minimized"]
    if os.name == "nt" and os.path.basename(exe).lower() == "python.exe" and os.path.exists(os.path.join(os.path.dirname(exe), "pythonw.exe")):
        exe = os.path.join(os.path.dirname(exe), "pythonw.exe")  # no console window for the GUI
    return [exe, script or os.path.abspath(__file__), "--minimized"]


def launch_opendm():
    """Start the OpenDM window (minimized, so it sits in the tray) detached from the browser's process tree."""
    kw = {}
    if os.name == "nt":
        kw["creationflags"] = 0x00000008 | 0x00000200 | 0x08000000  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW
    else:
        kw["start_new_session"] = True
    subprocess.Popen(launch_command(), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True, **kw)


class HostError(Exception):
    """A problem to report back to the extension (shown in its panel)."""


class NativeHost:
    """The program the browser starts. It trusts only the registered extension IDs, never prints anything but protocol
    bytes, and forwards `add` jobs to the OpenDM server using the pairing token it reads from disk."""
    LOCAL = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # never route 127.0.0.1 through a system proxy

    def __init__(self, state_dir=None, launch=None, sleep=time.sleep, wait_seconds=20):
        self.state_dir = state_dir or CFG_DIR
        self.launch, self.sleep, self.wait_seconds = launch or launch_opendm, sleep, wait_seconds

    def log(self, text):
        try:
            p = os.path.join(self.state_dir, "native-host.log")
            os.makedirs(self.state_dir, exist_ok=True)
            if os.path.exists(p) and os.path.getsize(p) > 100_000:
                os.remove(p)
            with open(p, "a", encoding="utf-8") as f:
                f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + text.rstrip() + "\n")
        except OSError:
            pass

    def settings(self):
        d = read_json(os.path.join(self.state_dir, "settings.json"), {})
        return d if isinstance(d, dict) else {}

    def port(self):
        p = read_json(os.path.join(self.state_dir, "api.json"), {}).get("port")
        return p if isinstance(p, int) and 0 < p < 65536 else API_PORT

    def _call(self, method, path, body=None):
        """HTTP status of a call to OpenDM's local server (0 if nothing is listening)."""
        req = urllib.request.Request(f"http://127.0.0.1:{self.port()}{path}", method=method,
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"X-OpenDM-Token": get_token(self.state_dir), "Content-Type": "application/json"})
        try:
            with self.LOCAL.open(req, timeout=10) as r:
                return r.status
        except urllib.error.HTTPError as e:
            return e.code
        except (urllib.error.URLError, OSError):
            return 0

    def _json_call(self, path, body, timeout=80):
        """(HTTP status, parsed JSON) of a POST to OpenDM's local server; (0, None) if nothing is listening."""
        req = urllib.request.Request(f"http://127.0.0.1:{self.port()}{path}", method="POST", data=json.dumps(body).encode(),
                                     headers={"X-OpenDM-Token": get_token(self.state_dir), "Content-Type": "application/json"})
        try:
            with self.LOCAL.open(req, timeout=timeout) as r:
                return r.status, json.loads(r.read(4 << 20) or b"{}")
        except urllib.error.HTTPError as e:
            return e.code, None
        except (urllib.error.URLError, OSError, ValueError):
            return 0, None

    def alive(self):
        return self._call("GET", "/ping") != 0

    def ensure_running(self):
        if self.alive():
            return
        if not self.settings().get("autostart_from_browser", True):
            raise HostError("OpenDM isn't running. Start it, or tick 'Start OpenDM when the browser sends a download' in Browser setup.")
        self.log("OpenDM not running: starting it")
        self.launch()
        end = time.time() + self.wait_seconds
        while time.time() < end:
            self.sleep(0.25)
            if self.alive():
                return
        raise HostError("OpenDM was started but did not become ready in time. Open it manually and try again.")

    def handle(self, msg):
        cmd = msg.get("cmd") if isinstance(msg, dict) else None
        if cmd == "ping":
            return {"ok": True, "app": "OpenDM", "version": __version__, "running": self.alive(), "port": self.port(),
                    "autostart": bool(self.settings().get("autostart_from_browser", True))}
        if cmd == "start":
            self.ensure_running()
            return {"ok": True}
        if cmd == "formats":  # the browser's "Download this video" menu asks which qualities a page offers
            job = msg.get("job")
            if not isinstance(job, dict) or not str(job.get("url", "")).lower().startswith(("http://", "https://")):
                raise HostError("That isn't a web address OpenDM can read.")
            self.ensure_running()
            code, obj = self._json_call("/formats", {k: job[k] for k in ("url", "referer", "cookie", "userAgent") if job.get(k) not in (None, "")})
            if code == 200 and isinstance(obj, dict):
                return obj
            raise HostError({401: "OpenDM refused the request (pairing token mismatch). Restart OpenDM and try again.", 0: "Could not reach OpenDM."}.get(code, f"OpenDM answered with error {code}."))
        if cmd == "add":
            job = msg.get("job")
            if not isinstance(job, dict) or not str(job.get("url", "")).lower().startswith(("http://", "https://")):
                raise HostError("That isn't a web address OpenDM can download.")
            self.ensure_running()
            code = self._call("POST", "/add", {k: job[k] for k in HOST_JOB_KEYS if job.get(k) not in (None, "")})
            if code == 200:
                return {"ok": True}
            raise HostError({401: "OpenDM refused the request (pairing token mismatch). Restart OpenDM and try again.",
                             400: "OpenDM did not accept that address.", 0: "Could not reach OpenDM."}.get(code, f"OpenDM answered with error {code}."))
        raise HostError("Unknown command.")

    def origin_allowed(self, args):
        extra = self.settings().get("extension_ids", [])
        for a in args:
            if a.startswith("chrome-extension://"):
                return a in [f"chrome-extension://{i}/" for i in extension_ids(extra if isinstance(extra, list) else [])]
            if a.startswith("moz-extension://"):
                return False
        if len(args) >= 2 and _basename(args[0]) == NATIVE_HOST_NAME + ".json":  # Firefox: <manifest path> <add-on id>
            return args[1] == FIREFOX_EXTENSION_ID
        return True  # started by hand with --native-host (testing)

    def serve(self, args, stdin=None, stdout=None):
        args = [a for a in args if a != "--native-host"]
        if not self.origin_allowed(args):
            self.log(f"refused caller: {args}")
            return 2
        if stdin is None or stdout is None:
            stdin, stdout = _std_binary_streams()
        while True:
            try:
                msg = nm_read(stdin)
            except (ValueError, struct.error, OSError) as e:
                self.log(f"bad message: {e}")
                try:
                    nm_write(stdout, {"ok": False, "error": f"Bad message: {e}"})
                except OSError:
                    pass
                return 1
            if msg is None:
                return 0
            try:
                reply = self.handle(msg)
            except HostError as e:
                reply = {"ok": False, "error": str(e)}
            except Exception as e:
                self.log(f"unexpected: {e!r}")
                reply = {"ok": False, "error": f"Host error: {e}"}
            try:
                nm_write(stdout, reply)
            except OSError:  # the browser closed the pipe
                return 0


# ============================== system tray ==============================
class Tray:
    """System tray icon through the optional `pystray` + `Pillow` packages (Windows and Linux; not macOS, where
    pystray insists on the main thread that the GUI already uses). Menu clicks arrive on pystray's own thread, so
    they are only queued as short command strings; the GUI loop picks them up with poll() and runs them."""
    LIMITS = (0, 256, 512, 1024, 5120)  # KB/s choices in the "Speed limit" submenu (0 = no limit)

    def __init__(self, png_bytes, get_limit=lambda: 0):
        self.cmds, self.icon, self.error = queue.Queue(), None, ""
        if platform.system() == "Darwin":
            self.error = "The tray icon isn't available on macOS."
            return
        try:
            import pystray
            from PIL import Image
            image = Image.open(io.BytesIO(png_bytes))
            image.load()
        except ImportError:
            self.error = "Install the tray add-on first:  pip install pystray pillow"
            return
        except Exception as e:  # e.g. no display / no tray support on this desktop
            self.error = f"The system tray isn't available here ({e})"
            return

        def cmd(name):
            return lambda *a: self.cmds.put(name)

        def label(kb):
            return "No limit" if not kb else f"{kb // 1024} MB/s" if kb % 1024 == 0 else f"{kb} KB/s"
        limits = pystray.Menu(*[pystray.MenuItem(label(kb), cmd(f"limit:{kb}"), radio=True,
                                                 checked=(lambda item, kb=kb: get_limit() == kb)) for kb in self.LIMITS])
        menu = pystray.Menu(
            pystray.MenuItem("Show OpenDM", cmd("show"), default=True),
            pystray.MenuItem("Pause all", cmd("pause_all")),
            pystray.MenuItem("Resume all", cmd("resume_all")),
            pystray.MenuItem("Speed limit", limits),
            pystray.MenuItem("Open download folder", cmd("folder")),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit OpenDM", cmd("quit")))
        self.icon = pystray.Icon("OpenDM", image, "OpenDM", menu)

    @property
    def available(self):
        return self.icon is not None

    def start(self):
        try:
            self.icon.run_detached()
        except Exception as e:
            self.error, self.icon = f"The system tray isn't available here ({e})", None

    def stop(self):
        if self.icon is not None:
            try:
                self.icon.stop()
            except Exception:
                pass

    def set_title(self, text):
        if self.icon is not None:
            try:
                self.icon.title = text[:127]  # Windows truncates tooltips at 127 characters
            except Exception:
                pass

    def notify(self, message, title="OpenDM"):
        if self.icon is not None:
            try:
                self.icon.notify(message[:250], title)
            except Exception:
                pass

    def poll(self):
        """Commands clicked in the tray menu since the last call."""
        out = []
        while True:
            try:
                out.append(self.cmds.get_nowait())
            except queue.Empty:
                return out


# ============================== GUI (IDM-style window) ==============================
tk = ttk = messagebox = filedialog = simpledialog = None  # tkinter is imported lazily so the CLI works without it

AFTER = {"none": "Do nothing", "exit": "Exit OpenDM", "shutdown": "Shut down computer"}
MIT_TEXT = """MIT License

Copyright (c) 2026 OpenDM contributors

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
documentation files (the "Software"), to deal in the Software without restriction, including without limitation
the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and
to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of
the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO
THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF
CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
IN THE SOFTWARE."""

# (icon, label, App method) - None draws a separator, like IDM's toolbar groups
TOOLBAR = (("add", "Add URL", "add_dialog"), ("resume", "Resume", "resume"), ("stop", "Stop", "stop"), ("stopall", "Stop All", "stop_all"),
           ("delete", "Delete", "delete"), ("delc", "Delete C.", "delete_completed"), None,
           ("options", "Options", "options_dialog"), ("scheduler", "Scheduler", "scheduler_dialog"), None,
           ("startq", "Start Queue", "start_queue"), ("stopq", "Stop Queue", "stop_queue"), None,
           ("grabber", "Grabber", "grabber_dialog"), ("browser", "Browser", "pairing_dialog"))


def _load_tk():
    global tk, ttk, messagebox, filedialog, simpledialog
    import tkinter as _tk
    from tkinter import ttk as _ttk, messagebox as _mb, filedialog as _fd, simpledialog as _sd
    tk, ttk, messagebox, filedialog, simpledialog = _tk, _ttk, _mb, _fd, _sd


class App:
    """The main window, laid out like IDM's classic interface: menu bar, icon toolbar, a navigation tree on the left
    (All Downloads > categories, Unfinished, Finished, Grabber projects, Queues) and the download list on the right."""

    def __init__(self, port=API_PORT, minimized=False):
        _load_tk()
        self.port, self.minimized = port, minimized
        self.mgr = Manager()
        st = self.mgr.settings
        self.root = root = tk.Tk()
        root.title("OpenDM - Open Download Manager")
        root.geometry("1220x700")
        root.minsize(860, 480)
        try:  # window / taskbar icon (embedded, so it also works from a single-file build)
            root._icon = tk.PhotoImage(data=ICON_B64)
            root.iconphoto(True, root._icon)
        except tk.TclError:
            pass
        self.style = ttk.Style(root)
        if platform.system() == "Linux" and "clam" in self.style.theme_names():
            self.style.theme_use("clam")
        self.style.configure("Treeview", rowheight=22)
        self.style.configure("Toolbutton", padding=(8, 4))
        self.icons = {k: tk.PhotoImage(data=v) for k, v in UI_ICONS.items()}
        self.folder = tk.StringVar(value=st.get("folder") or os.path.join(os.path.expanduser("~"), "Downloads"))
        st["folder"] = self.folder.get()
        self.conns = tk.IntVar(value=int(st.get("connections") or 8))
        self.limit_var = tk.IntVar(value=int(st.get("limit_kb") or 0))
        self.limit_var.trace_add("write", self._on_limit)
        self.flt = tk.StringVar(value="all")  # "all" | "unfinished" | "finished" | "cat:X" | "queue:X" | "project:X" | "queues" | "projects"
        self.sort = ("", False)
        self.show_side, self.show_toolbar, self.show_status, self.show_graph = (tk.BooleanVar(value=True) for _ in range(4))
        self.tray, self.last_tip, self.seen, self.hint_shown = None, "", {}, False
        self.side_map = {}      # navigation tree row id -> (label, filter)
        self.menu_rules = []    # (menu, index, rule): which entries are greyed out for the current selection
        self.note, self._quiet = ("", 0), False
        self.captured, self.pending_urls, self.pwins = queue.Queue(), set(), {}  # links from the browser awaiting confirmation; open confirm dialogs; open progress windows
        for d in self.mgr.items:
            d.announced = d.status == "Completed"  # only downloads that finish during this session pop up "Download complete"
        self.api_srv = start_api(self.mgr, lambda: (self.folder.get(), self.conns.get()), port, confirm=self._capture)
        self.build_menu()
        self.build_ui()
        self.build_context_menus()
        self.bind_keys()
        self.rebuild_side()
        root.protocol("WM_DELETE_WINDOW", self.request_close)

    # ------------------------------------------------------------------ small helpers
    def _on_limit(self, *_):
        try:
            self.mgr.set_limit_kb(self.limit_var.get())
        except tk.TclError:  # box is empty or mid-edit
            pass

    def selected(self):
        return [self.mgr.items[int(i)] for i in self.tree.selection() if int(i) < len(self.mgr.items)]

    def cur_queue(self):
        f = self.flt.get()
        return f[6:] if f.startswith("queue:") else MAIN_QUEUE

    def info(self, title, text, parent=None):
        messagebox.showinfo(title, text, parent=parent or self.root)

    # ------------------------------------------------------------------ menu bar
    def build_menu(self):
        bar = tk.Menu(self.root, tearoff=0)
        self.root.config(menu=bar)
        self.menubar = bar

        def menu(label, underline=0):
            m = tk.Menu(bar, tearoff=0, postcommand=self.update_state)
            bar.add_cascade(label=label, menu=m, underline=underline)
            return m

        def item(m, label, cmd, accel=None, need=None):
            m.add_command(label=label, command=cmd, accelerator=accel)
            if need:
                self.menu_rules.append((m, m.index("end"), need))

        tasks = menu("Tasks")
        item(tasks, "Add new download...", self.add_dialog, "Ctrl+N")
        item(tasks, "Add batch download from clipboard", self.add_from_clipboard)
        item(tasks, "Run site grabber...", self.grabber_dialog)
        tasks.add_separator()
        item(tasks, "Export download list...", self.export_list)
        item(tasks, "Import download list...", self.import_list)
        tasks.add_separator()
        item(tasks, "Exit", self.on_close, "Alt+F4")

        f = menu("File")
        item(f, "Open", self.open_file, "Enter", "done")
        item(f, "Open folder", self.open_folder, None, "sel")
        item(f, "Move/Rename...", self.rename_file, "F2", "done1")
        item(f, "Redownload", self.redownload, None, "sel")
        f.add_separator()
        item(f, "Properties...", self.properties_dialog, "Alt+Enter", "sel1")
        item(f, "Copy address", self.copy_address, "Ctrl+C", "sel")

        d = menu("Downloads")
        item(d, "Resume", self.resume, "Ctrl+R", "resumable")
        item(d, "Stop", self.stop, "Ctrl+S", "active")
        item(d, "Stop All", self.stop_all, None, "anyactive")
        d.add_separator()
        item(d, "Delete", self.delete, "Del", "sel")
        item(d, "Delete completed", self.delete_completed, None, "anydone")
        d.add_separator()
        self.menu_cat = tk.Menu(d, tearoff=0, postcommand=lambda: self._fill_cat_menu(self.menu_cat))
        d.add_cascade(label="Move to category", menu=self.menu_cat)
        self.menu_rules.append((d, d.index("end"), "sel"))
        self.menu_que = tk.Menu(d, tearoff=0, postcommand=lambda: self._fill_queue_menu(self.menu_que))
        d.add_cascade(label="Move to queue", menu=self.menu_que)
        self.menu_rules.append((d, d.index("end"), "sel"))
        d.add_separator()
        item(d, "Start queue", self.start_queue)
        item(d, "Stop queue", self.stop_queue)
        item(d, "New queue...", self.new_queue)
        d.add_separator()
        item(d, "Speed limiter...", self.speed_dialog)
        item(d, "Limit selected downloads...", self.limit_selected, None, "sel")
        item(d, "Scheduler...", self.scheduler_dialog)
        item(d, "Categories...", self.categories_dialog)
        d.add_separator()
        item(d, "Options...", self.options_dialog)

        v = menu("View")
        for label, var, cmd in (("Toolbar", self.show_toolbar, self.apply_layout), ("Categories pane", self.show_side, self.apply_layout),
                                ("Speed graph", self.show_graph, self.apply_layout), ("Status bar", self.show_status, self.apply_layout)):
            v.add_checkbutton(label=label, variable=var, command=cmd)
        v.add_separator()
        sortm = tk.Menu(v, tearoff=0)
        for key, title, _ in COLUMNS:
            sortm.add_command(label=title, command=lambda k=key: self.sort_by(k, toggle=False))
        sortm.add_separator()
        sortm.add_command(label="Original order", command=lambda: self.sort_by("", toggle=False))
        v.add_cascade(label="Sort by", menu=sortm)
        item(v, "Refresh", self.tick_once, "F5")

        h = menu("Help")
        item(h, "Quick help", self.help_dialog)
        item(h, "Browser extension setup...", self.pairing_dialog)
        item(h, "Keyboard shortcuts", self.shortcuts_dialog)
        h.add_separator()
        item(h, "About OpenDM", self.about_dialog)

        r = menu("Registration")
        item(r, "Registration status...", self.registration_dialog)
        item(r, "License (MIT)...", self.license_dialog)

    # ------------------------------------------------------------------ window layout
    def build_ui(self):
        root = self.root
        root.grid_columnconfigure(0, weight=1)
        root.grid_rowconfigure(1, weight=1)
        # toolbar: big icon above the label, flat buttons, grouped by separators
        self.toolbar = ttk.Frame(root, padding=(4, 3))
        self.toolbar.grid(row=0, column=0, sticky="ew")
        self.tbtn = {}
        for entry in TOOLBAR:
            if entry is None:
                ttk.Separator(self.toolbar, orient="vertical").pack(side="left", fill="y", padx=5, pady=3)
                continue
            icon, label, meth = entry
            b = ttk.Button(self.toolbar, text=label, image=self.icons[icon], compound="top", style="Toolbutton", command=getattr(self, meth))
            b.pack(side="left", padx=1)
            self.tbtn[icon] = b
        # navigation tree (left) + download list (right) in a resizable split
        self.body = ttk.PanedWindow(root, orient="horizontal")
        self.body.grid(row=1, column=0, sticky="nsew", padx=4, pady=(0, 2))
        self.side_frame = ttk.Frame(self.body)
        self.side = ttk.Treeview(self.side_frame, show="tree", selectmode="browse")
        self.side.column("#0", width=250, minwidth=150)
        self.side.pack(fill="both", expand=True)
        self.side.bind("<<TreeviewSelect>>", self.on_side)
        self.list_frame = ttk.Frame(self.body)
        self.tree = ttk.Treeview(self.list_frame, columns=[c[0] for c in COLUMNS], show="headings", selectmode="extended")
        for key, title, w in COLUMNS:
            self.tree.heading(key, text=title, command=lambda k=key: self.sort_by(k))
            self.tree.column(key, width=w, minwidth=30, anchor="center" if key == "q" else "w", stretch=key in ("name", "desc"))
        sb = ttk.Scrollbar(self.list_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.update_state())
        self.tree.bind("<Double-1>", self.on_double_click)
        self.body.add(self.side_frame, weight=0)
        self.body.add(self.list_frame, weight=1)
        # optional speed graph (View menu)
        self.gframe = ttk.Frame(root)
        self.gframe.grid(row=2, column=0, sticky="ew", padx=4, pady=(2, 0))
        self.gtitle = ttk.Label(self.gframe, text="", anchor="w")
        self.gtitle.pack(fill="x")
        self.gcv = tk.Canvas(self.gframe, height=110, bg="white", highlightthickness=1, highlightbackground="#d1d5db")
        self.gcv.pack(fill="x")
        self.mapcv = tk.Canvas(self.gframe, height=16, bg="#f3f4f6", highlightthickness=0)
        self.mapcv.pack(fill="x", pady=(4, 0))
        # status bar
        self.status = ttk.Label(root, text="", anchor="w", relief="sunken", padding=(6, 2))
        self.status.grid(row=3, column=0, sticky="ew")
        self.apply_layout()

    def apply_layout(self):
        if self.show_toolbar.get():
            self.toolbar.grid()
        else:
            self.toolbar.grid_remove()
        if self.show_graph.get():
            self.gframe.grid()
        else:
            self.gframe.grid_remove()
        if self.show_status.get():
            self.status.grid()
        else:
            self.status.grid_remove()
        shown = str(self.side_frame) in [str(p) for p in self.body.panes()]
        if self.show_side.get() and not shown:
            self.body.insert(0, self.side_frame, weight=0)
        elif not self.show_side.get() and shown:
            self.body.forget(self.side_frame)

    # ------------------------------------------------------------------ navigation tree
    def rebuild_side(self):
        want = self.flt.get()
        self.side.delete(*self.side.get_children())
        self.side_map.clear()

        def add(parent, iid, label, flt, icon):
            self.side.insert(parent, "end", iid=iid, text="  " + label, image=self.icons[icon], open=True)
            self.side_map[iid] = (label, flt)
        add("", "all", "All Downloads", "all", "t_all")
        for n, c in enumerate(self.mgr.settings["categories"]):
            add("all", f"c:{n}", c["name"], "cat:" + c["name"], "t_folder")
        add("", "unfinished", "Unfinished", "unfinished", "t_unfinished")
        add("", "finished", "Finished", "finished", "t_finished")
        add("", "projects", "Grabber projects", "projects", "t_grabber")
        for n, p in enumerate(self.mgr.projects()):
            add("projects", f"p:{n}", p, "project:" + p, "t_folder")
        add("", "queues", "Queues", "queues", "t_queue")
        for n, q in enumerate(self.mgr.settings["queues"]):
            add("queues", f"q:{n}", q, "queue:" + q, "t_queue")
        iid = next((i for i, (_, f) in self.side_map.items() if f == want), "all")
        self.flt.set(self.side_map[iid][1])
        self._select_side(iid)
        self.update_side()

    def _select_side(self, iid):
        self._quiet = True
        self.side.selection_set(iid)
        self._quiet = False

    def update_side(self):
        for iid, (label, f) in self.side_map.items():
            n = sum(matches_filter(d, f) for d in self.mgr.items)
            self.side.item(iid, text=f"  {label} ({n})")

    def on_side(self, _=None):
        sel = self.side.selection()
        if getattr(self, "_quiet", False) or not sel or sel[0] not in self.side_map:
            return
        self.flt.set(self.side_map[sel[0]][1])
        self.draw_list()
        self.update_state()

    # ------------------------------------------------------------------ download list
    def sort_by(self, col, toggle=True):
        old, rev = self.sort
        self.sort = (col, (not rev) if (toggle and col == old and col) else False)
        for key, title, _ in COLUMNS:
            arrow = (" \u25b2" if not self.sort[1] else " \u25bc") if key == self.sort[0] else ""
            self.tree.heading(key, text=title + arrow)
        self.draw_list()

    def row_values(self, d, qpos):
        return (d.label, qpos.get(id(d), ""), human(d.size) if d.size > 0 else "", status_text(d), fmt_left(d.eta_sec),
                fmt_rate(d.speed) if d.status in ACTIVE else "", fmt_when(d.last_try), d.desc)

    def draw_list(self):
        qpos = queue_positions(self.mgr.items)
        rows = [(i, d) for i, d in enumerate(self.mgr.items) if matches_filter(d, self.flt.get())]
        col, rev = self.sort
        if col:
            rows.sort(key=lambda t: sort_key(t[1], col, qpos), reverse=rev)
        ids = [str(i) for i, _ in rows]
        if list(self.tree.get_children()) == ids:  # same rows: update in place, so selection and scroll position stay
            for i, d in rows:
                self.tree.item(str(i), values=self.row_values(d, qpos))
            return
        sel = self.tree.selection()
        self.tree.delete(*self.tree.get_children())
        for i, d in rows:
            self.tree.insert("", "end", iid=str(i), values=self.row_values(d, qpos))
        for i in sel:
            if self.tree.exists(i):
                self.tree.selection_add(i)

    def on_double_click(self, e):
        if not self.tree.identify_row(e.y):
            return
        sel = self.selected()
        if sel and sel[0].status == "Completed":
            self.open_file()
        elif sel:
            self.progress_window(sel[0])

    # ------------------------------------------------------------------ enabling / greying out
    def flags(self):
        sel, items = self.selected(), self.mgr.items
        return {"sel": bool(sel), "sel1": len(sel) == 1,
                "done": any(d.status == "Completed" and d.path and os.path.exists(d.path) for d in sel),
                "done1": len(sel) == 1 and sel[0].status == "Completed" and bool(sel[0].path),
                "resumable": any(d.status in ("Paused", "Error", "Queued") for d in sel),
                "active": any(d.status in ACTIVE or d.status == "Queued" for d in sel),
                "anyactive": any(d.status in ACTIVE or d.status == "Queued" for d in items),
                "anydone": any(d.status == "Completed" for d in items)}

    def update_state(self):
        fl = self.flags()
        for icon, rule in (("resume", "resumable"), ("stop", "active"), ("stopall", "anyactive"), ("delete", "sel"), ("delc", "anydone")):
            self.tbtn[icon].state(["!disabled"] if fl[rule] else ["disabled"])
        for m, idx, rule in self.menu_rules:
            m.entryconfig(idx, state="normal" if fl[rule] else "disabled")

    def tick_once(self):
        self.draw_list()
        self.update_side()

    # ------------------------------------------------------------------ context menus + keyboard
    def _fill_cat_menu(self, menu):
        menu.delete(0, "end")
        for c in self.mgr.settings["categories"]:
            menu.add_command(label=c["name"], command=lambda n=c["name"]: self.move_selected_category(n))

    def _fill_queue_menu(self, menu):
        menu.delete(0, "end")
        for q in self.mgr.settings["queues"]:
            menu.add_command(label=q, command=lambda n=q: self.move_selected_queue(n))

    def build_context_menus(self):
        self.ctx = ctx = tk.Menu(self.root, tearoff=0)
        self.ctx_rules = {"Open": "done", "Open folder": "sel", "Resume": "resumable", "Stop": "active", "Delete": "sel", "Move to category": "sel",
                          "Move to queue": "sel", "Limit speed...": "sel", "Redownload": "sel", "Properties...": "sel1", "Copy address": "sel"}
        ctx.add_command(label="Open", command=self.open_file)
        ctx.add_command(label="Open folder", command=self.open_folder)
        ctx.add_separator()
        ctx.add_command(label="Resume", command=self.resume)
        ctx.add_command(label="Stop", command=self.stop)
        ctx.add_command(label="Delete", command=self.delete)
        ctx.add_separator()
        cat = tk.Menu(ctx, tearoff=0, postcommand=lambda: self._fill_cat_menu(cat))
        que = tk.Menu(ctx, tearoff=0, postcommand=lambda: self._fill_queue_menu(que))
        ctx.add_cascade(label="Move to category", menu=cat)
        ctx.add_cascade(label="Move to queue", menu=que)
        ctx.add_separator()
        ctx.add_command(label="Limit speed...", command=self.limit_selected)
        ctx.add_command(label="Redownload", command=self.redownload)
        ctx.add_command(label="Properties...", command=self.properties_dialog)
        ctx.add_command(label="Copy address", command=self.copy_address)
        for ev in ("<Button-3>", "<Button-2>"):  # Button-2 is the right button on macOS
            self.tree.bind(ev, self.show_ctx)
            self.side.bind(ev, self.show_side_ctx)

    def _popup(self, menu, e):
        try:
            menu.tk_popup(e.x_root, e.y_root)
        finally:
            menu.grab_release()

    def show_ctx(self, e):
        iid = self.tree.identify_row(e.y)
        if not iid:
            return
        if iid not in self.tree.selection():
            self.tree.selection_set(iid)
        fl = self.flags()
        for i in range(self.ctx.index("end") + 1):
            if self.ctx.type(i) != "separator":
                self.ctx.entryconfig(i, state="normal" if fl[self.ctx_rules[self.ctx.entrycget(i, "label")]] else "disabled")
        self._popup(self.ctx, e)

    def show_side_ctx(self, e):
        iid = self.side.identify_row(e.y)
        if iid not in self.side_map:
            return
        self.side.selection_set(iid)
        label, f = self.side_map[iid]
        m = tk.Menu(self.root, tearoff=0)
        if f.startswith("queue:"):
            m.add_command(label="Start queue", command=self.start_queue)
            m.add_command(label="Stop queue", command=self.stop_queue)
            m.add_separator()
            m.add_command(label="Rename...", command=lambda: self.rename_queue_node(label), state="disabled" if label == MAIN_QUEUE else "normal")
            m.add_command(label="Delete queue", command=lambda: self.delete_queue_node(label), state="disabled" if label == MAIN_QUEUE else "normal")
        elif iid == "queues":
            m.add_command(label="New queue...", command=self.new_queue)
        elif f.startswith("project:"):
            m.add_command(label="Forget this project label", command=lambda: self.forget_project(label))
        elif f.startswith("cat:") or iid == "all":
            m.add_command(label="Edit categories...", command=self.categories_dialog)
        else:
            return
        self._popup(m, e)

    def bind_keys(self):
        r, t = self.root, self.tree
        r.bind("<Control-n>", lambda e: self.add_dialog())
        r.bind("<Control-r>", lambda e: self.resume())
        r.bind("<Control-s>", lambda e: self.stop())
        r.bind("<F5>", lambda e: self.tick_once())
        t.bind("<Delete>", lambda e: self.delete())
        t.bind("<F2>", lambda e: self.rename_file())
        t.bind("<Alt-Return>", lambda e: self.properties_dialog())
        t.bind("<Return>", lambda e: self.open_file() if self.flags()["done"] else self.properties_dialog())
        t.bind("<Control-c>", lambda e: self.copy_address())
        t.bind("<Control-a>", lambda e: (t.selection_set(t.get_children()), "break")[1])

    # ------------------------------------------------------------------ download actions
    def after_change(self):
        self.rebuild_side()
        self.draw_list()
        self.update_state()

    def flash(self, text, seconds=6):
        self.note = (text, time.time() + seconds)

    def resume_items(self, ds):
        for d in ds:
            if d.status in ("Paused", "Error", "Queued"):
                d.status, d.force, d.auto_paused = "Queued", True, False  # a manual start ignores the scheduler window

    def pause_items(self, ds):
        for d in ds:
            d.auto_paused = d.force = False
            if d.status in ACTIVE:
                d.pause()
            elif d.status == "Queued":
                d.status = "Paused"

    def resume(self):
        self.resume_items(self.selected())
        self.draw_list()
        self.update_state()

    def stop(self):
        self.pause_items(self.selected())
        self.draw_list()
        self.update_state()

    def stop_all(self):
        self.pause_items(self.mgr.items)
        self.draw_list()
        self.update_state()

    def confirm_delete(self, sel):
        """IDM-style confirmation. Returns (confirmed, also_delete_finished_files_from_disk)."""
        win = tk.Toplevel(self.root)
        win.title("Delete")
        win.transient(self.root)
        win.resizable(False, False)
        out, also = {"ok": False}, tk.BooleanVar(value=False)
        names = ", ".join(d.label[:40] for d in sel[:3]) + (" ..." if len(sel) > 3 else "")
        ttk.Label(win, text=f"Delete {len(sel)} download{'s' if len(sel) > 1 else ''} from the list?\n{names}", justify="left").pack(padx=16, pady=(16, 8))
        if any(d.status == "Completed" for d in sel):
            ttk.Checkbutton(win, text="Also delete the downloaded file(s) from disk", variable=also).pack(anchor="w", padx=16)
        row = ttk.Frame(win)
        row.pack(pady=14)
        ttk.Button(row, text="Yes", command=lambda: (out.update(ok=True), win.destroy())).pack(side="left", padx=6)
        ttk.Button(row, text="No", command=win.destroy).pack(side="left", padx=6)
        win.grab_set()
        win.wait_window()
        return out["ok"], also.get()

    def delete(self):
        sel = self.selected()
        if not sel:
            return
        ok, files = self.confirm_delete(sel)
        if ok:
            for d in sel:
                self.mgr.remove(d, delete_file=True, delete_completed=files)
            self.after_change()

    def delete_completed(self):
        done = [d for d in self.mgr.items if d.status == "Completed"]
        if not done:
            return self.info("Delete completed", "There are no completed downloads in the list.")
        if messagebox.askyesno("Delete completed", f"Remove {len(done)} completed download(s) from the list?\n(The files stay on disk.)", parent=self.root):
            for d in done:
                self.mgr.remove(d)
            self.after_change()

    def start_queue(self):
        q = self.cur_queue()
        self.flash(f"Queue '{q}': {self.mgr.start_queue(q)} download(s) queued to start")
        self.draw_list()
        self.update_state()

    def stop_queue(self):
        q = self.cur_queue()
        self.flash(f"Queue '{q}': {self.mgr.stop_queue(q)} download(s) stopped")
        self.draw_list()
        self.update_state()

    def new_queue(self):
        name = simpledialog.askstring("New queue", "Name of the new queue:", parent=self.root)
        if name is not None:
            try:
                self.mgr.add_queue(name)
            except ValueError as e:
                return messagebox.showerror("New queue", str(e), parent=self.root)
            self.after_change()

    def rename_queue_node(self, old):
        new = simpledialog.askstring("Rename queue", "New name:", initialvalue=old, parent=self.root)
        if new is not None and new != old:
            try:
                self.flt.set("queue:" + self.mgr.rename_queue(old, new))
            except ValueError as e:
                return messagebox.showerror("Rename queue", str(e), parent=self.root)
            self.after_change()

    def delete_queue_node(self, name):
        if messagebox.askyesno("Delete queue", f"Delete the queue '{name}'?\nIts downloads move to '{MAIN_QUEUE}'.", parent=self.root):
            self.mgr.delete_queue(name)
            self.flt.set("queues")
            self.after_change()

    def forget_project(self, name):
        for d in self.mgr.items:
            if d.project == name:
                d.project = ""
        self.flt.set("projects")
        self.after_change()

    def move_selected_category(self, cat):
        for d in self.selected():
            try:
                self.mgr.move_to_category(d, cat)
            except ValueError as e:
                self.info("Move to category", f"{d.label}\n\n{e}")
                break
        self.after_change()

    def move_selected_queue(self, name):
        for d in self.selected():
            self.mgr.move_to_queue(d, name)
        self.after_change()

    # ------------------------------------------------------------------ file actions
    def open_path(self, target):
        try:
            if platform.system() == "Windows":
                os.startfile(target)
            elif platform.system() == "Darwin":
                subprocess.Popen(["open", target])
            else:
                subprocess.Popen(["xdg-open", target])
        except OSError as e:
            messagebox.showerror("OpenDM", f"Couldn't open {target}\n{e}", parent=self.root)

    def open_file(self):
        sel = self.selected()
        if sel and sel[0].status == "Completed" and sel[0].path and os.path.exists(sel[0].path):
            self.open_path(sel[0].path)

    def open_folder(self):
        sel = self.selected()
        target = (os.path.dirname(sel[0].path) if sel and sel[0].path else sel[0].folder if sel else self.folder.get())
        self.open_path(target if os.path.isdir(target) else self.folder.get())

    def rename_file(self):
        sel = self.selected()
        if len(sel) != 1 or sel[0].status != "Completed" or not sel[0].path or not os.path.exists(sel[0].path):
            return
        d = sel[0]
        new = simpledialog.askstring("Move/Rename", "New file name:", initialvalue=os.path.basename(d.path), parent=self.root)
        if not new or new == os.path.basename(d.path):
            return
        target = os.path.join(os.path.dirname(d.path), clean_name(new))
        if os.path.exists(target):
            return messagebox.showerror("Move/Rename", "A file with that name already exists.", parent=self.root)
        try:
            os.rename(d.path, target)
        except OSError as e:
            return messagebox.showerror("Move/Rename", str(e), parent=self.root)
        d.path, d.name = target, os.path.basename(target)
        self.draw_list()

    def redownload(self):
        sel = self.selected()
        if not sel or not messagebox.askyesno("Redownload", f"Download {len(sel)} item(s) again?\nA finished file is kept; the new copy gets a number.", parent=self.root):
            return
        for d in sel:
            kw = dict(referer=d.referer, cookie=d.cookie, ua=d.ua, hint=d.hint, queue=d.queue, project=d.project, desc=d.desc)
            kind = "hls" if isinstance(d, HlsDownload) else "mux" if isinstance(d, MuxDownload) else "dash" if isinstance(d, DashDownload) else "ytdlp" if isinstance(d, ExtractDownload) else None
            if kind in ("dash", "ytdlp"):
                kw.update(quality=d.quality)
            if kind == "hls":
                kw.update(quality=d.quality, pick_bw=d.pick_bw)
            elif kind == "mux":
                kw["audio_url"] = d.audio_url
            self.mgr.add(d.url, d.base, d.connections, kind=kind, **kw)
        self.after_change()

    def limit_selected(self):
        sel = self.selected()
        if not sel:
            return
        kb = simpledialog.askinteger("Speed limit", "Limit for the selected download(s) in KBytes/sec (0 = no limit):",
                                     parent=self.root, minvalue=0, initialvalue=sel[0].limit_kb)
        if kb is not None:
            for d in sel:
                d.set_limit(kb)

    def copy_address(self):
        sel = self.selected()
        if sel:
            self.root.clipboard_clear()
            self.root.clipboard_append("\n".join(d.url for d in sel))

    def properties_dialog(self):
        sel = self.selected()
        if len(sel) != 1:
            return
        d = sel[0]
        win = tk.Toplevel(self.root)
        win.title("Download properties")
        win.transient(self.root)
        rows = (("File name", d.name or "(not known yet)"), ("Save to", os.path.dirname(d.path) if d.path else d.folder), ("Address", d.url),
                ("Referer", d.referer or ""), ("Category", d.category), ("Queue", d.queue), ("Status", status_text(d)),
                ("Size", human(d.size) if d.size > 0 else "unknown"), ("Downloaded", human(d.done)), ("Last try", fmt_when(d.last_try)))
        for r, (k, v) in enumerate(rows):
            ttk.Label(win, text=k + ":").grid(row=r, column=0, sticky="e", padx=(14, 6), pady=3)
            e = ttk.Entry(win, width=70)
            e.insert(0, v)
            e.state(["readonly"])
            e.grid(row=r, column=1, padx=(0, 14), pady=3)
        ttk.Label(win, text="Description:").grid(row=len(rows), column=0, sticky="e", padx=(14, 6), pady=3)
        desc = tk.StringVar(value=d.desc)
        ttk.Entry(win, textvariable=desc, width=70).grid(row=len(rows), column=1, padx=(0, 14), pady=3)
        row = ttk.Frame(win)
        row.grid(row=len(rows) + 1, column=0, columnspan=2, pady=12)
        ttk.Button(row, text="OK", command=lambda: (setattr(d, "desc", desc.get().strip()), win.destroy(), self.draw_list())).pack(side="left", padx=6)
        ttk.Button(row, text="Cancel", command=win.destroy).pack(side="left", padx=6)

    # ------------------------------------------------------------------ IDM-style windows: confirm, progress, complete
    def _guard(self, fn, *a):
        """Run one step of the refresh loop; a bug in a dialog must never stop the whole GUI from updating."""
        try:
            fn(*a)
        except Exception:
            import traceback
            traceback.print_exc()

    def _front(self, win):
        """Bring a dialog to the front even when the main window is hidden in the tray."""
        try:
            win.deiconify()
            win.lift()
            win.attributes("-topmost", True)
            win.after(400, lambda: win.winfo_exists() and win.attributes("-topmost", False))
            win.focus_force()
        except tk.TclError:
            pass

    def _capture(self, job):
        """Called from the API thread for every link the browser sends."""
        now = time.time()
        seen = self.__dict__.setdefault("recent_captures", {})   # url -> time it was last offered
        for u in [u for u, t in seen.items() if now - t > CAPTURE_DEDUPE_SECS]:
            seen.pop(u, None)
        if job["url"] in seen or job["url"] in self.pending_urls:  # the browser sometimes sends a link twice
            return
        seen[job["url"]] = now
        if self.mgr.settings.get("confirm_captured", True):
            if self.captured.qsize() >= CAPTURE_MAX_QUEUE:  # a page spraying links: don't bury the user in windows
                return
            job["_t"] = now
            self.captured.put(job)  # the GUI thread shows the confirmation window
        else:
            self.mgr.add(job["url"], job["folder"], job["connections"], kind=job["kind"], **job["kw"])

    def drain_captured(self):
        # One confirmation window at a time; the rest wait in the queue (and expire if the user never gets to them).
        while not self.pending_urls:
            try:
                job = self.captured.get_nowait()
            except queue.Empty:
                return
            if time.time() - job.get("_t", time.time()) > CAPTURE_EXPIRE_SECS:
                continue
            self.confirm_dialog(job)

    def confirm_dialog(self, job):
        """'Download File Info': a captured link only starts when the user clicks Start Download."""
        url, kw = job["url"], job["kw"]
        kind = job["kind"] or detect_kind(url)
        self.pending_urls.add(url)
        win = tk.Toplevel(self.root)
        win.title("Download File Info")
        win.resizable(False, False)
        folder, cat, que = tk.StringVar(value=job["folder"]), tk.StringVar(value="Automatic"), tk.StringVar(value=MAIN_QUEUE)
        guess = kw.get("hint") or urllib.parse.unquote(os.path.basename(urllib.parse.urlparse(url).path))
        if kind in ("hls", "mux") and guess and not os.path.splitext(guess)[1]:
            guess += ".mp4"
        if kind == "ytdlp" and not kw.get("hint"):
            guess = ""
        name = tk.StringVar(value=clean_name(guess) if guess else "(taken from the video page)" if kind == "ytdlp" else "(not known yet)")
        size = tk.StringVar(value={"hls": "Video stream (HLS)", "mux": "Video + audio (merged when done)", "dash": "Video stream (DASH, merged by ffmpeg)",
                                   "ytdlp": "Video page - best available quality, found by yt-dlp"}.get(kind, "Checking..."))
        body = ttk.Frame(win, padding=14)
        body.pack(fill="both", expand=True)
        for r, (label, var) in enumerate((("Address", None), ("File name", name), ("File size", size))):
            ttk.Label(body, text=label + ":").grid(row=r, column=0, sticky="e", padx=(0, 8), pady=3)
            if label == "File size":
                ttk.Label(body, textvariable=var).grid(row=r, column=1, columnspan=3, sticky="w", pady=3)
                continue
            e = ttk.Entry(body, width=70, textvariable=var)
            if var is None:
                e.insert(0, url)
            e.state(["readonly"])
            e.grid(row=r, column=1, columnspan=3, sticky="we", pady=3)
        ttk.Label(body, text="Category:").grid(row=3, column=0, sticky="e", padx=(0, 8), pady=3)
        ttk.Combobox(body, textvariable=cat, state="readonly", width=18, values=["Automatic"] + [c["name"] for c in self.mgr.settings["categories"]]).grid(row=3, column=1, sticky="w", pady=3)
        ttk.Label(body, text="Queue:").grid(row=3, column=2, sticky="e", padx=(12, 8))
        ttk.Combobox(body, textvariable=que, state="readonly", width=24, values=self.mgr.settings["queues"]).grid(row=3, column=3, sticky="w")
        ttk.Label(body, text="Save to:").grid(row=4, column=0, sticky="e", padx=(0, 8), pady=3)
        ttk.Entry(body, textvariable=folder, width=56).grid(row=4, column=1, columnspan=2, sticky="we", pady=3)
        ttk.Button(body, text="Browse...", command=lambda: folder.set(filedialog.askdirectory(parent=win, initialdir=folder.get()) or folder.get())).grid(row=4, column=3, sticky="w", padx=6)
        ttk.Label(body, text="Nothing is downloaded until you click Start Download.", foreground="#6b7280").grid(row=5, column=1, columnspan=3, sticky="w", pady=(6, 0))

        def close():
            self.pending_urls.discard(url)
            if win.winfo_exists():
                win.destroy()

        def go(later):
            dest = folder.get().strip() or self.folder.get()
            d = self.mgr.add(url, dest, job["connections"], kind=kind, queue=que.get(), later=later, **kw)
            if cat.get() != "Automatic":
                try:
                    self.mgr.move_to_category(d, cat.get())
                except ValueError as e:
                    messagebox.showerror("OpenDM", str(e), parent=win)
            close()
            self.after_change()
            if not later:
                self.progress_window(d)

        row = ttk.Frame(win)
        row.pack(pady=(0, 12))
        ttk.Button(row, text="Start Download", command=lambda: go(False)).pack(side="left", padx=6)
        ttk.Button(row, text="Download Later", command=lambda: go(True)).pack(side="left", padx=6)
        ttk.Button(row, text="Cancel", command=close).pack(side="left", padx=6)
        win.protocol("WM_DELETE_WINDOW", close)
        self._front(win)

        if kind is None:  # like IDM, ask the server for the real name and size (a 1-byte request; no file data is downloaded)
            box = {}

            def probe():
                try:
                    t = Download(url, folder.get(), 1, referer=kw.get("referer"), cookie=kw.get("cookie"), ua=kw.get("ua"), hint=kw.get("hint"))
                    t._probe()
                    box["r"] = (t.name, t.size)
                except Exception:
                    box["r"] = (None, -1)
            threading.Thread(target=probe, daemon=True).start()

            def poll():
                if not win.winfo_exists():
                    return
                if "r" not in box:
                    return win.after(300, poll)
                n, z = box["r"]
                if n:
                    name.set(n)
                size.set(f"{human(z)} ({z:,} Bytes)" if z and z > 0 else "unknown")
            poll()

    def progress_window(self, d):
        """The live window of a running download: Download status / Speed Limiter / Options on completion."""
        old = self.pwins.get(id(d))
        if old and old["win"].winfo_exists():
            return self._front(old["win"])
        st = self.mgr.settings
        win = tk.Toplevel(self.root)
        win.minsize(540, 120)
        nb = ttk.Notebook(win)
        nb.pack(fill="both", expand=True, padx=8, pady=(8, 0))

        # ---- tab 1: Download status
        t1 = ttk.Frame(nb, padding=10)
        nb.add(t1, text="Download status")
        url_e = ttk.Entry(t1)
        url_e.insert(0, d.url)
        url_e.state(["readonly"])
        url_e.pack(fill="x", pady=(0, 6))
        grid = ttk.Frame(t1)
        grid.pack(fill="x")
        lab = {}
        for r, k in enumerate(("Status", "File size", "Downloaded", "Transfer rate", "Time left", "Resume capability")):
            ttk.Label(grid, text=k, width=18).grid(row=r, column=0, sticky="w", pady=1)
            lab[k] = ttk.Label(grid, text="")
            lab[k].grid(row=r, column=1, sticky="w", pady=1)
        bar = ttk.Progressbar(t1, maximum=100)
        bar.pack(fill="x", pady=(8, 4))
        cv = tk.Canvas(t1, height=14, highlightthickness=0, background="white")
        cv.pack(fill="x", pady=(0, 6))
        details = ttk.Frame(t1)
        details.pack(fill="both", expand=True)
        tv = ttk.Treeview(details, columns=("n", "got", "info"), show="headings", height=8, selectmode="none")
        for c, text, w, anchor in (("n", "N.", 50, "center"), ("got", "Downloaded", 130, "e"), ("info", "Info", 260, "w")):
            tv.heading(c, text=text)
            tv.column(c, width=w, anchor=anchor)
        sb = ttk.Scrollbar(details, orient="vertical", command=tv.yview)
        tv.configure(yscrollcommand=sb.set)
        tv.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        # ---- tab 2: Speed Limiter
        t2 = ttk.Frame(nb, padding=14)
        nb.add(t2, text="Speed Limiter")
        use, kb = tk.BooleanVar(value=d.limit_kb > 0), tk.IntVar(value=d.limit_kb or 100)
        spin = ttk.Spinbox(t2, from_=1, to=10_000_000, width=9, textvariable=kb)
        lim_note = ttk.Label(t2, foreground="#6b7280")

        def apply_limit(*_):
            try:
                v = max(1, int(kb.get()))
            except (tk.TclError, ValueError):
                v = d.limit_kb or 100
            kb.set(v)
            d.set_limit(v if use.get() else 0)
            spin.state(["!disabled"] if use.get() else ["disabled"])
            lim_note.config(text=f"This download is limited to {v} KBytes/sec." if use.get() else "No limit for this download (the global limit still applies).")
        ttk.Checkbutton(t2, text="Use speed limiter", variable=use, command=apply_limit).pack(anchor="w")
        r2 = ttk.Frame(t2)
        r2.pack(anchor="w", pady=8)
        ttk.Label(r2, text="Maximum download speed (KBytes/sec):").pack(side="left")
        spin.pack(side="left", padx=8)
        ttk.Button(r2, text="Apply", command=apply_limit).pack(side="left")
        lim_note.pack(anchor="w")
        apply_limit()

        # ---- tab 3: Options on completion
        t3 = ttk.Frame(nb, padding=14)
        nb.add(t3, text="Options on completion")
        show = tk.BooleanVar(value=st.get("show_complete_dialog", True) if d.show_complete is None else d.show_complete)
        opn, ext, off = tk.BooleanVar(value=d.open_when_done), tk.BooleanVar(value=st.get("after") == "exit"), tk.BooleanVar(value=st.get("after") == "shutdown")

        def sync(which=""):
            d.show_complete, d.open_when_done = show.get(), opn.get()
            if which == "exit" and ext.get():
                off.set(False)
            if which == "off" and off.get():
                ext.set(False)
            st["after"] = "exit" if ext.get() else "shutdown" if off.get() else "none"
            self.mgr.save_settings()
        for text, var, which in (("Show download complete dialog", show, ""), ("Open the file when done", opn, ""),
                                 ("Exit OpenDM when all downloads are done", ext, "exit"), ("Turn off computer when all downloads are done", off, "off")):
            ttk.Checkbutton(t3, text=text, variable=var, command=lambda w=which: sync(w)).pack(anchor="w", pady=3)

        # ---- buttons
        btns = ttk.Frame(win)
        btns.pack(fill="x", padx=8, pady=8)
        hide_txt = tk.StringVar(value="<< Hide details")
        pause_txt = tk.StringVar(value="Pause")

        def toggle_details():
            if details.winfo_ismapped():
                details.pack_forget()
                hide_txt.set("Show details >>")
            else:
                details.pack(fill="both", expand=True)
                hide_txt.set("<< Hide details")

        def pause_resume():
            (self.pause_items if d.status in ACTIVE or d.status == "Queued" else self.resume_items)([d])
            self.draw_list()
            self.update_state()

        def close():
            self.pwins.pop(id(d), None)
            if win.winfo_exists():
                win.destroy()

        def cancel():
            self.pause_items([d])
            self.draw_list()
            close()
        ttk.Button(btns, textvariable=hide_txt, command=toggle_details).pack(side="left")
        ttk.Button(btns, text="Cancel", command=cancel).pack(side="right", padx=(6, 0))
        ttk.Button(btns, textvariable=pause_txt, command=pause_resume).pack(side="right")
        win.protocol("WM_DELETE_WINDOW", close)

        cache = {"rows": None}

        def refresh():
            if d not in self.mgr.items or d.status == "Completed":
                return close()  # a finished download is announced by the Download complete dialog
            pct = d.percent
            win.title(f"{pct:.0f}% - {d.label[:40]}" if d.status in ACTIVE else d.label[:50])
            lab["Status"].config(text=status_text(d))
            lab["File size"].config(text=f"{human(d.size)} ({d.size:,} Bytes)" if d.size > 0 else "unknown")
            lab["Downloaded"].config(text=f"{human(d.done)} ({pct:.2f}%)" if d.size > 0 or pct else human(d.done))
            lab["Transfer rate"].config(text=fmt_rate(d.speed) or "-")
            lab["Time left"].config(text=fmt_left(d.eta_sec) or "-")
            lab["Resume capability"].config(text="Yes" if d.ranges or isinstance(d, (HlsDownload, MuxDownload)) else "No" if d.name else "Unknown")
            bar["value"] = pct
            pause_txt.set("Pause" if d.status in ACTIVE or d.status == "Queued" else "Resume")
            cv.delete("all")
            W, H = max(cv.winfo_width(), 100), max(cv.winfo_height(), 10)
            for x0, x1, xf in d.segment_map():
                cv.create_rectangle(x0 * W, 1, x1 * W, H - 1, fill="#e5e7eb", outline="#9ca3af")
                if xf > x0:
                    cv.create_rectangle(x0 * W, 1, xf * W, H - 1, fill="#2563eb", outline="")
            rows = d.segment_rows()
            if rows != cache["rows"]:
                cache["rows"] = rows
                have = tv.get_children()
                for i, vals in enumerate(rows):
                    if i < len(have):
                        tv.item(have[i], values=vals)
                    else:
                        tv.insert("", "end", values=vals)
                for iid in have[len(rows):]:
                    tv.delete(iid)
        self.pwins[id(d)] = {"win": win, "d": d, "refresh": refresh}
        refresh()
        self._front(win)

    def update_progress_windows(self):
        for key, w in list(self.pwins.items()):
            if w["win"].winfo_exists():
                w["refresh"]()
            else:
                self.pwins.pop(key, None)

    def check_completed(self):
        """Pops up the Download complete dialog once for each download that finishes."""
        for d in list(self.mgr.items):
            if d.status != "Completed" or d.announced:
                continue
            d.announced = True
            w = self.pwins.pop(id(d), None)
            if w and w["win"].winfo_exists():
                w["win"].destroy()
            if d.open_when_done and d.path and os.path.exists(d.path):
                self.open_path(d.path)
            show = self.mgr.settings.get("show_complete_dialog", True) if d.show_complete is None else d.show_complete
            if show:
                self.complete_dialog(d)

    def open_with(self, path, parent):
        system = platform.system()
        try:
            if system == "Windows":
                subprocess.Popen(["rundll32.exe", "shell32.dll,OpenAs_RunDLL", path])
                return
            prog = filedialog.askopenfilename(parent=parent, title="Open with...", initialdir="/Applications" if system == "Darwin" else "/usr/bin")
            if prog:
                subprocess.Popen(["open", "-a", prog, path] if system == "Darwin" else [prog, path])
        except OSError as e:
            messagebox.showerror("OpenDM", f"Couldn't open the file with that program.\n{e}", parent=parent)

    def reveal(self, path):
        """Open the file's folder, with the file highlighted where the OS supports it."""
        try:
            if platform.system() == "Windows":
                subprocess.Popen(["explorer", "/select," + os.path.normpath(path)])
            elif platform.system() == "Darwin":
                subprocess.Popen(["open", "-R", path])
            else:
                self.open_path(os.path.dirname(path))
        except OSError as e:
            messagebox.showerror("OpenDM", f"Couldn't open the folder.\n{e}", parent=self.root)

    def complete_dialog(self, d):
        """IDM's 'Download complete' window."""
        path = os.path.normpath(d.path) if d.path else ""
        try:
            nbytes = os.path.getsize(path)
        except OSError:
            nbytes = d.size
        win = tk.Toplevel(self.root)
        win.title("Download complete")
        win.resizable(False, False)
        top = ttk.Frame(win, padding=(14, 12, 14, 4))
        top.pack(fill="x")
        try:
            win._icon = tk.PhotoImage(data=ICON_B64).subsample(3)
            ttk.Label(top, image=win._icon).pack(side="left", padx=(0, 12))
        except tk.TclError:
            pass
        head = ttk.Frame(top)
        head.pack(side="left", fill="x")
        ttk.Label(head, text="Download complete", font=("TkDefaultFont", 12, "bold")).pack(anchor="w")
        ttk.Label(head, text=f"{size_mb_bytes(nbytes)} downloaded").pack(anchor="w", pady=(2, 0))
        body = ttk.Frame(win, padding=(14, 6))
        body.pack(fill="x")
        for r, (k, v) in enumerate((("Address", d.url), ("Saved to", path))):
            ttk.Label(body, text=k + ":").grid(row=r, column=0, sticky="e", padx=(0, 8), pady=3)
            e = ttk.Entry(body, width=64)
            e.insert(0, v)
            e.state(["readonly"])
            e.grid(row=r, column=1, sticky="we", pady=3)
        never = tk.BooleanVar(value=False)

        def finish():
            if never.get():
                self.mgr.settings["show_complete_dialog"] = False
                self.mgr.save_settings()
            if win.winfo_exists():
                win.destroy()

        def need_file():
            if path and os.path.exists(path):
                return True
            messagebox.showerror("OpenDM", "The file is no longer there.", parent=win)
            return False
        row = ttk.Frame(win)
        row.pack(pady=(8, 4))
        for text, fn in (("Open", lambda: need_file() and (self.open_path(path), finish())),
                         ("Open with...", lambda: need_file() and (self.open_with(path, win), finish())),
                         ("Open folder", lambda: need_file() and (self.reveal(path), finish())),
                         ("Close", finish)):
            ttk.Button(row, text=text, command=fn).pack(side="left", padx=5)
        ttk.Checkbutton(win, text="Don't show this dialog again", variable=never).pack(anchor="w", padx=14, pady=(4, 12))
        win.protocol("WM_DELETE_WINDOW", finish)
        self._front(win)

    # ------------------------------------------------------------------ adding downloads
    def add_dialog(self):
        win = tk.Toplevel(self.root)
        win.title("Enter new address to download")
        win.transient(self.root)
        ttk.Label(win, text="Address (one link per line):").pack(anchor="w", padx=14, pady=(14, 2))
        txt = tk.Text(win, width=78, height=6)
        txt.pack(padx=14)
        try:
            clip = self.root.clipboard_get().strip()
            if clip.lower().startswith(("http://", "https://")):
                txt.insert("1.0", clip)
        except tk.TclError:
            pass
        row = ttk.Frame(win)
        row.pack(fill="x", padx=14, pady=10)
        cat, que = tk.StringVar(value="Automatic"), tk.StringVar(value=self.cur_queue())
        ttk.Label(row, text="Category:").pack(side="left")
        ttk.Combobox(row, textvariable=cat, state="readonly", width=16, values=["Automatic"] + [c["name"] for c in self.mgr.settings["categories"]]).pack(side="left", padx=(4, 16))
        ttk.Label(row, text="Queue:").pack(side="left")
        ttk.Combobox(row, textvariable=que, state="readonly", width=22, values=self.mgr.settings["queues"]).pack(side="left", padx=4)
        ttk.Label(win, text="Save to: " + self.folder.get(), foreground="#6b7280").pack(anchor="w", padx=14)

        def go(later):
            urls = [x.strip() for x in txt.get("1.0", "end").splitlines() if x.strip().lower().startswith(("http://", "https://"))]
            if not urls:
                return self.info("Add URL", "Paste at least one http:// or https:// address.", win)
            added = []
            for u in urls:
                d = self.mgr.add(u, self.folder.get(), self.conns.get(), queue=que.get(), later=later)
                if cat.get() != "Automatic":
                    self.mgr.move_to_category(d, cat.get())
                added.append(d)
            win.destroy()
            self.after_change()
            if not later:
                for d in added[:3]:  # a window per download, but not a screenful for a big batch
                    self.progress_window(d)
        btns = ttk.Frame(win)
        btns.pack(pady=(10, 14))
        ttk.Button(btns, text="Start Download", command=lambda: go(False)).pack(side="left", padx=6)
        ttk.Button(btns, text="Download Later", command=lambda: go(True)).pack(side="left", padx=6)
        ttk.Button(btns, text="Cancel", command=win.destroy).pack(side="left", padx=6)
        txt.focus_set()

    def add_from_clipboard(self):
        try:
            text = self.root.clipboard_get()
        except tk.TclError:
            text = ""
        urls = list(dict.fromkeys(re.findall(r"https?://[^\s<>\"']+", text)))
        if not urls:
            return self.info("Batch download", "The clipboard doesn't contain any http:// or https:// links.")
        if messagebox.askyesno("Batch download", f"Download {len(urls)} link(s) from the clipboard?", parent=self.root):
            for u in urls:
                self.mgr.add(u, self.folder.get(), self.conns.get(), queue=self.cur_queue())
            self.after_change()

    def grabber_dialog(self):
        """Site grabber: scan a page (and optionally the pages it links to) for downloadable files."""
        win = tk.Toplevel(self.root)
        win.title("Site Grabber")
        win.transient(self.root)
        top = ttk.Frame(win)
        top.pack(fill="x", padx=12, pady=(12, 4))
        start = tk.StringVar()
        try:
            clip = self.root.clipboard_get().strip()
            if clip.lower().startswith(("http://", "https://")) and "\n" not in clip:
                start.set(clip)
        except tk.TclError:
            pass
        ttk.Label(top, text="Start page:").grid(row=0, column=0, sticky="w")
        ttk.Entry(top, textvariable=start, width=70).grid(row=0, column=1, columnspan=3, sticky="ew", padx=6)
        ttk.Label(top, text="Look in:").grid(row=1, column=0, sticky="w", pady=6)
        depth = tk.StringVar(value="This page only")
        ttk.Combobox(top, textvariable=depth, state="readonly", width=44,
                     values=["This page only", "This page and the pages it links to on the same site (up to 20)"]).grid(row=1, column=1, sticky="w", padx=6)
        kinds = ttk.LabelFrame(win, text="Find these files")
        kinds.pack(fill="x", padx=12, pady=4)
        checks = {}
        for c in self.mgr.settings["categories"]:
            if c["exts"]:
                checks[c["name"]] = tk.BooleanVar(value=True)
                ttk.Checkbutton(kinds, text=c["name"], variable=checks[c["name"]]).pack(side="left", padx=8, pady=4)
        anyfile = tk.BooleanVar(value=False)
        ttk.Checkbutton(kinds, text="Any other file", variable=anyfile).pack(side="left", padx=8)
        state = ttk.Label(win, text="Enter a page address and press Explore.", foreground="#6b7280")
        state.pack(anchor="w", padx=12)
        box = ttk.Frame(win)
        box.pack(fill="both", expand=True, padx=12, pady=4)
        res = ttk.Treeview(box, columns=("name", "type", "page"), show="headings", selectmode="extended", height=12)
        for k, t, w in (("name", "File name", 260), ("type", "Type", 60), ("page", "Found on", 340)):
            res.heading(k, text=t)
            res.column(k, width=w, anchor="w")
        sb = ttk.Scrollbar(box, orient="vertical", command=res.yview)
        res.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        res.pack(side="left", fill="both", expand=True)
        found, title, inbox = {}, {"t": ""}, queue.Queue()
        bottom = ttk.Frame(win)
        bottom.pack(fill="x", padx=12, pady=(4, 12))
        project = tk.StringVar()
        ttk.Label(bottom, text="Project name:").pack(side="left")
        ttk.Entry(bottom, textvariable=project, width=24).pack(side="left", padx=6)

        def explore():
            url = start.get().strip()
            if not url.lower().startswith(("http://", "https://")):
                return self.info("Site Grabber", "Enter an http:// or https:// address.", win)
            wanted = {e for c in self.mgr.settings["categories"] if c["name"] in checks and checks[c["name"]].get() for e in c["exts"]}
            if not wanted and not anyfile.get():
                return self.info("Site Grabber", "Tick at least one kind of file.", win)
            state.config(text="Exploring...")
            btn.state(["disabled"])
            deep = 1 if depth.get().startswith("This page and") else 0

            def work():
                try:
                    inbox.put(("ok", *grab_site(url, wanted, deep, anyfile.get())))
                except Exception as e:
                    inbox.put(("err", str(e)))
            threading.Thread(target=work, daemon=True).start()
            poll()

        def poll():
            try:
                msg = inbox.get_nowait()
            except queue.Empty:
                return win.after(150, poll) if win.winfo_exists() else None
            btn.state(["!disabled"])
            if msg[0] == "err":
                return state.config(text="Couldn't read that page: " + msg[1])
            res.delete(*res.get_children())
            found.clear()
            for n, f in enumerate(msg[1]):
                found[str(n)] = f
                res.insert("", "end", iid=str(n), values=(f["name"], f["ext"], f["page"]))
            res.selection_set(res.get_children())
            title["t"] = msg[2]
            project.set(project.get() or msg[2][:40] or urllib.parse.urlparse(start.get()).netloc)
            state.config(text=f"Found {len(found)} file(s). Select the ones you want." if found else "No matching files found on that page.")

        def grab(later):
            chosen = [found[i] for i in res.selection() if i in found]
            if not chosen:
                return self.info("Site Grabber", "Select at least one file.", win)
            name = project.get().strip() or urllib.parse.urlparse(start.get()).netloc
            for f in chosen:
                self.mgr.add(f["url"], self.folder.get(), self.conns.get(), queue=self.cur_queue(), project=name, later=later, referer=f["page"])
            state.config(text=f"Added {len(chosen)} download(s) to project '{name}'.")
            self.after_change()
        btn = ttk.Button(top, text="Explore", command=explore)
        btn.grid(row=1, column=2, padx=6)
        ttk.Button(bottom, text="Close", command=win.destroy).pack(side="right")
        ttk.Button(bottom, text="Download Later", command=lambda: grab(True)).pack(side="right", padx=6)
        ttk.Button(bottom, text="Start Download", command=lambda: grab(False)).pack(side="right")
        ttk.Button(bottom, text="Select none", command=lambda: res.selection_set(())).pack(side="right", padx=12)
        ttk.Button(bottom, text="Select all", command=lambda: res.selection_set(res.get_children())).pack(side="right")

    def export_list(self):
        p = filedialog.asksaveasfilename(parent=self.root, title="Export download list", defaultextension=".json", initialfile="opendm-downloads.json",
                                         filetypes=[("OpenDM list", "*.json"), ("All files", "*.*")])
        if p:
            self.flash(f"Exported {self.mgr.export_list(p)} download(s) to {p}")

    def import_list(self):
        p = filedialog.askopenfilename(parent=self.root, title="Import download list",
                                       filetypes=[("OpenDM list or text with links", "*.json *.txt *.csv *.lst"), ("All files", "*.*")])
        if p:
            try:
                n = self.mgr.import_list(p, self.folder.get())
            except OSError as e:
                return messagebox.showerror("Import", str(e), parent=self.root)
            self.flash(f"Imported {n} download(s); they are stopped until you start them")
            self.after_change()

    # ------------------------------------------------------------------ dialogs: options, speed limiter, scheduler
    def text_dialog(self, title, text, width=78, height=22):
        win = tk.Toplevel(self.root)
        win.title(title)
        win.transient(self.root)
        box = ttk.Frame(win)
        box.pack(fill="both", expand=True, padx=10, pady=(10, 4))
        t = tk.Text(box, width=width, height=height, wrap="word", padx=8, pady=6)
        sb = ttk.Scrollbar(box, orient="vertical", command=t.yview)
        t.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        t.pack(side="left", fill="both", expand=True)
        t.insert("1.0", text)
        t.config(state="disabled")
        ttk.Button(win, text="Close", command=win.destroy).pack(pady=8)

    def options_dialog(self):
        st = self.mgr.settings
        win = tk.Toplevel(self.root)
        win.title("Options")
        win.transient(self.root)
        nb = ttk.Notebook(win)
        nb.pack(fill="both", expand=True, padx=10, pady=(10, 4))
        v = {k: tk.BooleanVar(value=bool(st.get(k))) for k in ("tray", "close_to_tray", "notify", "start_minimized", "auto_sort", "show_complete_dialog", "confirm_captured")}
        folder, conns = tk.StringVar(value=self.folder.get()), tk.IntVar(value=self.conns.get())
        maxa, limit = tk.IntVar(value=self.mgr.max_active), tk.IntVar(value=self.limit_var.get())
        quality = tk.StringVar(value=str(st.get("quality") or "Best"))

        gen = ttk.Frame(nb, padding=14)
        nb.add(gen, text="General")
        for key, text in (("tray", "Show an icon in the system tray"), ("close_to_tray", "Closing the window keeps OpenDM running in the tray"),
                          ("notify", "Notify me when a download finishes or fails"), ("start_minimized", "Start minimized (to the tray if it is on)"),
                          ("show_complete_dialog", "Show the \"Download complete\" dialog when a download finishes"),
                          ("confirm_captured", "Ask before starting links sent from the browser")):
            ttk.Checkbutton(gen, text=text, variable=v[key]).pack(anchor="w", pady=3)
        ttk.Label(gen, wraplength=420, justify="left", foreground="#6b7280",
                  text="The tray icon needs the optional add-on:  pip install pystray pillow  (Windows and Linux; not macOS).").pack(anchor="w", pady=(10, 0))

        sv = ttk.Frame(nb, padding=14)
        nb.add(sv, text="Save to")
        ttk.Label(sv, text="Default download folder:").pack(anchor="w")
        fr = ttk.Frame(sv)
        fr.pack(anchor="w", pady=(2, 10))
        ttk.Entry(fr, textvariable=folder, width=52).pack(side="left")
        ttk.Button(fr, text="Browse...", command=lambda: folder.set(filedialog.askdirectory(parent=win, initialdir=folder.get()) or folder.get())).pack(side="left", padx=6)
        ttk.Checkbutton(sv, text="Save each download in its category's folder (Video, Documents, ...)", variable=v["auto_sort"]).pack(anchor="w", pady=3)
        ttk.Button(sv, text="Edit categories...", command=self.categories_dialog).pack(anchor="w", pady=10)

        cn = ttk.Frame(nb, padding=14)
        nb.add(cn, text="Connection")
        for r, (label, var, lo, hi) in enumerate((("Connections per download (new downloads):", conns, 1, 32), ("Maximum simultaneous downloads:", maxa, 1, 10),
                                                   ("Speed limit in KBytes/sec (0 = unlimited):", limit, 0, 10_000_000))):
            ttk.Label(cn, text=label).grid(row=r, column=0, sticky="w", pady=5)
            ttk.Spinbox(cn, from_=lo, to=hi, width=9, textvariable=var).grid(row=r, column=1, padx=10)
        ttk.Label(cn, text="Video quality for HLS streams:").grid(row=3, column=0, sticky="w", pady=5)
        ttk.Combobox(cn, textvariable=quality, state="readonly", width=8, values=["Best", "1080", "720", "480", "360"]).grid(row=3, column=1, padx=10)

        br = ttk.Frame(nb, padding=14)
        nb.add(br, text="Browser")
        ttk.Label(br, wraplength=440, justify="left", text=(f"The browser extension talks to OpenDM on 127.0.0.1:{self.port}"
                                                            + ("." if self.api_srv else " - but that port is busy right now; restart with  python opendm.py -p 6801")
                                                            + "\nPaste this pairing token into the extension's options page:")).pack(anchor="w")
        e = ttk.Entry(br, width=52)
        e.insert(0, get_token())
        e.state(["readonly"])
        e.pack(anchor="w", pady=8)
        ttk.Button(br, text="Copy token", command=lambda: (self.root.clipboard_clear(), self.root.clipboard_append(get_token()))).pack(anchor="w")

        def num(var, lo, hi, default):
            try:
                return max(lo, min(hi, int(var.get())))
            except (tk.TclError, ValueError):
                return default

        def ok():
            f = folder.get().strip()
            if f:
                self.folder.set(f)
                st["folder"] = f
            self.conns.set(num(conns, 1, 32, 8))
            st["connections"] = self.conns.get()
            self.mgr.max_active = st["max_active"] = num(maxa, 1, 10, 3)
            self.limit_var.set(num(limit, 0, 10_000_000, 0))
            st["quality"] = 0 if quality.get() == "Best" else int(quality.get())
            st["auto_sort"] = v["auto_sort"].get()
            want = v["tray"].get()
            if want != bool(self.tray):
                err = self.set_tray(want)
                if err and want:
                    messagebox.showinfo("System tray", err, parent=win)
                    want = False
            st.update(tray=want, close_to_tray=v["close_to_tray"].get(), notify=v["notify"].get(), start_minimized=v["start_minimized"].get(),
                      show_complete_dialog=v["show_complete_dialog"].get(), confirm_captured=v["confirm_captured"].get())
            self.mgr.save_settings()
            win.destroy()
            self.flash("Options saved")
        row = ttk.Frame(win)
        row.pack(pady=(4, 12))
        ttk.Button(row, text="OK", command=ok).pack(side="left", padx=6)
        ttk.Button(row, text="Cancel", command=win.destroy).pack(side="left", padx=6)

    def speed_dialog(self):
        win = tk.Toplevel(self.root)
        win.title("Speed limiter")
        win.transient(self.root)
        on, kb = tk.BooleanVar(value=self.limit_var.get() > 0), tk.IntVar(value=self.limit_var.get() or 512)
        ttk.Checkbutton(win, text="Use speed limiter", variable=on).pack(anchor="w", padx=14, pady=(14, 6))
        row = ttk.Frame(win)
        row.pack(padx=14, anchor="w")
        ttk.Label(row, text="Maximum download speed (KBytes/sec):").pack(side="left")
        ttk.Spinbox(row, from_=1, to=10_000_000, width=9, textvariable=kb).pack(side="left", padx=8)

        def ok():
            try:
                self.limit_var.set(max(1, int(kb.get())) if on.get() else 0)
            except (tk.TclError, ValueError):
                return
            win.destroy()
        r2 = ttk.Frame(win)
        r2.pack(pady=14)
        ttk.Button(r2, text="OK", command=ok).pack(side="left", padx=6)
        ttk.Button(r2, text="Cancel", command=win.destroy).pack(side="left", padx=6)

    def scheduler_dialog(self):
        st = self.mgr.settings
        win = tk.Toplevel(self.root)
        win.title("Scheduler")
        win.transient(self.root)
        on, a, b = tk.BooleanVar(value=st["sched_on"]), tk.StringVar(value=st["start"]), tk.StringVar(value=st["stop"])
        after = tk.StringVar(value=AFTER[st["after"]])
        ttk.Checkbutton(win, text="Only download between these times (24-hour HH:MM)", variable=on).pack(anchor="w", padx=12, pady=(12, 4))
        row = ttk.Frame(win)
        row.pack(anchor="w", padx=12)
        ttk.Label(row, text="From").pack(side="left")
        ttk.Entry(row, textvariable=a, width=6).pack(side="left", padx=4)
        ttk.Label(row, text="to").pack(side="left")
        ttk.Entry(row, textvariable=b, width=6).pack(side="left", padx=4)
        ttk.Label(win, text="When all downloads finish (one time):").pack(anchor="w", padx=12, pady=(12, 2))
        ttk.Combobox(win, textvariable=after, values=list(AFTER.values()), state="readonly").pack(anchor="w", padx=12)

        def ok():
            try:
                parse_hm(a.get())
                parse_hm(b.get())
            except ValueError:
                return messagebox.showerror("Scheduler", "Times must look like 01:30", parent=win)
            st.update(sched_on=on.get(), start=a.get().strip(), stop=b.get().strip(), after=[k for k, x in AFTER.items() if x == after.get()][0])
            self.mgr.save_settings()
            win.destroy()
        ttk.Button(win, text="Save", command=ok).pack(pady=12)

    def countdown(self, sec=60):
        win = tk.Toplevel(self.root)
        win.title("Shutting down")
        lab = ttk.Label(win, padding=15)
        lab.pack()
        state = {"n": sec}
        ttk.Button(win, text="Cancel shutdown", command=win.destroy).pack(pady=8)

        def step():
            if state["n"] <= 0:
                self.mgr.shutdown()
                power_off()
                return self.root.destroy()
            lab.config(text=f"All downloads finished.\nShutting down the computer in {state['n']} s")
            state["n"] -= 1
            win.after(1000, step)
        step()

    def after_done(self):
        """Runs the one-time 'when finished' action. Returns True if the app is closing."""
        act, self.mgr.settings["after"] = self.mgr.settings["after"], "none"
        self.mgr.save_settings()
        if act == "exit":
            self.on_close()
            return True
        if act == "shutdown":
            self.countdown()
        return False

    # ------------------------------------------------------------------ dialogs: categories
    def categories_dialog(self):
        mgr = self.mgr
        win = tk.Toplevel(self.root)
        win.title("Categories")
        win.transient(self.root)
        orig = [c["name"] for c in mgr.settings["categories"]]
        cats = [dict(c, _was=c["name"]) for c in copy.deepcopy(mgr.settings["categories"])]  # edit a copy; OK applies it
        auto = tk.BooleanVar(value=mgr.settings.get("auto_sort", True))
        name, exts, fold, sites = tk.StringVar(), tk.StringVar(), tk.StringVar(), tk.StringVar()
        cur, entries = {"i": 0}, {}
        left = ttk.Frame(win)
        left.pack(side="left", fill="y", padx=(10, 6), pady=10)
        lb = tk.Listbox(left, width=20, height=13, exportselection=False)
        lb.pack(fill="y", expand=True)
        right = ttk.Frame(win)
        right.pack(side="left", fill="both", expand=True, padx=(0, 10), pady=10)

        def field(label, var, key):
            ttk.Label(right, text=label).pack(anchor="w")
            entries[key] = ttk.Entry(right, textvariable=var, width=54)
            entries[key].pack(anchor="w", pady=(0, 7))
        field("Name", name, "name")
        field("File types (comma separated, e.g. mp4, mkv)", exts, "exts")
        ttk.Label(right, text="Save to (empty = <download folder>/<name>)").pack(anchor="w")
        fr = ttk.Frame(right)
        fr.pack(anchor="w", pady=(0, 7))
        entries["folder"] = ttk.Entry(fr, textvariable=fold, width=44)
        entries["folder"].pack(side="left")
        ttk.Button(fr, text="Browse...", command=lambda: fold.set(filedialog.askdirectory(parent=win) or fold.get())).pack(side="left", padx=4)
        field("Websites (comma separated, e.g. school.example): these always go here", sites, "sites")
        ttk.Checkbutton(right, text="Automatically save downloads into their category's folder", variable=auto).pack(anchor="w", pady=(6, 0))
        ttk.Label(right, text="Override one download any time: right-click it > Move to category.", foreground="#6b7280").pack(anchor="w")

        def clean_site(x):
            x = re.sub(r"^https?://", "", x.strip().lower())
            return re.sub(r"^www\.", "", x).split("/")[0]

        def show(i):
            cur["i"] = i
            c = cats[i]
            name.set(c["name"])
            exts.set(", ".join(c["exts"]))
            fold.set(c["folder"])
            sites.set(", ".join(c["sites"]))
            general = c["name"] == "General"  # the catch-all can't be renamed or given file types
            entries["name"].config(state="disabled" if general else "normal")
            entries["exts"].config(state="disabled" if general else "normal")
            lb.selection_clear(0, "end")
            lb.selection_set(i)
            lb.see(i)

        def fill():
            lb.delete(0, "end")
            for c in cats:
                lb.insert("end", c["name"])

        def commit():
            c, n = cats[cur["i"]], name.get().strip()
            if c["name"] != "General":
                if not n or len(n) > 40 or any(ch in n for ch in '/\\:*?"<>|'):
                    return messagebox.showerror("Categories", 'Give it a short name without  / \\ : * ? " < > |', parent=win) and False
                if any(k != cur["i"] and x["name"].lower() == n.lower() for k, x in enumerate(cats)):
                    return messagebox.showerror("Categories", f"There is already a category called {n!r}.", parent=win) and False
                c["name"] = n
                c["exts"] = sorted({e.lstrip(".").lower() for e in re.split(r"[,\s]+", exts.get()) if e.lstrip(".").isalnum()})
            c["folder"] = fold.get().strip()
            c["sites"] = sorted({clean_site(x) for x in re.split(r"[,\s]+", sites.get()) if clean_site(x)})
            lb.delete(cur["i"])
            lb.insert(cur["i"], c["name"])
            lb.selection_set(cur["i"])
            return True

        def pick(_=None):
            sel = lb.curselection()
            if sel and sel[0] != cur["i"]:
                old = cur["i"]
                if commit():
                    show(sel[0])
                else:
                    lb.selection_clear(0, "end")
                    lb.selection_set(old)
        lb.bind("<<ListboxSelect>>", pick)

        def new():
            if commit():
                n, k = "New category", 1
                while any(c["name"].lower() == n.lower() for c in cats):
                    k += 1
                    n = f"New category {k}"
                cats.append({"name": n, "exts": [], "folder": "", "sites": []})
                fill()
                show(len(cats) - 1)

        def delete():
            if cats[cur["i"]]["name"] == "General":
                return messagebox.showinfo("Categories", "General is the catch-all and can't be deleted.", parent=win)
            del cats[cur["i"]]
            fill()
            show(min(cur["i"], len(cats) - 1))

        def reset():
            if messagebox.askyesno("Categories", "Replace the list with the built-in categories?", parent=win):
                cats[:] = [dict(c, _was=c["name"]) for c in copy.deepcopy(DEFAULT_CATEGORIES)]
                fill()
                show(0)

        def ok():
            if not commit():
                return
            kept = {c.get("_was") for c in cats}
            renames = {c["_was"]: c["name"] for c in cats if c.get("_was") and c["_was"] != c["name"]}
            for d in mgr.items:  # keep existing downloads pointing at real categories
                if d.category in renames:
                    d.category = renames[d.category]
                elif d.category in orig and d.category not in kept:
                    d.category, d.auto_cat = "General", True
            mgr.settings["categories"] = [{k: x for k, x in c.items() if k != "_was"} for c in cats]
            mgr.settings["auto_sort"] = auto.get()
            mgr._fix_categories()
            mgr.save_settings()
            win.destroy()
            self.after_change()
        ttk.Button(left, text="New category", command=new).pack(fill="x", pady=(6, 0))
        ttk.Button(left, text="Delete", command=delete).pack(fill="x", pady=(4, 0))
        ttk.Button(left, text="Reset to defaults", command=reset).pack(fill="x", pady=(4, 0))
        row = ttk.Frame(right)
        row.pack(anchor="e", pady=(14, 0), fill="x")
        ttk.Button(row, text="Cancel", command=win.destroy).pack(side="right")
        ttk.Button(row, text="OK", command=ok).pack(side="right", padx=6)
        fill()
        show(0)

    # ------------------------------------------------------------------ dialogs: browser pairing, help, registration
    def native(self):
        return NativeIntegration(self.mgr.settings.get("extension_ids", []))

    def register_browsers(self, silent=False):
        """Register OpenDM's native-messaging host with every installed browser (Windows: in the registry under HKCU)."""
        try:
            res = self.native().register()
        except Exception as e:  # e.g. registry locked down by policy, read-only profile folder
            self.flash(f"Browser integration failed: {e}", 20)
            if not silent:
                messagebox.showerror("Browser integration", f"Couldn't register with the browsers:\n{e}", parent=self.root)
            return []
        ok = [r["label"] for r in res if r["registered"]]
        self.flash("Browser integration ready for " + ", ".join(ok) if ok else "Browser integration: no supported browser found yet", 10)
        return res

    def pairing_dialog(self):
        """Browser integration: status per browser, register/repair/remove, and the manual token as a last resort."""
        st = self.mgr.settings
        win = tk.Toplevel(self.root)
        win.title("Browser integration")
        win.transient(self.root)
        where = "the Windows registry (HKCU, current user only)" if platform.system() == "Windows" else "each browser's NativeMessagingHosts folder"
        ttk.Label(win, wraplength=560, justify="left", text=("OpenDM registers itself with your browsers in " + where + ", so the OpenDM extension "
                  "sends downloads straight to it: no port numbers, no tokens. Only the extension IDs listed below are allowed to talk to OpenDM.")).pack(padx=14, pady=(14, 8), anchor="w")
        tv = ttk.Treeview(win, columns=("browser", "state"), show="headings", height=5)
        tv.heading("browser", text="Browser")
        tv.heading("state", text="Status")
        tv.column("browser", width=170)
        tv.column("state", width=380)
        tv.pack(padx=14, fill="x")
        names = {"registered": "Registered \u2714", "outdated": "Out of date - press Register / Repair", "not registered": "Not registered",
                 "browser not found": "Browser not found"}

        def refresh():
            tv.delete(*tv.get_children())
            for r in self.native().status():
                tv.insert("", "end", values=(r["label"], names[r["state"]]))

        def register():
            self.register_browsers()
            refresh()

        def remove():
            if messagebox.askyesno("Browser integration", "Remove OpenDM's registration from all browsers?\nThe extension will then need the manual token.", parent=win):
                self.native().unregister()
                refresh()
        row = ttk.Frame(win)
        row.pack(padx=14, pady=8, anchor="w")
        ttk.Button(row, text="Register / Repair", command=register).pack(side="left")
        ttk.Button(row, text="Remove registration", command=remove).pack(side="left", padx=6)
        ttk.Button(row, text="Refresh", command=refresh).pack(side="left")
        v_auto, v_start = tk.BooleanVar(value=st.get("native_register", True)), tk.BooleanVar(value=st.get("autostart_from_browser", True))

        def flags():
            st.update(native_register=v_auto.get(), autostart_from_browser=v_start.get())
            self.mgr.save_settings()
        ttk.Checkbutton(win, text="Register automatically every time OpenDM starts", variable=v_auto, command=flags).pack(padx=14, anchor="w")
        ttk.Checkbutton(win, text="Start OpenDM when the browser sends a download and it isn't running", variable=v_start, command=flags).pack(padx=14, anchor="w")
        ttk.Separator(win).pack(fill="x", padx=14, pady=10)
        ttk.Label(win, text="Extension ID built into this OpenDM (load the extension folder as an unpacked extension):").pack(padx=14, anchor="w")
        built = ttk.Entry(win, width=60)
        built.insert(0, DEFAULT_EXTENSION_IDS[0])
        built.state(["readonly"])
        built.pack(padx=14, anchor="w", pady=(2, 8))
        ttk.Label(win, text="Also trust these extension IDs (comma separated, e.g. a Chrome Web Store ID):").pack(padx=14, anchor="w")
        ids = tk.StringVar(value=", ".join(st.get("extension_ids", [])))
        r2 = ttk.Frame(win)
        r2.pack(padx=14, anchor="w", pady=(2, 0))
        ttk.Entry(r2, textvariable=ids, width=52).pack(side="left")

        def save_ids():
            wanted = [x.lower() for x in re.split(r"[,\s]+", ids.get()) if x]
            good = [i for i in extension_ids(wanted) if i not in DEFAULT_EXTENSION_IDS]
            bad = [x for x in wanted if x not in good and x not in DEFAULT_EXTENSION_IDS]
            if bad:
                return messagebox.showerror("Browser integration", "An extension ID is 32 letters from a to p. Not valid: " + ", ".join(bad), parent=win)
            st["extension_ids"] = good
            self.mgr.save_settings()
            register()
        ttk.Button(r2, text="Save", command=save_ids).pack(side="left", padx=6)
        ttk.Separator(win).pack(fill="x", padx=14, pady=10)
        ttk.Label(win, foreground="#6b7280", wraplength=560, justify="left", text=(
            f"Advanced - manual pairing, only if automatic registration can't be used. Server: 127.0.0.1:{self.port}"
            + ("" if self.api_srv else " (PORT BUSY: restart with  python opendm.py -p 6801)") + ". Pairing token:")).pack(padx=14, anchor="w")
        r3 = ttk.Frame(win)
        r3.pack(padx=14, anchor="w", pady=(2, 14))
        e = ttk.Entry(r3, width=52)
        e.insert(0, get_token())
        e.state(["readonly"])
        e.pack(side="left")
        ttk.Button(r3, text="Copy token", command=lambda: (self.root.clipboard_clear(), self.root.clipboard_append(get_token()))).pack(side="left", padx=6)
        refresh()

    def help_dialog(self):
        self.text_dialog("Quick help", """ADDING DOWNLOADS
  Tasks > Add new download (Ctrl+N), or copy links and use "Add batch download from clipboard".
  With the browser extension installed, downloads and videos on web pages are sent to OpenDM automatically.
  Tasks > Run site grabber scans a page for files (images, videos, documents...) and adds the ones you pick as a project.

THE LEFT PANE
  All Downloads  - every download, with the categories (Video, Documents, ...) below it.
  Unfinished / Finished - what is still running or stopped, and what is done.
  Grabber projects - downloads added from the site grabber, grouped by project.
  Queues - lists of downloads you can start and stop together. Right-click a queue to rename or delete it.

THE LIST
  Q is the position in the queue. Click a column title to sort. Double-click a finished file to open it.
  Right-click a download for Open, Resume, Stop, Delete, Move to category/queue, Redownload and Properties.

QUEUES AND THE SCHEDULER
  "Download Later" puts a download in its queue without starting it. Start queue / Stop queue act on the queue
  selected in the left pane (the main queue by default). Downloads > Scheduler restricts downloading to a time window.

SPEED
  Downloads > Speed limiter caps the total speed. View > Speed graph shows the live chart and the segment map.""")

    def shortcuts_dialog(self):
        self.text_dialog("Keyboard shortcuts", """Ctrl+N        Add new download
Ctrl+R        Resume the selected downloads
Ctrl+S        Stop the selected downloads
Delete        Delete the selected downloads
Enter         Open a finished file (or show properties)
Alt+Enter     Properties
F2            Move/Rename a finished file
F5            Refresh
Ctrl+A        Select all downloads
Ctrl+C        Copy the address of the selected downloads""", width=60, height=12)

    def about_dialog(self):
        self.info("About OpenDM", f"OpenDM {__version__}\n\nA free, open-source download manager:\nsegmented downloads, queues, categories, video (HLS),\nbrowser integration and a system tray icon.\n\nMIT License. No ads, no tracking, nothing to buy.")

    def registration_dialog(self):
        self.info("Registration", "OpenDM is free and open-source software (MIT License).\n\nThere is nothing to register or buy: no serial number, no trial period, "
                                  "no activation and no nag screens. Every feature is always available.\n\nIf you like it, tell a friend or contribute to the project.")

    def license_dialog(self):
        self.text_dialog("License", MIT_TEXT, width=100, height=20)

    # ------------------------------------------------------------------ system tray
    def show_window(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def set_tray(self, on):
        """Start or stop the tray icon. Returns an error message ('' if all is well)."""
        if on and not self.tray:
            t = Tray(base64.b64decode(ICON_B64), lambda: self.mgr.settings["limit_kb"])
            if t.available:
                t.start()
            if not t.available:
                return t.error
            self.tray = t
        elif not on and self.tray:
            self.tray.stop()
            self.tray = None
            self.show_window()
        return ""

    def handle_cmd(self, cmd):
        if cmd == "show":
            self.show_window()
        elif cmd == "pause_all":
            self.stop_all()
        elif cmd == "resume_all":
            self.resume_items(self.mgr.items)
        elif cmd.startswith("limit:"):
            self.limit_var.set(int(cmd[6:]))
        elif cmd == "folder":
            self.open_path(self.folder.get())
        elif cmd == "quit":
            self.on_close()

    def poll_tray(self):
        if self.tray:
            for c in self.tray.poll():
                self.handle_cmd(c)
        self.root.after(150, self.poll_tray)

    def notify_changes(self):
        """Balloon notification when a download finishes or fails while OpenDM isn't the window in front."""
        for d in self.mgr.items:
            prev, self.seen[id(d)] = self.seen.get(id(d)), d.status
            if prev is None or prev == d.status or not self.tray or not self.mgr.settings.get("notify", True):
                continue
            if self.root.state() in ("normal", "zoomed") and self.root.focus_displayof() is not None:
                continue
            if d.status == "Completed":
                self.tray.notify(f"Finished: {d.label}")
            elif d.status == "Error":
                self.tray.notify(f"Failed: {d.label}\n{d.error[:120]}")

    # ------------------------------------------------------------------ live refresh
    def redraw_graph(self):
        sel = self.selected()
        if len(sel) == 1:
            d = sel[0]
            what = d.label[:50]
            extra = (f" | {d.segs_done}/{d.total} parts" if isinstance(d, HlsDownload) else f" | {len(d.segs)} segments" if d.segs else "")
            samples, cells = d.hist, d.segment_map()
        else:
            what, extra, samples, cells = "All downloads", "", self.mgr.hist, []
        now, peak, avg = graph_stats(samples)
        self.gtitle.config(text=f"Speed - {what}{extra}      Now {human(now)}/s     Peak {human(peak)}/s     Avg {human(avg)}/s (last 60 s)")
        draw_graph(self.gcv, samples)
        draw_segmap(self.mapcv, cells)

    def update_toolbar(self):
        fl = self.flags()
        for icon, rule in (("resume", "resumable"), ("stop", "active"), ("stopall", "anyactive"), ("delete", "sel"), ("delc", "anydone")):
            self.tbtn[icon].state(["!disabled"] if fl[rule] else ["disabled"])

    def tick(self):
        if self.mgr.schedule() and self.after_done():
            return
        total = sum(d.speed for d in self.mgr.items)
        self.notify_changes()
        self._guard(self.drain_captured)
        self._guard(self.check_completed)
        self.draw_list()
        self.update_side()
        self.update_toolbar()
        self._guard(self.update_progress_windows)
        if self.tray:
            tip = tray_tooltip(self.mgr.items, total)
            if tip != self.last_tip:
                self.last_tip = tip
                self.tray.set_title(tip)
        st = self.mgr.settings
        api_txt = f"Browser API: listening on 127.0.0.1:{self.port}" if self.api_srv else f"Browser API: PORT {self.port} BUSY"
        sch = f" | Schedule {st['start']}-{st['stop']}: {'running' if self.mgr.in_window() else 'waiting'}" if st["sched_on"] else ""
        note = f" | {self.note[0]}" if time.time() < self.note[1] else ""
        self.status.config(text=f"{len(self.mgr.items)} downloads | {human(total)}/s | {api_txt}{sch} | Saving to: {self.folder.get()}{note}")
        if self.show_graph.get():
            self.redraw_graph()
        if int(time.time()) % 3 == 0:
            self.mgr.save()
        self.root.after(500, self.tick)

    # ------------------------------------------------------------------ closing and starting
    def on_close(self):  # really quit
        self.mgr.shutdown()
        self.root.destroy()

    def request_close(self):  # the window's X button: hide to the tray if there is one
        if self.tray and self.mgr.settings.get("close_to_tray", True):
            self.root.withdraw()
            if not self.hint_shown:
                self.hint_shown = True
                self.tray.notify("OpenDM is still running in the tray. Right-click the icon to quit.")
        else:
            self.on_close()

    def run(self):
        if self.mgr.settings.get("native_register", True):
            self.register_browsers(silent=True)  # keeps the registration pointing at this copy of OpenDM, even after it was moved
        if self.mgr.settings.get("tray", True):
            self.set_tray(True)  # if it can't start, Options explains why
        self.poll_tray()
        self.tick()
        if self.minimized or self.mgr.settings.get("start_minimized"):
            self.root.withdraw() if self.tray else self.root.iconify()
        self.root.mainloop()
        if self.tray:
            self.tray.stop()


def run_gui(port=API_PORT, minimized=False):
    App(port, minimized).run()


# ============================== CLI ==============================
def run_cli(args):
    mgr = Manager(args.max_active, persist=False)
    mgr.set_limit_kb(args.limit)
    mgr.settings["folder"], mgr.settings["auto_sort"] = os.path.expanduser(args.output), args.sort
    mgr.settings["quality"] = args.quality
    ds = [mgr.add(u, os.path.expanduser(args.output), args.connections) for u in args.urls]
    try:
        while any(d.status not in ("Completed", "Error") for d in ds):
            mgr.schedule()
            line = " | ".join(f"{(d.name or '...')[:25]} {d.percent:5.1f}% {human(d.speed)}/s" for d in ds)
            print("\r" + line[:110].ljust(110), end="", flush=True)
            time.sleep(0.5)
    except KeyboardInterrupt:
        for d in ds:
            d.pause()
        print("\nInterrupted.")
        return
    print()
    for d in ds:
        print(f"{d.status}: {d.path or d.url} {d.error}")


if __name__ == "__main__":
    if is_native_host_launch(sys.argv):  # started by a browser: speak native messaging, nothing else
        sys.exit(NativeHost().serve(sys.argv[1:]))
    p = argparse.ArgumentParser(description="OpenDM download manager")
    p.add_argument("--register-browsers", action="store_true", help="register the browser extension's native-messaging host (Windows Registry / browser folders), then exit")
    p.add_argument("--unregister-browsers", action="store_true", help="remove that registration, then exit")
    p.add_argument("--extension-id", action="append", default=[], metavar="ID", help="also trust this extension ID (e.g. from the Chrome Web Store); saved to settings")
    p.add_argument("--minimized", action="store_true", help="start minimized (to the system tray if available)")
    p.add_argument("--version", action="version", version=f"OpenDM {__version__}")
    p.add_argument("urls", nargs="*", help="URLs to download (omit to open the GUI)")
    p.add_argument("-n", "--connections", type=int, default=8)
    p.add_argument("-o", "--output", default="~/Downloads")
    p.add_argument("-m", "--max-active", type=int, default=3)
    p.add_argument("--sort", action="store_true", help="CLI: sort files into category sub-folders (Video, Documents, ...)")
    p.add_argument("-l", "--limit", type=int, default=0, help="speed limit in KB/s (0 = unlimited)")
    p.add_argument("-q", "--quality", type=int, default=0, help="max video height for HLS streams (0 = best)")
    p.add_argument("-p", "--port", type=int, default=API_PORT, help="browser-extension API port (GUI mode)")
    a = p.parse_args()
    if a.register_browsers or a.unregister_browsers or a.extension_id:
        mg = Manager(persist=True)
        st = mg.settings
        if a.extension_id:
            st["extension_ids"] = sorted(set(extension_ids(list(st.get("extension_ids", [])) + a.extension_id)) - set(DEFAULT_EXTENSION_IDS))
            mg.save_settings()
        ni = NativeIntegration(st.get("extension_ids", []))
        if a.unregister_browsers:
            ni.unregister()
            print("Removed OpenDM's browser registration.")
        else:
            for r in ni.register():
                print(f"{r['label']:16} {'registered' if r['registered'] else 'skipped'}  {r['detail']}")
        sys.exit(0)
    run_cli(a) if a.urls else run_gui(a.port, a.minimized)
