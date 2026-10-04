"use strict";

const launchUrl = new URL(window.location.href);
if (launchUrl.searchParams.has("desktop_token")) {
  window.history.replaceState({}, document.title, launchUrl.pathname);
}

const api = "/api/v1";
let activeCaseId = null;
let toastTimer = null;

const $ = (id) => document.getElementById(id);

function setHealth(ok) {
  const badge = $("health-badge");
  badge.textContent = ok ? "Engine online" : "Engine unavailable";
  badge.className = ok ? "status status-good" : "status status-bad";
}

function setSessionState(principal) {
  const badge = $("session-badge");
  const signIn = $("signin-link");
  const signOut = $("logout-link");

  if (!principal) {
    badge.hidden = true;
    signIn.hidden = false;
    signOut.hidden = true;
    return;
  }

  badge.textContent = principal.subject_id + " · " + principal.tenant_id;
  badge.className = "status status-good";
  badge.hidden = false;
  signIn.hidden = true;
  signOut.hidden = principal.auth_method !== "oidc";
}

async function loadSession() {
  const response = await fetch(api + "/session");
  if (response.status === 401) {
    setSessionState(null);
    return;
  }
  if (!response.ok) {
    setSessionState(null);
    return;
  }
  setSessionState(await response.json());
}

function toast(message) {
  const element = $("toast");
  element.textContent = message;
  element.hidden = false;
  if (toastTimer !== null) {
    window.clearTimeout(toastTimer);
  }
  toastTimer = window.setTimeout(() => {
    element.hidden = true;
  }, 4200);
}

async function jsonRequest(url, options = {}) {
  const response = await fetch(url, options);
  let payload = null;
  const type = response.headers.get("content-type") || "";
  if (type.includes("application/json")) {
    payload = await response.json();
  }
  if (!response.ok) {
    const message = payload && payload.detail
      ? payload.detail
      : "Request failed (" + String(response.status) + ")";
    throw new Error(message);
  }
  return payload;
}

function metric(label, value, codeValue = false) {
  const box = document.createElement("div");
  box.className = "metric";
  const name = document.createElement("span");
  name.textContent = label;
  const result = document.createElement(codeValue ? "code" : "strong");
  result.textContent = String(value);
  box.append(name, result);
  return box;
}

function fillMetrics(container, metrics) {
  container.replaceChildren();
  for (const item of metrics) {
    container.append(metric(item.label, item.value, item.code || false));
  }
}

function statusCell(status) {
  const span = document.createElement("span");
  span.textContent = status;
  span.className = status === "DETECTED" ? "evidence-detected" : "evidence-clear";
  return span;
}

function evidenceDetail(item) {
  const params = item.parameters || {};
  if (typeof params.total_count === "number") {
    return String(params.total_count);
  }
  if (typeof params.total_sequences === "number") {
    return String(params.total_sequences);
  }
  if (item.locations && item.locations.length) {
    return String(item.locations.length) + " location(s)";
  }
  return item.reason || "—";
}

function renderEvidence(rows, body, countTarget, includeId = false) {
  body.replaceChildren();
  countTarget.textContent = String(rows.length) + " record" + (rows.length === 1 ? "" : "s");
  for (const item of rows) {
    const row = document.createElement("tr");

    if (includeId) {
      const idCell = document.createElement("td");
      const code = document.createElement("code");
      code.textContent = item.evidence_id;
      idCell.append(code);
      row.append(idCell);
    }

    const finding = document.createElement("td");
    finding.textContent = item.finding || "—";
    row.append(finding);

    if (includeId) {
      const family = document.createElement("td");
      family.textContent = item.family;
      row.append(family);

      const status = document.createElement("td");
      status.append(statusCell(item.status));
      row.append(status);
      body.append(row);
      continue;
    }

    const status = document.createElement("td");
    status.append(statusCell(item.status));
    row.append(status);

    const detail = document.createElement("td");
    detail.textContent = evidenceDetail(item);
    row.append(detail);

    const detector = document.createElement("td");
    detector.textContent = item.detector_id + "@" + item.detector_version;
    row.append(detector);
    body.append(row);
  }
}

async function scanFile(file) {
  const data = new FormData();
  data.append("file", file);
  $("scan-progress").hidden = false;
  $("scan-progress").textContent = "Preserving bytes and running Unicode forensics…";

  try {
    const result = await jsonRequest(api + "/analyze/unicode", {
      method: "POST",
      body: data,
    });
    fillMetrics($("artifact-cards"), [
      { label: "Filename", value: result.artifact.original_filename || "unnamed" },
      { label: "SHA-256", value: result.artifact.sha256, code: true },
      { label: "Bytes", value: result.artifact.byte_length },
      { label: "Media type", value: result.artifact.media_type },
      { label: "Encoding", value: result.artifact.detected_encoding || "n/a" },
      { label: "Views", value: result.views.length },
    ]);
    renderEvidence(result.evidence, $("evidence-body"), $("evidence-count"));
    $("scan-summary").hidden = false;
  } finally {
    $("scan-progress").hidden = true;
  }
}

