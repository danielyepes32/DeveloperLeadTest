"use strict";

// ----------------------------------------------------------------- state + api
const state = { token: localStorage.getItem("token"), user: null, currentNeg: null };

const $ = (id) => document.getElementById(id);

async function api(path, { method = "GET", body, idempotent = false } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (state.token) headers["Authorization"] = `Bearer ${state.token}`;
  if (idempotent) headers["Idempotency-Key"] = crypto.randomUUID();

  const res = await fetch(path, { method, headers, body: body ? JSON.stringify(body) : undefined });
  const data = res.status === 204 ? null : await res.json().catch(() => null);
  if (!res.ok) {
    const msg = data?.message || data?.detail || `Error ${res.status}`;
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  return data;
}

// ----------------------------------------------------------------- formatting
const copFmt = new Intl.NumberFormat("es-CO", { style: "currency", currency: "COP", maximumFractionDigits: 0 });

function money(n, currency) {
  const value = Number(n);
  if (!Number.isFinite(value)) return String(n);
  if (!currency || currency === "COP") return copFmt.format(value);
  return `${value.toLocaleString("es-CO")} ${currency}`;
}

function formatDate(iso) {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleString("es-CO");
}

// ----------------------------------------------------------------- feedback
let toastTimer;
function toast(msg, kind = "") {
  const t = $("toast");
  t.textContent = msg;
  t.className = `toast ${kind}`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.add("hidden"), 3500);
}

/** Wrap an async form/button submit with loading + anti-double-submit. */
async function withLoading(btn, fn) {
  if (!btn || btn.disabled) return;
  btn.disabled = true;
  btn.classList.add("is-loading");
  try {
    return await fn();
  } finally {
    btn.disabled = false;
    btn.classList.remove("is-loading");
  }
}

function submitButton(form) {
  return form.querySelector('button[type="submit"], button[data-loading]');
}

// ----------------------------------------------------------------- accessible modal
const modalState = { onConfirm: null, lastFocus: null };

function openModal({ title, amount = "", message = "", confirmLabel = "Confirmar", onConfirm }) {
  modalState.onConfirm = onConfirm;
  modalState.lastFocus = document.activeElement;
  $("modal-title").textContent = title;
  $("modal-amount").value = amount;
  $("modal-message").value = message;
  $("modal-confirm").textContent = confirmLabel;
  const err = $("modal-error");
  err.textContent = "";
  err.classList.add("hidden");
  $("modal-backdrop").classList.remove("hidden");
  $("modal-amount").focus();
}

function closeModal() {
  $("modal-backdrop").classList.add("hidden");
  modalState.onConfirm = null;
  if (modalState.lastFocus && typeof modalState.lastFocus.focus === "function") {
    modalState.lastFocus.focus();
  }
}

function modalError(msg) {
  const err = $("modal-error");
  err.textContent = msg;
  err.classList.remove("hidden");
}

$("modal-cancel").addEventListener("click", closeModal);
$("modal-backdrop").addEventListener("mousedown", (e) => {
  if (e.target === $("modal-backdrop")) closeModal();
});

$("modal-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const amount = Number($("modal-amount").value);
  if (!Number.isFinite(amount) || amount <= 0) {
    modalError("Ingresa un monto válido mayor a 0.");
    $("modal-amount").focus();
    return;
  }
  const message = $("modal-message").value.trim();
  await withLoading($("modal-confirm"), async () => {
    try {
      await modalState.onConfirm({ amount, message });
      closeModal();
    } catch (err) {
      modalError(err.message);
    }
  });
});

// Keyboard: Escape closes, Tab is trapped within the modal.
document.addEventListener("keydown", (e) => {
  if ($("modal-backdrop").classList.contains("hidden")) return;
  if (e.key === "Escape") { closeModal(); return; }
  if (e.key !== "Tab") return;
  const focusable = $("modal").querySelectorAll('input, button:not(:disabled)');
  if (!focusable.length) return;
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
  else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
});

// ----------------------------------------------------------------- auth UI
document.querySelectorAll(".tab").forEach((tab) =>
  tab.addEventListener("click", () => {
    const which = tab.dataset.tab;
    document.querySelectorAll(".tab").forEach((t) => {
      const active = t === tab;
      t.classList.toggle("active", active);
      t.setAttribute("aria-selected", String(active));
    });
    $("login-form").classList.toggle("hidden", which !== "login");
    $("register-form").classList.toggle("hidden", which !== "register");
  })
);

$("register-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target;
  const f = Object.fromEntries(new FormData(form));
  await withLoading(submitButton(form), async () => {
    try {
      await api("/auth/register", { method: "POST", body: f });
      toast("Cuenta creada. Ahora ingresa.", "ok");
      document.querySelector('.tab[data-tab="login"]').click();
      $("login-email").value = f.email;
      $("login-password").focus();
    } catch (err) { toast(err.message, "bad"); }
  });
});

