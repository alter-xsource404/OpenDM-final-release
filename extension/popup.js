// Minimal toolbar popup: two switches + connection state (matches IDM's extension menu).
const api = globalThis.browser ?? globalThis.chrome;
const $ = (id) => document.getElementById(id);
(async () => {
  const c = await api.storage.local.get({ intercept: true, overlay: true });
  $("on").checked = c.intercept;
  $("ovr").checked = c.overlay;
  $("on").onchange = (e) => api.storage.local.set({ intercept: e.target.checked });
  $("ovr").onchange = (e) => api.storage.local.set({ overlay: e.target.checked });
  api.runtime.sendMessage({ cmd: "status" }).then((s) => {
    $("conn").textContent = s?.mode === "native" || s?.mode === "manual"
      ? "OpenDM: connected \u2714" + (s.mode === "native" && !s.running ? " (starts when needed)" : "")
      : "OpenDM: not connected. Open OpenDM once to set it up.";
  }).catch(() => {});
  $("opt").onclick = () => { api.runtime.openOptionsPage(); window.close(); };
})();
