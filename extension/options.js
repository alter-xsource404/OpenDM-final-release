const api = globalThis.browser ?? globalThis.chrome;
const $ = (id) => document.getElementById(id);
api.storage.local.get({ port: 6800, token: "", intercept: true, minSizeKB: 0 }).then((c) => {
  $("token").value = c.token; $("port").value = c.port; $("min").value = c.minSizeKB; $("intercept").checked = c.intercept;
});

async function check() {
  const box = $("conn");
  box.className = ""; box.textContent = "Checking...";
  const s = (await api.runtime.sendMessage({ cmd: "status" })) || {};
  if (s.mode === "native") {
    box.className = "ok";
    box.textContent = s.running ? `Connected to OpenDM ${s.version || ""} through the browser integration \u2714`
      : "Browser integration is set up \u2714. OpenDM isn't running right now" + (s.autostart ? "; it starts automatically when you send a download." : ". Start it yourself (automatic start is off in OpenDM's Browser setup).");
  } else if (s.mode === "manual") {
    box.className = "ok";
    box.textContent = "Connected through the manual pairing token \u2714. Tip: open OpenDM once and it will register itself with this browser, so you won't need the token.";
  } else {
    box.className = "bad";
    box.textContent = "Not connected. Open OpenDM once: it registers itself with your browser automatically (or click Browser in its toolbar), then press Check again. Details: " + (s.error || "unknown");
  }
}
$("recheck").onclick = check;
check();

const saveBasic = () => api.storage.local.set({ minSizeKB: +$("min").value || 0, intercept: $("intercept").checked });
$("saveBasic").onclick = async () => { await saveBasic(); $("msg2").textContent = "Saved"; };
$("save").onclick = async () => {
  await saveBasic();
  const c = { token: $("token").value.trim(), port: +$("port").value || 6800 };
  await api.storage.local.set(c);
  try {
    const r = await fetch(`http://127.0.0.1:${c.port}/ping`, { headers: { "X-OpenDM-Token": c.token } });
    $("msg").textContent = r.ok ? "Connected to OpenDM \u2714" : r.status === 401 ? "Wrong token" : "Error " + r.status;
  } catch { $("msg").textContent = "OpenDM isn't running (or the port is wrong)"; }
  check();
};
