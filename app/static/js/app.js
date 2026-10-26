/* Personal Finance Advisor Bot - front-end behaviour (no inline scripts needed). */
(function () {
  "use strict";

  // Auto-submit selects (month picker)
  document.querySelectorAll("[data-autosubmit]").forEach(function (el) {
    el.addEventListener("change", function () { el.form.submit(); });
  });

  // Confirm destructive actions
  document.querySelectorAll("form[data-confirm]").forEach(function (form) {
    form.addEventListener("submit", function (e) {
      if (!window.confirm(form.getAttribute("data-confirm"))) { e.preventDefault(); }
    });
  });

  // ---------- Charts ----------
  var dataEl = document.getElementById("chart-data");
  if (dataEl && typeof Chart !== "undefined") {
    var d = JSON.parse(dataEl.textContent);
    var cur = d.currency || "";
    var fmt = function (v) { return cur + Number(v).toLocaleString(cur === "₹" ? "en-IN" : "en-US", { maximumFractionDigits: 0 }); };
    Chart.defaults.font.family = '-apple-system, BlinkMacSystemFont, "Segoe UI", Inter, sans-serif';
    Chart.defaults.color = "#64748b";
    var money = { callbacks: { label: function (c) { return " " + (c.dataset.label ? c.dataset.label + ": " : (c.label + ": ")) + fmt(c.parsed.y !== undefined ? c.parsed.y : c.parsed); } } };
    var axisMoney = { ticks: { callback: function (v) { return fmt(v); } }, grid: { color: "#eef2f6" }, beginAtZero: true };

    var make = function (id, config) { var el = document.getElementById(id); if (el) { new Chart(el, config); } };

    if (d.category) {
      make("categoryChart", { type: "doughnut",
        data: { labels: d.category.labels, datasets: [{ data: d.category.values, backgroundColor: d.category.colors, borderWidth: 2 }] },
        options: { maintainAspectRatio: false, cutout: "62%", plugins: { legend: { position: "bottom" },
          tooltip: { callbacks: { label: function (c) { return " " + c.label + ": " + fmt(c.parsed); } } } } } });
    }
    if (d.monthly) {
      make("incomeExpenseChart", { type: "bar",
        data: { labels: d.monthly.labels, datasets: [
          { label: "Income", data: d.monthly.income, backgroundColor: "#10b981", borderRadius: 6 },
          { label: "Expenses", data: d.monthly.expense, backgroundColor: "#f87171", borderRadius: 6 }] },
        options: { maintainAspectRatio: false, plugins: { legend: { position: "bottom" }, tooltip: money }, scales: { y: axisMoney, x: { grid: { display: false } } } } });
    }
    if (d.daily) {
      make("trendChart", { type: "line",
        data: { labels: d.daily.labels, datasets: [{ label: "Daily spending", data: d.daily.values, borderColor: "#059669",
          backgroundColor: "rgba(5,150,105,.12)", fill: true, tension: .3, pointRadius: 2 }] },
        options: { maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: money }, scales: { y: axisMoney, x: { grid: { display: false } } } } });
    }
    if (d.budget && d.budget.labels.length) {
      make("budgetChart", { type: "bar",
        data: { labels: d.budget.labels, datasets: [
          { label: "Budget", data: d.budget.budget, backgroundColor: "#93c5fd", borderRadius: 6 },
          { label: "Actual", data: d.budget.actual, backgroundColor: "#34d399", borderRadius: 6 }] },
        options: { maintainAspectRatio: false, plugins: { legend: { position: "bottom" }, tooltip: money }, scales: { y: axisMoney, x: { grid: { display: false } } } } });
    }
  }

  // ---------- AI advisor chat ----------
  var chatForm = document.getElementById("chat-form");
  if (chatForm) {
    var log = document.getElementById("chat-log");
    var input = document.getElementById("chat-input");
    var send = document.getElementById("chat-send");
    var csrf = document.querySelector('meta[name="csrf-token"]').content;

    var add = function (text, cls) {
      var div = document.createElement("div");
      div.className = "chat-msg " + cls;
      div.textContent = text;           // textContent: never inject HTML
      log.appendChild(div);
      log.scrollTop = log.scrollHeight;
      return div;
    };
    var note = function (text) {
      var div = document.createElement("div");
      div.className = "chat-note"; div.textContent = text; log.appendChild(div);
    };

    var ask = function (question) {
      add(question, "chat-user");
      var pending = add("Thinking…", "chat-bot");
      send.disabled = true;
      fetch(chatForm.getAttribute("data-url"), {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
        credentials: "same-origin",
        body: JSON.stringify({ question: question, year: Number(chatForm.dataset.year), month: Number(chatForm.dataset.month) })
      }).then(function (r) { return r.json().then(function (j) { return { ok: r.ok, body: j }; }); })
        .then(function (res) {
          pending.textContent = res.ok ? res.body.reply : (res.body.error || "Something went wrong.");
          if (res.ok) { note(res.body.source === "ai" ? "Answered with your configured AI provider" : (res.body.note || "Answered by the built-in advisor")); }
        })
        .catch(function () { pending.textContent = "Sorry, I could not reach the server. Please refresh and try again."; })
        .finally(function () { send.disabled = false; log.scrollTop = log.scrollHeight; });
    };

    chatForm.addEventListener("submit", function (e) {
      e.preventDefault();
      var q = input.value.trim();
      if (!q) { return; }
      input.value = "";
      ask(q);
    });
    document.querySelectorAll("[data-question]").forEach(function (btn) {
      btn.addEventListener("click", function () { ask(btn.getAttribute("data-question")); });
    });
  }
})();
