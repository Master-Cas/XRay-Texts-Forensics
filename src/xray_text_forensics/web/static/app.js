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


function familyStateClass(state) {
  if (state === "COMPLETE") {
    return "family-state family-complete";
  }
  if (state === "NOT_TESTABLE" || state === "INSUFFICIENT_DATA") {
    return "family-state family-unavailable";
  }
  return "family-state family-error";
}

function renderFamilySummaries(rows) {
  const container = $("family-cards");
  container.replaceChildren();
  for (const item of rows) {
    const card = document.createElement("article");
    card.className = "family-card";

    const heading = document.createElement("div");
    heading.className = "family-card-heading";
    const title = document.createElement("strong");
    title.textContent = item.title;
    const state = document.createElement("span");
    state.className = familyStateClass(item.state);
    state.textContent = item.state === "COMPLETE"
      ? "Completed"
      : item.state === "NOT_TESTABLE"
        ? "Unavailable"
        : item.state === "INSUFFICIENT_DATA"
          ? "Limited sample"
          : "Error";
    heading.append(title, state);

    const summary = document.createElement("p");
    summary.textContent = item.summary;
    card.append(heading, summary);
    container.append(card);
  }
}

function renderOriginAssessment(origin) {
  const badge = $("origin-badge");
  $("origin-title").textContent = origin.headline;
  $("origin-text").textContent = origin.explanation;
  if (origin.state === "REFERENCE_COMPARISON") {
    badge.textContent = "Reference comparison available";
    badge.className = "status status-good";
  } else {
    badge.textContent = "Origin not testable yet";
    badge.className = "status status-warn";
  }
}

function renderReferenceComparison(report) {
  const section = $("reference-results");
  const container = $("reference-cards");
  container.replaceChildren();

  if (!report || !report.comparisons || report.comparisons.length === 0) {
    section.hidden = true;
    return;
  }

  const sorted = [...report.comparisons].sort(
    (a, b) => b.style_similarity - a.style_similarity,
  );
  for (const item of sorted) {
    const card = document.createElement("article");
    card.className = "reference-card";
    const title = document.createElement("strong");
    title.textContent = item.label;

    const style = document.createElement("span");
    style.textContent = "Style " + item.style_similarity.toFixed(3);
    const chars = document.createElement("span");
    chars.textContent = "Character patterns " + item.char_svd_similarity.toFixed(3);
    const content = document.createElement("span");
    content.textContent = "Content " + item.content_similarity.toFixed(3);

    card.append(title, style, chars, content);
    container.append(card);
  }
  section.hidden = false;
}

const evidenceLanguage = {
  ZERO_WIDTH_CHARACTER: {
    title: "Hidden zero-width characters",
    detected: "Invisible zero-width characters are present. They can be legitimate, but because they are normally unseen they deserve review.",
    clear: "No hidden zero-width characters were found.",
  },
  BIDI_CONTROL: {
    title: "Text-direction controls",
    detected: "Characters that can change the visual reading order of text were found. Review where they appear, because what is displayed can differ from the stored order.",
    clear: "No text-direction control characters were found.",
  },
  UNICODE_TAG_CHARACTER: {
    title: "Invisible Unicode tag characters",
    detected: "Invisible Unicode tag characters are present. They are uncommon in ordinary prose and should be reviewed in context.",
    clear: "No invisible Unicode tag characters were found.",
  },
  VARIATION_SELECTOR: {
    title: "Glyph variation selectors",
    detected: "Characters that request a different visual form for a symbol were found. They are often legitimate, especially around symbols or emoji.",
    clear: "No glyph variation selectors were found.",
  },
  SPACE_VARIANT: {
    title: "Non-standard spaces",
    detected: "The text contains spaces other than the ordinary keyboard space. This may come from typography, copy/paste or document formatting and is not suspicious by itself.",
    clear: "No non-standard spacing characters were found.",
  },
  CONTROL_CHARACTER: {
    title: "Non-standard control characters",
    detected: "Control characters outside normal tabs and line breaks were found. They may affect software processing even when they are hard to see.",
    clear: "No non-standard control characters were found.",
  },
  FORMAT_CONTROL_OTHER: {
    title: "Other invisible formatting controls",
    detected: "Other Unicode formatting-control characters were found. Their meaning depends on where they occur, so the locations should be reviewed.",
    clear: "No other invisible formatting controls were found.",
  },
  SUSPICIOUS_COMBINING_SEQUENCE: {
    title: "Unusual combining marks",
    detected: "An unusual sequence of combining marks was found. These marks can alter how nearby characters are displayed and should be checked in context.",
    clear: "No unusual combining-mark sequences were found.",
  },
  NORMALIZATION_DIFFERENCE: {
    title: "Unicode representation changes after normalization",
    detected: "Some characters change to an equivalent Unicode representation when normalized. This can happen in ordinary text and is not evidence of manipulation by itself.",
    clear: "The text keeps the same representation across the Unicode normalization checks.",
  },
  MIXED_SCRIPT_TOKEN: {
    title: "Words mixing look-alike alphabets",
    detected: "At least one word mixes Latin, Cyrillic or Greek characters. This can be legitimate, but it can also be used to substitute look-alike letters.",
    clear: "No words mixing Latin, Cyrillic and Greek characters were found.",
  },
};