$("login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target;
  const f = Object.fromEntries(new FormData(form));
  await withLoading(submitButton(form), async () => {
    try {
      const { access_token } = await api("/auth/login", { method: "POST", body: f });
      state.token = access_token;
      localStorage.setItem("token", access_token);
      await boot();
    } catch (err) { toast(err.message, "bad"); }
  });
});

$("logout").addEventListener("click", () => {
  localStorage.removeItem("token");
  location.reload();
});

// ----------------------------------------------------------------- client: new request
$("request-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target;
  const f = Object.fromEntries(new FormData(form));
  f.quantity = Number(f.quantity);
  await withLoading(submitButton(form), async () => {
    try {
      await api("/requests", { method: "POST", body: f, idempotent: true });
      form.reset();
      $("req-qty").value = "1";
      toast("Solicitud creada", "ok");
      await refresh();
    } catch (err) { toast(err.message, "bad"); }
  });
});

// ----------------------------------------------------------------- render helpers
function emptyEl(text) {
  const p = document.createElement("p");
  p.className = "empty";
  p.textContent = text;
  return p;
}

function badge(status) {
  const span = document.createElement("span");
  span.className = `badge ${status}`;
  span.textContent = status;
  return span;
}

// ----------------------------------------------------------------- render lists
async function refresh() {
  const isSupplier = state.user.role === "supplier";
  $("requests-title").textContent = isSupplier ? "Solicitudes abiertas (mercado)" : "Mis solicitudes";
  $("stat-requests-label").textContent = isSupplier ? "Solicitudes abiertas" : "Mis solicitudes";

  const [requests, negs] = await Promise.all([api("/requests"), api("/negotiations")]);
  renderRequests(requests, isSupplier);
  renderNegotiations(negs);
  updateSummary(requests, negs);
}

function renderRequests(requests, isSupplier) {
  const el = $("requests");
  el.innerHTML = "";
  if (!requests.length) {
    el.appendChild(emptyEl(isSupplier ? "No hay solicitudes abiertas por ahora." : "Aún no tienes solicitudes. Crea una arriba."));
    return;
  }
  for (const r of requests) {
    const div = document.createElement("div");
    div.className = "item";

    const main = document.createElement("div");
    main.className = "item-main";
    const title = document.createElement("strong");
    title.textContent = r.product_name;
    main.append(title, document.createTextNode(` ×${r.quantity}`));
    if (r.description) {
      const small = document.createElement("small");
      small.textContent = r.description;
      main.appendChild(small);
    }
    div.appendChild(main);

    if (isSupplier && r.status === "open") {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.textContent = "Ofertar";
      btn.addEventListener("click", () => makeOffer(r.id, r.product_name, btn));
      div.appendChild(btn);
    } else {
      div.appendChild(badge(r.status));
    }
    el.appendChild(div);
  }
}

function renderNegotiations(negs) {
  const el = $("negotiations");
  el.innerHTML = "";
  if (!negs.length) {
    el.appendChild(emptyEl("Aún no tienes negociaciones."));
    return;
  }
  for (const n of negs) {
    const div = document.createElement("div");
    div.className = "item";
    div.tabIndex = 0;
    div.setAttribute("role", "button");

    const main = document.createElement("div");
    main.className = "item-main";
    const title = document.createElement("strong");
    title.textContent = `Negociación #${n.id}`;
    main.append(title, document.createTextNode(` · solicitud ${n.request_id}`));
    if (n.agreed_amount) {
      const small = document.createElement("small");
      small.textContent = `Acordado: ${money(n.agreed_amount, n.currency)}`;
      main.appendChild(small);
    }
    div.append(main, badge(n.status));

    const open = () => openNegotiation(n.id);
    div.addEventListener("click", open);
    div.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(); }
    });
    el.appendChild(div);
  }
}

function updateSummary(requests, negs) {
  $("summary").classList.remove("hidden");
  $("stat-requests").textContent = String(requests.length);
  const active = negs.filter((n) => n.status === "active");
  $("stat-negs").textContent = String(active.length);
  const myTurn = active.filter((n) => n.last_actor_id != null && n.last_actor_id !== state.user.id).length;
  if (Number.isFinite(myTurn)) $("stat-turn").textContent = String(myTurn);
  // Hide the "tu turno" stat if the API list doesn't expose enough info.
  $("stat-turn-wrap").classList.toggle("hidden", !negs.some((n) => "last_actor_id" in n));
}

