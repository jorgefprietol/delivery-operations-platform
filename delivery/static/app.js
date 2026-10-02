"use strict";
let token = "";
const $ = (id) => document.getElementById(id);
const seconds = (value) =>
  value == null
    ? "—"
    : value < 60
      ? `${value.toFixed(1)} s`
      : value < 3600
        ? `${(value / 60).toFixed(1)} min`
        : `${(value / 3600).toFixed(1)} h`;
function element(tag, text, className) {
  const node = document.createElement(tag);
  node.textContent = text;
  if (className) node.className = className;
  return node;
}
async function read(path) {
  const result = await fetch(path, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });
  if (!result.ok)
    throw new Error(
      result.status === 401
        ? "Token inválido. Revisa la credencial e intenta de nuevo."
        : `Consulta rechazada: HTTP ${result.status}`,
    );
  return result.json();
}
async function refresh() {
  $("refresh").disabled = true;
  $("notice").className = "";
  $("notice").textContent = "Consultando registros…";
  try {
    const [summary, releases, health] = await Promise.all([
      read("/api/v1/summary"),
      read("/api/v1/releases"),
      read("/health/ready"),
    ]);
    $("evidence-mode").textContent =
      { demo: "DEMO · SINTÉTICO", verified: "MODO VERIFICADO" }[
        health.evidence_mode
      ] ?? "SIN CONSULTAR";
    $("deployments").textContent = summary.production_deployments;
    $("failure").textContent =
      summary.change_failure_rate == null
        ? "—"
        : `${(summary.change_failure_rate * 100).toFixed(1)}%`;
    $("lead").textContent = seconds(summary.mean_lead_time_seconds);
    $("recovery").textContent = seconds(summary.mean_recovery_time_seconds);
    $("environments").className = "";
    $("environments").replaceChildren();
    for (const item of summary.active) {
      const row = element("div", "", "environment");
      const description = element("div", "");
      description.append(
        element("strong", item.environment),
        element(
          "small",
          `Commit ${item.commit_sha.slice(0, 8)} · versión ${item.version}`,
        ),
      );
      row.append(
        description,
        element("span", item.status, `badge ${item.status}`),
      );
      $("environments").append(row);
    }
    if (!summary.active.length)
      $("environments").append(
        element("div", "Aún no hay entregas registradas.", "empty"),
      );
    $("rows").replaceChildren();
    for (const item of releases) {
      const row = element("tr", "");
      const commit = element("td", item.id.slice(0, 8));
      commit.append(element("small", item.commit_sha.slice(0, 12)));
      const state = element("td", "");
      state.append(element("span", item.status, `badge ${item.status}`));
      const digest = element("td", "");
      digest.append(element("code", `${item.image_digest.slice(0, 22)}…`));
      row.append(
        commit,
        element("td", item.environment),
        state,
        digest,
        element("td", new Date(item.created_at).toLocaleString("es-EC")),
      );
      $("rows").append(row);
    }
    if (!releases.length) {
      const row = element("tr", "");
      const cell = element("td", "Sin releases registrados.", "empty");
      cell.colSpan = 5;
      row.append(cell);
      $("rows").append(row);
    }
    $("notice").textContent =
      `Actualizado ${new Date().toLocaleTimeString("es-EC")} · ${summary.open_incidents} incidentes abiertos · ${summary.recovered_incidents} recuperados · métricas de registros, sin clasificación de madurez automática.`;
  } catch (error) {
    $("notice").className = "error";
    $("notice").textContent = error.message;
    // Clear stale data so an expired session never presents old values as live.
    $("evidence-mode").textContent = "SIN CONSULTAR";
    for (const id of ["deployments", "failure", "lead", "recovery"])
      $(id).textContent = "—";
    $("environments").replaceChildren(
      element("div", "Sesión sin datos disponibles.", "empty"),
    );
    $("rows").replaceChildren();
  } finally {
    $("refresh").disabled = !token;
  }
}
$("session").addEventListener("submit", (event) => {
  event.preventDefault();
  token = $("token").value;
  $("token").value = "";
  refresh();
});
$("refresh").addEventListener("click", refresh);