const descriptiveFindings = new Set([
  "NORMALIZATION_DIFFERENCE",
  "SPACE_VARIANT",
  "VARIATION_SELECTOR",
]);

function evidenceLabel(finding) {
  const copy = evidenceLanguage[finding];
  return copy ? copy.title : String(finding || "Unknown finding").replaceAll("_", " ");
}

function statusCell(status) {
  const span = document.createElement("span");
  if (status === "DETECTED") {
    span.textContent = "Found";
    span.className = "evidence-detected";
  } else if (status === "NOT_TESTABLE") {
    span.textContent = "Not testable";
    span.className = "evidence-untested";
  } else {
    span.textContent = "Not found";
    span.className = "evidence-clear";
  }
  span.title = status;
  return span;
}

function renderPlainLanguageEvidence(rows) {
  const badge = $("plain-summary-badge");
  const summary = $("plain-summary-text");
  const list = $("plain-findings");
  list.replaceChildren();

  const detected = rows.filter((item) => item.status === "DETECTED");
  const notTestable = rows.filter((item) => item.status === "NOT_TESTABLE");
  const review = detected.filter((item) => !descriptiveFindings.has(item.finding));

  if (notTestable.length > 0) {
    badge.textContent = "Some checks unavailable";
    badge.className = "status status-warn";
    summary.textContent = "The scan completed, but some Unicode checks could not be evaluated. Review the technical details before drawing conclusions.";
  } else if (detected.length === 0) {
    badge.textContent = "No unusual Unicode patterns found";
    badge.className = "status status-good";
    summary.textContent = "None of the Unicode patterns covered by this scan were detected in the document.";
  } else if (review.length === 0) {
    badge.textContent = "Technical difference found";
    badge.className = "status status-warn";
    summary.textContent = "The scan found a Unicode difference worth explaining, but it did not find the stronger invisible-control or mixed-alphabet patterns covered by these checks.";
  } else {
    badge.textContent = "Review recommended";
    badge.className = "status status-warn";
    summary.textContent = "The scan found Unicode patterns that deserve contextual review. They are evidence about how the text is encoded, not proof of authorship, intent or manipulation.";
  }

  for (const item of detected) {
    const copy = evidenceLanguage[item.finding];
    const entry = document.createElement("li");
    const title = document.createElement("strong");
    const explanation = document.createElement("span");
    title.textContent = copy ? copy.title : evidenceLabel(item.finding);
    explanation.textContent = copy
      ? copy.detected
      : (item.parameters && item.parameters.interpretation) || item.reason || "A technical Unicode finding was detected.";
    entry.append(title, explanation);
    list.append(entry);
  }

  if (detected.length === 0) {
    const entry = document.createElement("li");
    const title = document.createElement("strong");
    const explanation = document.createElement("span");
    title.textContent = "Checks completed";
    explanation.textContent = String(rows.length) + " Unicode checks returned no detected finding.";
    entry.append(title, explanation);
    list.append(entry);
  } else {
    const clearCount = rows.filter((item) => item.status === "NOT_DETECTED").length;
    if (clearCount > 0) {
      const entry = document.createElement("li");
      const title = document.createElement("strong");
      const explanation = document.createElement("span");
      title.textContent = "Other checks";
      explanation.textContent = String(clearCount) + " additional Unicode checks did not find the patterns they look for.";
      entry.append(title, explanation);
      list.append(entry);
    }
  }
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
    finding.textContent = evidenceLabel(item.finding);
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
  $("scan-progress").textContent = "Preserving bytes and running the full forensic scan…";

  try {
    const result = await jsonRequest(api + "/analyze/full", {
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
    renderOriginAssessment(result.origin_assessment);
    renderFamilySummaries(result.family_summaries || []);
    renderReferenceComparison(result.reference_comparison);
    renderPlainLanguageEvidence(result.unicode_evidence || []);
    renderEvidence(
      result.unicode_evidence || [],
      $("evidence-body"),
      $("evidence-count"),
    );
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
