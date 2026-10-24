#!/usr/bin/env python3
"""Print the Chrome/Edge extension ID that extension/manifest.json's "key" produces (pure standard library).
OpenDM's native-messaging host only talks to this ID (plus any you add in Browser setup)."""
import base64, hashlib, json, pathlib

def extension_id(public_key_b64):
    der = base64.b64decode(public_key_b64)
    return "".join(chr(ord("a") + int(c, 16)) for c in hashlib.sha256(der).hexdigest()[:32])

if __name__ == "__main__":
    manifest = pathlib.Path(__file__).resolve().parent.parent / "extension" / "manifest.json"
    print(extension_id(json.loads(manifest.read_text())["key"]))