// ----------------------------------------------------------------- offers / counters via modal
function makeOffer(requestId, productName, triggerBtn) {
  openModal({
    title: `Ofertar por ${productName}`,
    message: "Oferta inicial",
    confirmLabel: "Enviar oferta",
    onConfirm: async ({ amount, message }) => {
      const neg = await api(`/requests/${requestId}/offers`, {
        method: "POST", idempotent: true,
        body: { amount, currency: "COP", message: message || "Oferta inicial" },
      });
      toast("Oferta enviada", "ok");
      await refresh();
      await openNegotiation(neg.id);
    },
  });
  if (triggerBtn) modalState.lastFocus = triggerBtn;
}

// ----------------------------------------------------------------- negotiation detail
async function openNegotiation(id) {
  state.currentNeg = id;
  let neg;
  try {
    neg = await api(`/negotiations/${id}`);
  } catch (err) { toast(err.message, "bad"); return; }

  $("detail").classList.remove("hidden");
  $("detail-id").textContent = `#${neg.id}`;
  const statusEl = $("detail-status");
  statusEl.textContent = neg.status;
  statusEl.className = `badge ${neg.status}`;

  renderProposals(neg.proposals);
  renderTurn(neg);
  $("detail").scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function renderProposals(proposals) {
  const tl = $("proposals");
  tl.innerHTML = "";
  for (const p of proposals) {
    const b = document.createElement("div");
    b.className = `bubble ${p.actor_role}`;

    const amount = document.createElement("span");
    amount.className = "amount";
    amount.textContent = money(p.amount, p.currency);

    const meta = document.createElement("span");
    meta.className = "meta";
    meta.textContent = `${p.actor_role} · ${p.kind} · ${formatDate(p.created_at)}`;

    b.append(amount, meta);
    if (p.message) {
      const msg = document.createElement("div");
      msg.className = "msg";
      msg.textContent = p.message;
      b.appendChild(msg);
    }
    tl.appendChild(b);
  }
}

function renderTurn(neg) {
  const banner = $("turn-banner");
  const actions = $("actions");
  actions.innerHTML = "";
  banner.className = "turn-banner hidden";
  banner.textContent = "";

  const last = neg.proposals[neg.proposals.length - 1];
  const isActive = neg.status === "active";
  const myTurn = isActive && last && last.actor_id !== state.user.id;

  if (myTurn) {
    banner.textContent = "✅ Es tu turno: responde a la última propuesta.";
    banner.className = "turn-banner mine";

    const accept = document.createElement("button");
    accept.className = "ok";
    accept.type = "button";
    accept.textContent = `Aceptar ${money(last.amount, last.currency)}`;
    accept.addEventListener("click", () => accept_(neg.id, last, accept));

    const counter = document.createElement("button");
    counter.type = "button";
    counter.textContent = "Contraofertar";
    counter.addEventListener("click", () => counterOffer(neg.id, last, counter));

    const reject = document.createElement("button");
    reject.className = "danger";
    reject.type = "button";
    reject.textContent = "Rechazar";
    reject.addEventListener("click", () => reject_(neg.id, reject));

    actions.append(accept, counter, reject);
  } else if (isActive) {
    banner.textContent = "⏳ Esperando respuesta de la contraparte.";
    banner.className = "turn-banner theirs";
  }
}

// ----------------------------------------------------------------- decisions
async function postDecision(id, act, body) {
  await api(`/negotiations/${id}/${act}`, { method: "POST", body, idempotent: true });
  await refresh();
  await openNegotiation(id);
}

function accept_(id, last, btn) {
  withLoading(btn, async () => {
    try {
      await postDecision(id, "accept");
      toast(`Acuerdo cerrado en ${money(last.amount, last.currency)}`, "ok");
    } catch (err) { toast(err.message, "bad"); }
  });
}

function reject_(id, btn) {
  withLoading(btn, async () => {
    try {
      await postDecision(id, "reject");
      toast("Negociación rechazada");
    } catch (err) { toast(err.message, "bad"); }
  });
}

function counterOffer(id, last, triggerBtn) {
  openModal({
    title: "Tu contraoferta",
    message: "Contraoferta",
    confirmLabel: "Enviar contraoferta",
    onConfirm: async ({ amount, message }) => {
      await postDecision(id, "counter", { amount, message: message || "Contraoferta" });
      toast("Contraoferta enviada", "ok");
    },
  });
  if (triggerBtn) modalState.lastFocus = triggerBtn;
}

// ----------------------------------------------------------------- boot
async function boot() {
  state.user = await api("/auth/me");
  $("auth").classList.add("hidden");
  $("app").classList.remove("hidden");
  $("session").classList.remove("hidden");
  $("who").textContent = state.user.full_name;
  const roleBadge = $("role-badge");
  roleBadge.textContent = state.user.role === "supplier" ? "Proveedor" : "Cliente";
  $("client-new").classList.toggle("hidden", state.user.role !== "client");
  await refresh();
}

if (state.token) {
  boot().catch(() => { localStorage.removeItem("token"); });
}
