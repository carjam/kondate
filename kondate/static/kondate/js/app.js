/* kondate: progressive enhancement only. Every action here also works as a
   plain form post or link without JavaScript. */
(function () {
  "use strict";

  var store = {
    get: function (key) { try { return localStorage.getItem(key); } catch (e) { return null; } },
    set: function (key, value) { try { localStorage.setItem(key, value); } catch (e) { /* private mode */ } }
  };

  function $(sel, root) { return (root || document).querySelector(sel); }
  function $$(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }

  /* Quick-plan sheet (week page) ------------------------------------------ */
  function initPlanner() {
    var dialog = $("#planner");
    if (!dialog || typeof dialog.showModal !== "function") return;
    var form = $("#planner-form", dialog);
    var search = $("#planner-search", dialog);
    var note = $("#planner-note", dialog);
    var title = $("#planner-title", dialog);
    var rows = $$("li[data-search]", dialog);
    var suggestions = $("[data-suggestions]", dialog);
    var noMatch = $("[data-no-match]", dialog);

    function filter() {
      var q = search.value.trim().toLowerCase();
      var shown = 0;
      rows.forEach(function (li) {
        var hit = !q || li.getAttribute("data-search").indexOf(q) !== -1;
        li.hidden = !hit;
        if (hit) shown++;
      });
      if (suggestions) suggestions.hidden = !!q;
      noMatch.hidden = shown > 0;
    }

    $$("[data-plan-day]").forEach(function (link) {
      link.addEventListener("click", function (event) {
        event.preventDefault();
        $("#planner-date", dialog).value = link.getAttribute("data-plan-day");
        title.textContent = link.getAttribute("data-day-label");
        search.value = "";
        note.value = "";
        filter();
        dialog.showModal();
        // Don't pop the keyboard up on phones; the list is the main target.
        if (window.matchMedia("(hover: hover)").matches) search.focus();
      });
    });

    search.addEventListener("input", filter);
    search.addEventListener("keydown", function (event) {
      // Enter picks the first visible recipe.
      if (event.key !== "Enter") return;
      event.preventDefault();
      var first = rows.filter(function (li) { return !li.hidden; })[0];
      if (first) form.requestSubmit($("button", first));
    });

    $$("[data-note]", dialog).forEach(function (chip) {
      chip.addEventListener("click", function () {
        note.value = chip.getAttribute("data-note");
        form.requestSubmit();
      });
    });

    $("[data-close]", dialog).addEventListener("click", function () { dialog.close(); });
    dialog.addEventListener("click", function (event) {
      if (event.target === dialog) dialog.close(); // backdrop
    });
  }

  /* Shopping list ----------------------------------------------------------- */
  function initShopping() {
    if (!document.body.classList.contains("shopping-page")) return;
    var text = $("[data-text]");
    var hideToggle = $("[data-hide-done]");

    function refreshCounts() {
      var counted = $$("li[data-counted]");
      var left = counted.filter(function (li) { return !li.classList.contains("done"); }).length;
      var total = counted.length;
      var remaining = $("[data-remaining]");
      if (remaining) remaining.textContent = left;
      var bar = $("[data-progress] .bar");
      if (bar && total) {
        bar.setAttribute("aria-valuenow", String(total - left));
        $("span", bar).style.width = Math.round(((total - left) / total) * 100) + "%";
      }
    }

    // Ticks can finish out of order; only the newest refresh may write the text.
    var textVersion = 0;
    function refreshText() {
      if (!text) return;
      var version = ++textVersion;
      fetch(text.getAttribute("data-src"), { credentials: "same-origin" })
        .then(function (r) { return r.ok ? r.text() : Promise.reject(r.status); })
        .then(function (body) { if (version === textVersion) text.value = body; })
        .catch(function () { /* keep the last good copy */ });
    }

    var pending = new WeakMap();
    document.addEventListener("submit", function (event) {
      var form = event.target;
      if (!form.classList.contains("check")) return;
      event.preventDefault();
      var input = $("input[name=checked]", form);
      var button = $("button", form);
      var li = form.closest("li");
      var next = input.value === "1";
      // Optimistic: flip now, roll back (via a full post) if the server says no.
      li.classList.toggle("done", next);
      button.setAttribute("aria-checked", String(next));
      input.value = next ? "0" : "1";
      refreshCounts();
      var body = new FormData(form);
      body.set("checked", next ? "1" : "0");
      // Send one item's requests in order, so a quick tick-untick can't arrive
      // reversed and leave the server disagreeing with the screen.
      var previous = pending.get(form) || Promise.resolve();
      var request = previous.then(function () {
        return fetch(form.action, {
          method: "POST", body: body, credentials: "same-origin",
          headers: { "Accept": "application/json" }
        });
      }).then(function (r) {
        if (!r.ok) throw new Error(r.status);
        refreshText();
      });
      pending.set(form, request.catch(function () {}));
      request.catch(function () { window.location.reload(); });
    });

    if (hideToggle) {
      hideToggle.checked = store.get("kondate.hideDone") === "1";
      document.body.classList.toggle("hide-done", hideToggle.checked);
      hideToggle.addEventListener("change", function () {
        document.body.classList.toggle("hide-done", hideToggle.checked);
        store.set("kondate.hideDone", hideToggle.checked ? "1" : "0");
      });
    }

    var copy = $("[data-copy]");
    if (copy && text) {
      copy.addEventListener("click", function () {
        var label = $("span", copy);
        function done(msg) {
          label.textContent = msg;
          copy.classList.add("is-done");
          setTimeout(function () { label.textContent = "Copy list"; copy.classList.remove("is-done"); }, 1800);
        }
        if (navigator.clipboard && window.isSecureContext) {
          navigator.clipboard.writeText(text.value).then(function () { done("Copied"); }, fallback);
        } else {
          fallback();
        }
        function fallback() {
          var details = text.closest("details");
          if (details) details.open = true;
          text.focus();
          text.select();
          try { done(document.execCommand("copy") ? "Copied" : "Select & copy"); } catch (e) { done("Select & copy"); }
        }
      });
    }

    var mail = $("[data-mailto]");
    if (mail && text) {
      mail.addEventListener("click", function () {
        var to = mail.getAttribute("data-email") || "";
        mail.href = "mailto:" + encodeURIComponent(to) +
          "?subject=" + encodeURIComponent(text.value.split("\n")[0]) +
          "&body=" + encodeURIComponent(text.value);
      });
    }

    var share = $("[data-share]");
    if (share && text && navigator.share) {
      share.hidden = false;
      share.addEventListener("click", function () {
        navigator.share({ title: text.value.split("\n")[0], text: text.value }).catch(function () {});
      });
    }
  }

  /* Live filtering for recipes and ingredients ------------------------------ */
  function initLiveFilters() {
    $$("[data-live-filter]").forEach(function (bar) {
      var target = $(bar.getAttribute("data-live-filter"));
      if (!target) return;
      var rows = $$(bar.getAttribute("data-filter-rows") || "[data-search]", target);
      var input = $("input[type=search]", bar);
      var buyRadios = $$("[data-filter-buy]", bar);
      var noMatch = $("[data-no-match]");
      var groups = $$("[data-group]", target);

      function apply() {
        var q = input.value.trim().toLowerCase();
        var buy = (buyRadios.filter(function (r) { return r.checked; })[0] || {}).value || "";
        var shown = 0;
        rows.forEach(function (row) {
          var hit = row.getAttribute("data-search").indexOf(q) !== -1 &&
            (!buy || row.getAttribute("data-buy") === buy);
          row.hidden = !hit;
          if (hit) shown++;
        });
        // Hide an aisle heading when none of its rows are showing.
        groups.forEach(function (group) {
          var el = group.nextElementSibling, any = false;
          while (el && !el.hasAttribute("data-group")) { if (!el.hidden) any = true; el = el.nextElementSibling; }
          group.hidden = !any;
        });
        if (noMatch) noMatch.hidden = shown > 0;
      }

      input.addEventListener("input", apply);
      buyRadios.forEach(function (r) { r.addEventListener("change", apply); });
      // Sort is server-side: submit when it changes.
      $$("[data-autosubmit]", bar).forEach(function (r) {
        r.addEventListener("change", function () { bar.requestSubmit(); });
      });
      apply();
    });
  }

  /* Recipe form: add ingredient rows ---------------------------------------- */
  function initRecipeForm() {
    var add = $("#add-row");
    if (!add) return;
    var total = $("#id_items-TOTAL_FORMS");
    var rows = $("#itemrows");
    var tpl = $("#itemrow-template");
    add.addEventListener("click", function () {
      var n = parseInt(total.value, 10);
      rows.insertAdjacentHTML("beforeend", tpl.innerHTML.replace(/__prefix__/g, String(n)));
      total.value = String(n + 1);
      $("input", rows.lastElementChild).focus();
    });
  }

  /* Double-submit guard ----------------------------------------------------- */
  // A double tap on a phone posts twice: two copies of last week, two extras.
  // Runs last (bubble phase on window), so forms handled by fetch or cancelled
  // by a confirm() are left alone.
  function initSubmitGuard() {
    window.addEventListener("submit", function (event) {
      var form = event.target;
      if (event.defaultPrevented) return;
      if (form.hasAttribute("data-submitting")) { event.preventDefault(); return; }
      form.setAttribute("data-submitting", "");
      // Back/forward cache can restore the page with the flag still set.
      window.addEventListener("pageshow", function () { form.removeAttribute("data-submitting"); }, { once: true });
    });
  }

  /* Confirm destructive forms ----------------------------------------------- */
  function initConfirms() {
    $$("form[data-confirm]").forEach(function (form) {
      form.addEventListener("submit", function (event) {
        if (!window.confirm(form.getAttribute("data-confirm"))) event.preventDefault();
      });
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    initPlanner();
    initShopping();
    initLiveFilters();
    initRecipeForm();
    initConfirms();
    initSubmitGuard();
  });
})();
