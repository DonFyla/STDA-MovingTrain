/**
 * Lightweight, task-based booking guide.
 *
 * Renders a floating "Need help?" widget on pages that opt-in with
 * [data-guide-page]. Suggestions are rule-based and context-aware (balance,
 * upcoming sessions, coach type, etc.). No external dependencies.
 */
(function () {
  const GUIDE_HIDDEN_KEY = "mt-guide-hidden";
  const HIGHLIGHT_CLASSES = [
    "ring-4",
    "ring-brand-400",
    "ring-offset-2",
    "transition-all",
    "duration-500",
  ];

  const body = document.body;
  const enabled = body.dataset.guideEnabled !== "false";
  if (!enabled || localStorage.getItem(GUIDE_HIDDEN_KEY)) return;

  const pageEl = document.querySelector("[data-guide-page]");
  const page = pageEl ? pageEl.dataset.guidePage : null;
  if (!page) return;

  const root = document.createElement("div");
  root.id = "booking-guide-root";
  document.body.appendChild(root);

  let open = false;

  function buildUI() {
    root.innerHTML = `
      <div class="fixed bottom-4 left-4 right-4 md:left-auto md:right-8 md:bottom-8 md:w-80 z-50 flex flex-col items-end gap-3">
        <div id="guide-panel" class="hidden w-full bg-white rounded-2xl shadow-2xl border border-brand-100 p-5 transform transition-all" role="dialog" aria-live="polite" aria-label="Booking help">
          <div class="flex items-start justify-between mb-4">
            <div>
              <h3 class="font-bold text-brand-900">What would you like to do?</h3>
              <p class="text-xs text-brand-500 mt-0.5">${getPageSubtitle()}</p>
            </div>
            <button type="button" id="guide-close" class="text-brand-400 hover:text-brand-700 text-2xl leading-none" aria-label="Close help">×</button>
          </div>
          <div id="guide-actions" class="space-y-2"></div>
          <div class="mt-4 pt-3 border-t border-brand-100 text-xs text-brand-400 flex justify-between items-center">
            <span>Still stuck?</span>
            <a href="https://wa.link/uj48gk" target="_blank" rel="noopener noreferrer" class="text-brand-600 hover:underline font-medium">Chat with us</a>
          </div>
        </div>
        <button type="button" id="guide-toggle" class="group flex items-center gap-2 px-4 py-3 bg-brand-600 text-white rounded-full shadow-lg hover:bg-brand-700 transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-brand-600" aria-label="Open booking help">
          <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
          </svg>
          <span class="text-sm font-medium">Need help?</span>
        </button>
      </div>
    `;
    bindEvents();
    renderActions();
  }

  function getPageSubtitle() {
    switch (page) {
      case "dashboard":
        return "Pick a task and we'll take you there.";
      case "tutors":
        return "Choose the coaching option that fits you.";
      case "book_coach":
        return "Not sure which booking type to pick?";
      default:
        return "How can we help?";
    }
  }

  function getActions() {
    const actions = [];
    const isAuthenticated = body.dataset.userAuthenticated === "true";

    if (page === "dashboard") {
      const balance = parseFloat(pageEl.dataset.userBalance || "0") || 0;
      const upcoming = parseInt(pageEl.dataset.upcomingCount || "0", 10) || 0;
      const tutorsUrl = pageEl.dataset.tutorsUrl || "/tutors/";
      const buyPointsUrl = pageEl.dataset.buyPointsUrl || "/payments/buy-points/";
      const quizUrl = pageEl.dataset.quizUrl || "/quiz/";

      if (upcoming > 0) {
        actions.push({
          label: "Join my next session",
          desc: "See your upcoming classes and meeting links.",
          handler: () => highlight("#upcoming-sessions"),
        });
      }
      actions.push({
        label: "Book a single flexible class",
        desc: "Pay with points for one class at a time.",
        url: tutorsUrl,
      });
      actions.push({
        label: "Start a monthly subscription",
        desc: "Fixed weekly classes billed every month.",
        url: tutorsUrl,
      });
      if (balance === 0) {
        actions.push({
          label: "Buy more points",
          desc: "Top up so you can book flexible classes.",
          url: buyPointsUrl,
        });
      }
      actions.push({
        label: "Take the chess quiz",
        desc: "Find the right course level for you.",
        url: quizUrl,
      });
    }

    if (page === "tutors") {
      actions.push({
        label: "Book a flexible points session",
        desc: "Choose a regular coach and pay per class with points.",
        handler: () => switchTabAndHighlight("normal", "#panel-normal"),
      });
      actions.push({
        label: "Start a monthly subscription",
        desc: "Pick a regular coach for weekly recurring classes.",
        handler: () => switchTabAndHighlight("normal", "#panel-normal"),
      });
      actions.push({
        label: "Book elite/special coaching",
        desc: "One-on-one sessions with titled players.",
        handler: () => switchTabAndHighlight("special", "#panel-special"),
      });
    }

    if (page === "book_coach") {
      actions.push({
        label: "Pay per class with points",
        desc: "Use your points for a single flexible class.",
        handler: () => switchTabAndHighlight("points", "#panel-points"),
      });
      actions.push({
        label: "Subscribe monthly",
        desc: "Set up automatic weekly classes.",
        handler: () => switchTabAndHighlight("recurring", "#panel-recurring"),
      });
      if (document.getElementById("tab-special")) {
        actions.push({
          label: "Book an elite package",
          desc: "Buy a discounted bundle of special sessions.",
          handler: () => switchTabAndHighlight("special", "#panel-special"),
        });
      }
    }

    if (!isAuthenticated && page !== "dashboard") {
      actions.push({
        label: "Log in or sign up",
        desc: "You need an account to complete a booking.",
        url: "/accounts/login/",
      });
    }

    return actions;
  }

  function renderActions() {
    const container = document.getElementById("guide-actions");
    if (!container) return;
    const actions = getActions();
    if (!actions.length) {
      root.remove();
      return;
    }
    container.innerHTML = actions
      .map(
        (action, index) => `
        <button type="button" data-action-index="${index}" class="w-full text-left px-4 py-3 rounded-xl border border-brand-100 hover:border-brand-300 hover:bg-brand-50 transition-colors group focus:outline-none focus:ring-2 focus:ring-brand-200">
          <span class="block text-sm font-medium text-brand-900 group-hover:text-brand-700">${action.label}</span>
          ${action.desc ? `<span class="block text-xs text-brand-500 mt-0.5">${action.desc}</span>` : ""}
        </button>
      `
      )
      .join("");

    container.querySelectorAll("button[data-action-index]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const idx = parseInt(btn.dataset.actionIndex, 10);
        executeAction(actions[idx]);
      });
    });
  }

  function executeAction(action) {
    if (action.url) {
      window.location.href = action.url;
      return;
    }
    if (action.handler) {
      action.handler();
    }
    setOpen(false);
  }

  function bindEvents() {
    const toggle = document.getElementById("guide-toggle");
    const close = document.getElementById("guide-close");
    if (toggle) toggle.addEventListener("click", () => setOpen(!open));
    if (close) close.addEventListener("click", () => setOpen(false));

    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && open) setOpen(false);
    });

    document.addEventListener("click", (e) => {
      if (open && !root.contains(e.target)) setOpen(false);
    });
  }

  function setOpen(value) {
    open = value;
    const panel = document.getElementById("guide-panel");
    if (!panel) return;
    panel.classList.toggle("hidden", !open);
  }

  function switchTabAndHighlight(tabName, panelSelector) {
    if (typeof switchTab === "function") {
      switchTab(tabName);
    }
    setTimeout(() => {
      highlight(panelSelector || `#panel-${tabName}`);
    }, 50);
  }

  function highlight(selector) {
    const el = document.querySelector(selector);
    if (!el) return;
    el.classList.add(...HIGHLIGHT_CLASSES);
    el.setAttribute("tabindex", "-1");
    el.scrollIntoView({ behavior: "smooth", block: "center" });
    setTimeout(() => {
      el.classList.remove(...HIGHLIGHT_CLASSES);
      el.removeAttribute("tabindex");
    }, 2500);
  }

  // Booking stepper helper exposed for page-specific scripts.
  window.updateBookingStepper = function (activeStep) {
    const stepper = document.getElementById("booking-stepper");
    if (!stepper) return;
    const steps = stepper.querySelectorAll("[data-step]");
    steps.forEach((step) => {
      const num = parseInt(step.dataset.step, 10);
      const circle = step.querySelector(".step-circle");
      const label = step.querySelector(".step-label");
      const line = step.querySelector(".step-line");

      if (circle) {
        circle.classList.remove("bg-brand-600", "border-brand-600", "text-white", "bg-white", "border-brand-200", "text-brand-600");
        if (num <= activeStep) {
          circle.classList.add("bg-brand-600", "border-brand-600", "text-white");
        } else {
          circle.classList.add("bg-white", "border-brand-200", "text-brand-600");
        }
      }
      if (label) {
        label.classList.remove("text-brand-900", "font-semibold", "text-brand-400");
        if (num <= activeStep) {
          label.classList.add("text-brand-900", "font-semibold");
        } else {
          label.classList.add("text-brand-400");
        }
      }
      if (line) {
        line.classList.remove("bg-brand-600", "bg-brand-200");
        line.classList.add(num < activeStep ? "bg-brand-600" : "bg-brand-200");
      }
    });
  };

  buildUI();
})();
