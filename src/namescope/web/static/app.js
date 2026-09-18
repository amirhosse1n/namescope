const platformNames = {
  github: "GitHub",
  instagram: "Instagram",
  telegram: "Telegram",
};

const jobs = new Map();
const candidateNames = new Map();
let rules = {};

function statusLabel(status, platform = null) {
  if (status === "possibly_available") {
    if (platform === "github") return "Likely available";
    if (platform === "telegram") return "Likely unclaimed";
    return "Possibly available";
  }
  return {
    available: "Available",
    taken: "Taken",
    unavailable: "Unavailable",
    invalid: "Invalid",
    purchase_available: "Fragment purchase",
    unknown: "Unknown",
    rate_limited: "Rate limited",
    config_required: "Setup required",
    error: "Error",
  }[status] || status;
}

function platformUrl(platform, username) {
  const value = encodeURIComponent(username);
  if (platform === "github") return `https://github.com/${value}`;
  if (platform === "instagram") return `https://www.instagram.com/${value}/`;
  return `https://t.me/${value}`;
}

function element(tag, options = {}, children = []) {
  const node = document.createElement(tag);
  Object.entries(options).forEach(([key, value]) => {
    if (key === "className") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key.startsWith("data-")) node.setAttribute(key, value);
    else if (key in node) node[key] = value;
    else node.setAttribute(key, value);
  });
  for (const child of children) node.append(child);
  return node;
}

function statusBadge(result, platform = result.platform) {
  return element("span", {
    className: `status ${result.status}`,
    text: statusLabel(result.status, platform),
  });
}

async function api(url, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (options.body && !headers["Content-Type"]) headers["Content-Type"] = "application/json";
  const response = await fetch(url, { ...options, headers });
  if (!response.ok) {
    let payload = null;
    try {
      payload = await response.json();
    } catch (_) {
      payload = null;
    }
    const detail = Array.isArray(payload?.detail)
      ? payload.detail.join(" ")
      : (payload?.detail || `HTTP ${response.status}`);
    throw new Error(detail);
  }
  return response.json();
}

function switchView(view) {
  document.querySelectorAll(".view").forEach((node) => {
    node.classList.toggle("active", node.id === view);
  });
  document.querySelectorAll(".nav-link").forEach((node) => {
    node.classList.toggle("active", node.dataset.view === view);
  });
  window.history.replaceState(null, "", `#${view}`);
}

function renderQuickResults(results) {
  const target = document.getElementById("quick-results");
  target.replaceChildren();
  for (const result of results) {
    const card = element("article", { className: "result-card" });
    card.append(
      element("h3", { text: platformNames[result.platform] }),
      statusBadge(result),
      element("p", { className: "detail", text: result.detail }),
      element("div", {
        className: "meta",
        text: `${result.cached ? "Cached · " : ""}${result.latency_ms != null ? `${result.latency_ms} ms` : ""}`,
      }),
    );
    target.append(card);
  }
}

function platformNote(platform) {
  if (platform === "github") {
    return "NameScope checks the GitHub REST API first. When no public user resolves, it also tries GitHub's signup availability check. Only a positive signup response is labeled Available.";
  }
  if (platform === "instagram") {
    return "Instagram does not expose a public username-registration API. NameScope combines public web-profile signals and labels missing profiles as Possibly available, not guaranteed available.";
  }
  return "Public t.me checks work without logging in. For a definitive Available result, configure a Telegram user session so NameScope can call account.checkUsername.";
}