function reportUrl(format) {
  return api + "/cases/" + encodeURIComponent(activeCaseId) + "/report?format=" + format;
}

function renderCase(bundle) {
  activeCaseId = bundle.case.case_id;
  $("case-workspace").hidden = false;
  $("case-name").textContent = bundle.case.title;
  $("active-case-id").textContent = activeCaseId;
  $("case-id-input").value = activeCaseId;

  const audit = $("audit-badge");
  audit.textContent = bundle.audit_verified ? "Audit chain verified" : "Audit chain invalid";
  audit.className = bundle.audit_verified ? "status status-good" : "status status-bad";

  fillMetrics($("case-stats"), [
    { label: "Artifacts", value: bundle.artifacts.length },
    { label: "Detector runs", value: bundle.runs.length },
    { label: "Evidence", value: bundle.evidence.length },
    { label: "Audit events", value: bundle.audit_event_count },
  ]);
  renderEvidence(
    bundle.evidence,
    $("case-evidence-body"),
    $("case-evidence-count"),
    true,
  );

  $("report-html").href = reportUrl("html");
  $("report-pdf").href = reportUrl("pdf");
  $("report-json").href = reportUrl("json");
}

document.querySelectorAll(".nav-item").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".nav-item").forEach((item) => {
      item.classList.remove("active");
    });
    document.querySelectorAll(".panel").forEach((panel) => {
      panel.classList.remove("active");
    });
    button.classList.add("active");
    $(button.dataset.panel).classList.add("active");
  });
});

$("scan-file").addEventListener("change", (event) => {
  const file = event.target.files[0];
  const label = document.querySelector(".file-drop strong");
  if (file) {
    label.textContent = file.name;
  }
});

$("scan-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const file = $("scan-file").files[0];
  if (!file) {
    return;
  }
  try {
    await scanFile(file);
  } catch (error) {
    toast(error.message);
  }
});

$("case-create-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const created = await jsonRequest(api + "/cases", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: $("case-title").value }),
    });
    const bundle = await jsonRequest(
      api + "/cases/" + encodeURIComponent(created.case_id),
    );
    renderCase(bundle);
    toast("Case created.");
  } catch (error) {
    toast(error.message);
  }
});

$("case-open-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const caseId = $("case-id-input").value.trim();
    const bundle = await jsonRequest(api + "/cases/" + encodeURIComponent(caseId));
    renderCase(bundle);
  } catch (error) {
    toast(error.message);
  }
});

$("case-analyze-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!activeCaseId) {
    return;
  }
  const file = $("case-file").files[0];
  if (!file) {
    return;
  }
  const data = new FormData();
  data.append("file", file);
  try {
    const url = api + "/cases/" + encodeURIComponent(activeCaseId) + "/analyze/unicode";
    const bundle = await jsonRequest(url, { method: "POST", body: data });
    renderCase(bundle);
    toast("Artifact added and analyzed.");
  } catch (error) {
    toast(error.message);
  }
});

$("compare-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const original = $("original-file").files[0];
  const transformed = $("transformed-file").files[0];
  if (!original || !transformed) {
    return;
  }

  const data = new FormData();
  data.append("original", original);
  data.append("transformed", transformed);

  try {
    const result = await jsonRequest(api + "/compare-transform", {
      method: "POST",
      body: data,
    });
    fillMetrics($("compare-metrics"), [
      { label: "Token Jaccard", value: result.token_jaccard.toFixed(4) },
      { label: "Sequence ratio", value: result.token_sequence_ratio.toFixed(4) },
      { label: "5-gram survival", value: result.fivegram_survival.toFixed(4) },
      { label: "Lexical TF-IDF", value: result.lexical_tfidf_cosine.toFixed(4) },
      { label: "Length ratio", value: result.char_length_ratio.toFixed(4) },
      {
        label: "Tokens",
        value: String(result.original_token_count) + " → " + String(result.transformed_token_count),
      },
    ]);
    $("compare-results").hidden = false;
  } catch (error) {
    toast(error.message);
  }
});

jsonRequest(api + "/health")
  .then(() => setHealth(true))
  .catch(() => setHealth(false));

loadSession().catch(() => setSessionState(null));