function platformTemplate(platform, rule) {
  const groups = [
    ["letters", "Letters", true],
    ["digits", "Digits", false],
    ["underscore", "Underscore", false],
    ["hyphen", "Hyphen", false],
    ["period", "Period", false],
  ];

  const section = document.getElementById(platform);
  section.replaceChildren();

  const header = element("div", { className: "platform-head" });
  const copy = element("div", { className: "copy" });
  copy.append(
    element("p", { className: "eyebrow", text: `${platformNames[platform].toUpperCase()} SCANNER` }),
    element("h1", { text: "Generate, validate, then check." }),
    element("p", {
      className: "lede",
      text: "Build a bounded search space from the characters you choose. Platform rules are applied before any network request.",
    }),
  );
  header.append(copy, element("span", { className: "rule-chip", text: rule.summary }));

  const layout = element("div", { className: "layout" });
  const form = element("form", { className: "panel scan-form" });
  form.dataset.platform = platform;
  form.append(
    element("h2", { text: "Search space" }),
    element("p", {
      className: "panel-sub",
      text: "By default, previously checked usernames are skipped using the local history database.",
    }),
  );

  const lengths = element("div", { className: "field-row" });
  const defaultLength = Math.max(rule.min_length, platform === "telegram" ? 5 : 3);
  lengths.append(
    numberField("Minimum length", "min_length", rule.min_length, rule.max_length, defaultLength),
    numberField("Maximum length", "max_length", rule.min_length, rule.max_length, defaultLength),
  );
  form.append(lengths);
  form.append(numberField("Usernames to generate and check", "count", 1, 10000, 100));

  const characterField = element("div", { className: "field" });
  characterField.append(element("label", { text: "Character groups" }));
  const checks = element("div", { className: "checks" });
  for (const [key, label, checked] of groups) {
    const allowed = rule.allowed_groups.includes(key);
    const input = element("input", { type: "checkbox", name: key, checked: checked && allowed, disabled: !allowed });
    const pill = element("label", { className: `check-pill ${allowed ? "" : "disabled"}` }, [input, document.createTextNode(` ${label}`)]);
    checks.append(pill);
  }
  characterField.append(checks);
  form.append(characterField);

  form.append(textField("Custom characters (optional)", "custom", "e.g. abcxyz017"));

  const strategyField = element("div", { className: "field" });
  strategyField.append(element("label", { text: "Generation strategy" }));
  const strategy = element("select", { name: "strategy" });
  strategy.append(
    element("option", { value: "random", text: "Random spread" }),
    element("option", { value: "lexicographic", text: "Lexicographic" }),
  );
  strategyField.append(strategy);
  form.append(strategyField);

  const historyBox = element("div", { className: "history-box" });
  const historyCopy = element("div");
  const historyMeta = element("div", { className: "meta" });
  const historyCount = element("span", { text: "0" });
  historyCount.dataset.historyCount = "";
  historyMeta.append(historyCount, document.createTextNode(` usernames saved for ${platformNames[platform]}`));
  historyCopy.append(element("strong", { text: "Persistent history" }), historyMeta);
  historyBox.append(historyCopy, element("button", { type: "button", className: "text-button clear-history", text: "Clear history" }));
  form.append(historyBox);

  form.append(
    checkboxRow("recheck_previous", "Recheck usernames already saved in history"),
    element("p", {
      className: "microcopy",
      text: "Leave this off to spend requests only on new candidates. Turning it on also forces a fresh network check for repeated names.",
    }),
    checkboxRow("force_refresh", "Ignore reusable cache for this scan"),
  );

  const actions = element("div", { className: "actions" });
  actions.append(
    element("button", { type: "submit", className: "primary", text: "Start scan" }),
    element("button", { type: "button", className: "secondary cancel", text: "Cancel", disabled: true }),
  );
  form.append(actions, element("div", { className: "note", text: platformNote(platform) }));

  const scanMain = buildScanMain(platform);
  layout.append(form, scanMain);
  section.append(header, layout);
}

function numberField(label, name, min, max, value) {
  const wrapper = element("div", { className: "field" });
  wrapper.append(
    element("label", { text: label }),
    element("input", { type: "number", name, min, max, value, required: true }),
  );
  return wrapper;
}

function textField(label, name, placeholder) {
  const wrapper = element("div", { className: "field" });
  wrapper.append(
    element("label", { text: label }),
    element("input", { type: "text", name, placeholder, autocomplete: "off", spellcheck: false }),
  );
  return wrapper;
}

function checkboxRow(name, label) {
  const input = element("input", { type: "checkbox", name });
  return element("label", { className: "option-row" }, [input, document.createTextNode(` ${label}`)]);
}

function buildScanMain(platform) {
  const main = element("div", { className: "scan-main" });
  const summary = element("div", { className: "scan-summary" });
  for (const [key, label] of [
    ["checked", "Checked"],
    ["available", "Candidates"],
    ["taken", "Taken / unavailable"],
    ["uncertain", "Uncertain"],
  ]) {
    const value = element("strong", { text: "0" });
    value.dataset.stat = key;
    summary.append(element("div", { className: "stat" }, [element("span", { text: label }), value]));
  }

  const progress = element("progress", { className: "progress-native", max: 100, value: 0 });

  const tableWrap = element("div", { className: "result-table-wrap" });
  const tableHead = element("div", { className: "table-head" });
  const jobState = element("span", { className: "meta job-state", text: "Not started" });
  tableHead.append(element("h3", { text: "Live results" }), jobState);

  const tableScroll = element("div", { className: "table-scroll" });
  const table = element("table");
  const thead = element("thead");
  const headRow = element("tr");
  for (const label of ["Username", "Status", "Detail", "Latency"]) headRow.append(element("th", { text: label }));
  thead.append(headRow);
  const tbody = element("tbody");
  tbody.append(emptyRow("Start a scan to see results here."));
  table.append(thead, tbody);
  tableScroll.append(table);
  tableWrap.append(tableHead, tableScroll);

  const candidatePanel = element("div", { className: "candidate-panel" });
  const candidateHead = element("div", { className: "candidate-head" });
  const candidateCopy = element("div");
  candidateCopy.append(
    element("p", { className: "eyebrow", text: "SHORTLIST" }),
    element("h3", { text: "Available candidates" }),
    element("p", {
      className: "candidate-sub",
      text: "Names that look available or unclaimed based on the strongest check NameScope could perform.",
    }),
  );
  const copyButton = element("button", { type: "button", className: "secondary copy-candidates", text: "Copy all", disabled: true });
  candidateHead.append(candidateCopy, copyButton);
  const candidateList = element("div", { className: "candidate-list" });
  candidateList.append(element("div", { className: "empty compact", text: "No candidates yet." }));
  candidatePanel.append(candidateHead, candidateList);

  main.append(summary, progress, tableWrap, candidatePanel);
  main.dataset.platform = platform;
  return main;
}

function emptyRow(message) {
  const cell = element("td", { className: "empty", colSpan: 4, text: message });
  return element("tr", {}, [cell]);
}

function scanPayload(form, platform) {
  const data = new FormData(form);
  return {
    platform,
    min_length: Number(data.get("min_length")),
    max_length: Number(data.get("max_length")),
    count: Number(data.get("count")),
    include_letters: data.get("letters") === "on",
    include_digits: data.get("digits") === "on",
    include_underscore: data.get("underscore") === "on",
    include_hyphen: data.get("hyphen") === "on",
    include_period: data.get("period") === "on",
    custom_characters: data.get("custom") || "",
    strategy: data.get("strategy"),
    force_refresh: data.get("force_refresh") === "on",
    recheck_previous: data.get("recheck_previous") === "on",
  };
}

function updateCandidateUI(section, snapshot) {
  const candidates = snapshot.candidates || [];
  candidateNames.set(snapshot.platform, candidates.map((item) => item.username));

  const button = section.querySelector(".copy-candidates");
  button.disabled = candidates.length === 0;
  button.textContent = candidates.length ? `Copy all (${candidates.length})` : "Copy all";

  const list = section.querySelector(".candidate-list");
  list.replaceChildren();
  if (!candidates.length) {
    list.append(element("div", { className: "empty compact", text: "No candidates yet." }));
    return;
  }

  for (const item of [...candidates].reverse()) {
    const copy = element("button", { type: "button", className: "candidate-copy", text: item.username, title: "Copy username" });
    copy.dataset.copyUsername = item.username;
    const open = element("a", {
      className: "candidate-open",
      text: "Open ↗",
      href: platformUrl(snapshot.platform, item.username),
      target: "_blank",
      rel: "noopener noreferrer",
    });
    list.append(element("div", { className: "candidate-item" }, [copy, statusBadge(item, snapshot.platform), open]));
  }
}

function updateScanUI(section, snapshot) {
  const counts = snapshot.counts || {};
  section.querySelector('[data-stat="checked"]').textContent = snapshot.checked;
  section.querySelector('[data-stat="available"]').textContent =
    (counts.available || 0) + (counts.possibly_available || 0) + (counts.purchase_available || 0);
  section.querySelector('[data-stat="taken"]').textContent = (counts.taken || 0) + (counts.unavailable || 0);
  section.querySelector('[data-stat="uncertain"]').textContent =
    (counts.unknown || 0) + (counts.error || 0) + (counts.rate_limited || 0) +
    (counts.config_required || 0) + (counts.invalid || 0);

  const progress = snapshot.requested ? Math.min(100, (snapshot.checked / snapshot.requested) * 100) : 0;
  section.querySelector(".progress-native").value = progress;

  const stateParts = [snapshot.state];
  if (snapshot.message) stateParts.push(snapshot.message);
  if (snapshot.error) stateParts.push(snapshot.error);
  section.querySelector(".job-state").textContent = stateParts.join(" · ");

  const body = section.querySelector("tbody");
  body.replaceChildren();
  if (!snapshot.results.length) {
    body.append(emptyRow("No checked results yet."));
  } else {
    for (const result of [...snapshot.results].reverse()) {
      const row = element("tr");
      row.append(
        element("td", { className: "username", text: result.username }),
        element("td", {}, [statusBadge(result, snapshot.platform)]),
        element("td", { text: result.detail }),
        element("td", {
          text: `${result.latency_ms != null ? `${result.latency_ms} ms` : "—"}${result.cached ? " · cached" : ""}`,
        }),
      );
      body.append(row);
    }
  }

  updateCandidateUI(section, snapshot);
}

async function refreshHistory(platform) {
  const section = document.getElementById(platform);
  const target = section?.querySelector("[data-history-count]");
  if (!target) return;
  try {
    const payload = await api(`/api/history/${platform}?limit=1`);
    target.textContent = payload.count;
  } catch (_) {
    target.textContent = "?";
  }
}

async function pollJob(platform, section, jobId) {
  while (true) {
    const snapshot = await api(`/api/scans/${jobId}`);
    updateScanUI(section, snapshot);
    if (!["queued", "running"].includes(snapshot.state)) {
      section.querySelector('.scan-form button[type="submit"]').disabled = false;
      section.querySelector(".cancel").disabled = true;
      jobs.delete(platform);
      await refreshHistory(platform);
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, 800));
  }
}

async function startScan(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const platform = form.dataset.platform;
  const section = document.getElementById(platform);
  candidateNames.set(platform, []);
  updateCandidateUI(section, { platform, candidates: [] });

  try {
    const started = await api("/api/scans", {
      method: "POST",
      body: JSON.stringify(scanPayload(form, platform)),
    });
    jobs.set(platform, started.job_id);
    form.querySelector('button[type="submit"]').disabled = true;
    form.querySelector(".cancel").disabled = false;
    section.querySelector(".job-state").textContent = "queued";
    await pollJob(platform, section, started.job_id);
  } catch (error) {
    section.querySelector(".job-state").textContent = `Error · ${error.message}`;
    form.querySelector('button[type="submit"]').disabled = false;
    form.querySelector(".cancel").disabled = true;
  }
}

async function copyText(text, button = null) {
  if (!text) return;
  try {
    await navigator.clipboard.writeText(text);
    if (button) {
      const previous = button.textContent;
      button.textContent = "Copied";
      setTimeout(() => { button.textContent = previous; }, 900);
    }
  } catch (_) {
    window.prompt("Copy usernames:", text);
  }
}

function bindPlatform(platform) {
  const section = document.getElementById(platform);
  const form = section.querySelector(".scan-form");
  form.addEventListener("submit", startScan);

  section.querySelector(".cancel").addEventListener("click", async () => {
    const id = jobs.get(platform);
    if (!id) return;
    try {
      await api(`/api/scans/${id}/cancel`, { method: "POST" });
    } catch (_) {
      // The polling loop will surface the current job state.
    }
  });

  section.querySelector(".clear-history").addEventListener("click", async () => {
    if (jobs.has(platform)) return;
    if (!window.confirm(`Clear all saved ${platformNames[platform]} history and cached results?`)) return;
    try {
      await api(`/api/history/${platform}`, { method: "DELETE" });
      await refreshHistory(platform);
      section.querySelector(".job-state").textContent = "History cleared";
    } catch (error) {
      section.querySelector(".job-state").textContent = `Error · ${error.message}`;
    }
  });

  section.querySelector(".copy-candidates").addEventListener("click", async (event) => {
    await copyText((candidateNames.get(platform) || []).join("\n"), event.currentTarget);
  });

  section.querySelector(".candidate-list").addEventListener("click", async (event) => {
    const button = event.target.closest("[data-copy-username]");
    if (!button) return;
    await copyText(button.dataset.copyUsername, button);
  });
}

async function initialize() {
  rules = await api("/api/rules");
  for (const platform of ["github", "instagram", "telegram"]) {
    platformTemplate(platform, rules[platform]);
    bindPlatform(platform);
    await refreshHistory(platform);
  }

  document.querySelectorAll(".nav-link").forEach((button) => {
    button.addEventListener("click", () => switchView(button.dataset.view));
  });
  document.querySelectorAll("[data-view-link]").forEach((link) => {
    link.addEventListener("click", (event) => {
      event.preventDefault();
      switchView(link.dataset.viewLink);
    });
  });

  const initial = window.location.hash.slice(1);
  if (["quick", "github", "instagram", "telegram"].includes(initial)) switchView(initial);
}

document.getElementById("quick-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const username = document.getElementById("quick-username").value.trim();
  const message = document.getElementById("quick-message");
  const target = document.getElementById("quick-results");
  message.classList.add("hidden");
  target.replaceChildren(element("div", { className: "empty", text: `Checking ${username}…` }));

  try {
    const payload = await api("/api/check", {
      method: "POST",
      body: JSON.stringify({
        username,
        force_refresh: document.getElementById("quick-force").checked,
      }),
    });
    renderQuickResults(payload.results);
    await Promise.all(["github", "instagram", "telegram"].map(refreshHistory));
  } catch (error) {
    target.replaceChildren();
    message.textContent = error.message;
    message.classList.remove("hidden");
  }
});

initialize().catch((error) => {
  const message = document.getElementById("quick-message");
  message.textContent = `NameScope could not initialize: ${error.message}`;
  message.classList.remove("hidden");
});
