/**
 * Lightweight booking guide + onboarding tours.
 *
 * Renders a floating "Need help?" widget and can run one of several
 * page-aware tours:
 *   - Home tour for anonymous visitors
 *   - Student dashboard → tutors → book coach tour
 *   - Coach dashboard tour
 */
(function () {
  const GUIDE_HIDDEN_KEY = "mt-guide-hidden";
  const TOUR_ACTIVE_KEY = "mt-tour-active";
  const TOUR_STEP_KEY = "mt-tour-step";
  const TOUR_NAME_KEY = "mt-tour-name";
  const PENDING_STUDENT_TOUR_KEY = "mt-pending-student-tour";
  const PENDING_COACH_TOUR_KEY = "mt-pending-coach-tour";

  const TOUR_SEEN_KEYS = {
    home: "mt-home-tour-seen",
    student: "mt-student-tour-seen",
    coach: "mt-coach-tour-seen",
  };

  const HIGHLIGHT_CLASSES = [
    "ring-4",
    "ring-brand-400",
    "ring-offset-2",
    "transition-all",
    "duration-500",
  ];

  const HOME_TOUR_STEPS = [
    {
      page: "home",
      selector: '[data-tour="home-hero"]',
      title: "Welcome to Moving Train",
      text: "We help kids and adults fall in love with chess through world-class online coaching.",
      position: "bottom",
    },
    {
      page: "home",
      selector: '[data-tour="home-about"]',
      title: "Our Mission",
      text: "We build strategic thinking, problem-solving, and sportsmanship—one move at a time.",
      position: "top",
    },
    {
      page: "home",
      selector: '[data-tour="home-courses"]',
      title: "Programs for Every Level",
      text: "Choose from Beginner, Intermediate, or Expert courses based on your goals.",
      position: "top",
    },
    {
      page: "home",
      selector: '[data-tour="home-tutors"]',
      title: "Learn from the Best",
      text: "Our coaches include FIDE Masters, National Champions, and experienced educators.",
      position: "top",
    },
    {
      page: "home",
      selector: '[data-tour="home-cta"]',
      title: "Ready to Start?",
      text: "Create a free account to book a class, or browse our coaches first.",
      position: "top",
      actions: [
        { label: "Sign Up", key: "signup" },
        { label: "Browse Coaches", key: "tutors" },
      ],
    },
  ];

  const STUDENT_TOUR_STEPS = [
    {
      page: "dashboard",
      selector: null,
      title: "Welcome to your dashboard",
      text: "This is your home base. You can see your points, book classes, and manage subscriptions.",
    },
    {
      page: "dashboard",
      selector: '[data-tour="points-balance"]',
      title: "Points Balance",
      text: "Your points let you book flexible single classes. Buy more anytime.",
    },
    {
      page: "dashboard",
      selector: '[data-tour="quick-actions"]',
      title: "Quick Actions",
      text: "Jump straight to booking, buying points, taking the quiz, or getting help.",
    },
    {
      page: "dashboard",
      selector: "#upcoming-sessions",
      title: "Upcoming Sessions",
      text: "All your confirmed classes show here with join links.",
    },
    {
      page: "dashboard",
      selector: '[data-tour="monthly-bookings"]',
      title: "Monthly Bookings",
      text: "Your recurring subscriptions appear here. You can pay or cancel.",
    },
    {
      page: "tutors",
      selector: '[data-tour="tutors-tabs"]',
      title: "Regular vs Elite Coaches",
      text: "Regular coaches work with points or monthly plans. Elite coaches are pay-per-session for advanced training.",
    },
    {
      page: "tutors",
      selector: '[data-tour="coach-card"]',
      title: "Coach Card",
      text: "Each card shows the coach's details. Click Book a Session to continue.",
    },
    {
      page: "book_coach",
      selector: "#booking-stepper",
      title: "Follow the Steps",
      text: "The stepper shows where you are: choose type, pick date/time, fill info, and complete.",
    },
    {
      page: "book_coach",
      selector: '[data-tour="booking-tabs"]',
      title: "Choose Booking Type",
      text: "Pay with points, subscribe monthly, or book an elite package.",
    },
    {
      page: "book_coach",
      selector: '[data-tour="time-selection"]',
      title: "Pick a Time",
      text: "Select the day and time that works for you.",
    },
    {
      page: "book_coach",
      selector: '[data-tour="student-info"]',
      title: "Your Information",
      text: "Fill in your details so the coach knows who to expect.",
    },
    {
      page: "book_coach",
      selector: '[data-tour="payment-button"]',
      title: "Complete Booking",
      text: "Review and submit. For paid options, you'll check out securely with Flutterwave.",
    },
  ];

  const COACH_TOUR_STEPS = [
    {
      page: "coach_dashboard",
      selector: '[data-tour="coach-header"]',
      title: "Coach Dashboard",
      text: "This is where you manage your profile, availability, and bookings.",
    },
    {
      page: "coach_dashboard",
      selector: '[data-tour="coach-tabs"]',
      title: "Schedule & Profile",
      text: "Switch between your schedule and your public coach profile.",
    },
    {
      page: "coach_dashboard",
      selector: '[data-tour="coach-meeting-link"]',
      title: "Meeting Link",
      text: "Add your Zoom or Google Meet link so students can join sessions.",
    },
    {
      page: "coach_dashboard",
      selector: '[data-tour="coach-weekly-availability"]',
      title: "Weekly Availability",
      text: "Set the days and times you are usually free for classes.",
    },
    {
      page: "coach_dashboard",
      selector: '[data-tour="coach-block-dates"]',
      title: "Block Dates",
      text: "Mark dates you are unavailable so students cannot book them.",
    },
    {
      page: "coach_dashboard",
      selector: '[data-tour="coach-availability-preview"]',
      title: "Availability Preview",
      text: "See how your schedule looks over the next seven days.",
    },
    {
      page: "coach_dashboard",
      selector: '[data-tour="coach-pending-bookings"]',
      title: "Pending Bookings",
      text: "Review and confirm paid bookings, or reject requests you cannot take.",
    },
    {
      page: "coach_dashboard",
      selector: '[data-tour="coach-confirmed-bookings"]',
      title: "Confirmed Bookings",
      text: "View all upcoming sessions and student details.",
    },
  ];

  const TOURS = {
    home: { steps: HOME_TOUR_STEPS, seenKey: TOUR_SEEN_KEYS.home },
    student: { steps: STUDENT_TOUR_STEPS, seenKey: TOUR_SEEN_KEYS.student },
    coach: { steps: COACH_TOUR_STEPS, seenKey: TOUR_SEEN_KEYS.coach },
  };

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
  let currentTourTarget = null;
  let currentTourName = null;

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
      case "home":
        return "New here? Take a quick tour.";
      case "dashboard":
        return "Pick a task and we'll take you there.";
      case "coach_dashboard":
        return "Manage your coaching schedule.";
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
    const isCoach = body.dataset.isCoach === "true";

    // Tour restart action
    if (page === "home") {
      actions.push({
        label: "Take a tour",
        desc: "See what Moving Train offers in 5 steps.",
        handler: () => startTour("home", 0, false),
      });
    } else if (page === "dashboard" && isAuthenticated && !isCoach) {
      actions.push({
        label: "Take a tour",
        desc: "Walk through the dashboard and booking flow.",
        handler: () => startTour("student", 0, false),
      });
    } else if (page === "coach_dashboard" && isCoach) {
      actions.push({
        label: "Take a tour",
        desc: "Learn your way around the coach dashboard.",
        handler: () => startTour("coach", 0, false),
      });
    } else if (page === "tutors" || page === "book_coach") {
      actions.push({
        label: "Take a tour",
        desc: "Walk through the dashboard and booking flow.",
        handler: () => startTour("student", 0, true),
      });
    }

    if (page === "home") {
      actions.push({
        label: "Browse coaches",
        desc: "See our regular and elite coaches.",
        url: pageEl && pageEl.dataset.tutorsUrl ? pageEl.dataset.tutorsUrl : "/tutors/",
      });
      actions.push({
        label: "Sign up",
        desc: "Create a free account to book classes.",
        url: pageEl && pageEl.dataset.signupUrl ? pageEl.dataset.signupUrl : "/accounts/signup/",
      });
    }

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

    if (!isAuthenticated && page !== "home") {
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

  // ================= TOURS =================

  function currentTourSteps() {
    return currentTourName ? TOURS[currentTourName].steps : [];
  }

  function initTour() {
    const isAuthenticated = body.dataset.userAuthenticated === "true";
    const isCoach = body.dataset.isCoach === "true";

    // Sign-up handoff
    if (isAuthenticated && sessionStorage.getItem(PENDING_STUDENT_TOUR_KEY) === "true" && page === "dashboard" && !isCoach) {
      sessionStorage.removeItem(PENDING_STUDENT_TOUR_KEY);
      startTour("student", 0, false);
      return;
    }
    if (isAuthenticated && isCoach && sessionStorage.getItem(PENDING_COACH_TOUR_KEY) === "true" && page === "coach_dashboard") {
      sessionStorage.removeItem(PENDING_COACH_TOUR_KEY);
      startTour("coach", 0, false);
      return;
    }

    // Resume an active tour
    if (sessionStorage.getItem(TOUR_ACTIVE_KEY) === "true") {
      const savedName = sessionStorage.getItem(TOUR_NAME_KEY);
      const stepIndex = parseInt(sessionStorage.getItem(TOUR_STEP_KEY) || "0", 10);
      if (savedName && TOURS[savedName]) {
        currentTourName = savedName;
        setTimeout(() => runStep(stepIndex), 600);
        return;
      }
    }

    // First-time auto-start
    if (!isAuthenticated && page === "home" && !localStorage.getItem(TOUR_SEEN_KEYS.home)) {
      setTimeout(() => startTour("home", 0, false), 1500);
      return;
    }
    if (isAuthenticated && page === "dashboard" && !isCoach && !localStorage.getItem(TOUR_SEEN_KEYS.student)) {
      setTimeout(() => startTour("student", 0, false), 1500);
      return;
    }
    if (isAuthenticated && isCoach && page === "coach_dashboard" && !localStorage.getItem(TOUR_SEEN_KEYS.coach)) {
      setTimeout(() => startTour("coach", 0, false), 1500);
      return;
    }
  }

  function startTour(tourName, stepIndex, navigateToStart) {
    if (!TOURS[tourName]) return;
    endTour(false);
    currentTourName = tourName;
    sessionStorage.setItem(TOUR_ACTIVE_KEY, "true");
    sessionStorage.setItem(TOUR_NAME_KEY, tourName);
    sessionStorage.setItem(TOUR_STEP_KEY, String(stepIndex));

    if (navigateToStart) {
      const startPage = TOURS[tourName].steps[0].page;
      if (startPage !== page) {
        const url = getStepUrl(startPage);
        if (url) {
          window.location.href = url;
          return;
        }
      }
    }

    setOpen(false);
    setTimeout(() => runStep(stepIndex), 400);
  }

  function runStep(index) {
    const steps = currentTourSteps();
    if (index < 0 || index >= steps.length) {
      endTour(true);
      return;
    }
    sessionStorage.setItem(TOUR_STEP_KEY, String(index));
    const step = steps[index];
    if (step.page && step.page !== page) {
      const url = getStepUrl(step.page);
      if (url) {
        window.location.href = url;
        return;
      }
      // No direct URL for this step; skip it.
      runStep(index + 1);
      return;
    }
    showTourStep(step, index);
  }

  function getStepUrl(targetPage) {
    if (targetPage === "dashboard") {
      return body.dataset.dashboardUrl || "/accounts/dashboard/";
    }
    if (targetPage === "tutors") {
      return pageEl && pageEl.dataset.tourTutorsUrl
        ? pageEl.dataset.tourTutorsUrl
        : "/tutors/";
    }
    if (targetPage === "book_coach") {
      const firstCard = document.querySelector("[data-tour-coach-url]");
      return firstCard ? firstCard.dataset.tourCoachUrl : null;
    }
    return null;
  }

  function showTourStep(step, index) {
    clearTourUI();
    createTourBackdrop();
    const target = step.selector ? document.querySelector(step.selector) : null;
    currentTourTarget = target;
    if (target) {
      target.classList.add(...HIGHLIGHT_CLASSES);
      target.style.position = "relative";
      target.style.zIndex = "60";
      target.setAttribute("tabindex", "-1");
      target.scrollIntoView({ behavior: "smooth", block: "center" });
    }
    const tooltip = createTourTooltip(step, index);
    positionTourTooltip(tooltip, target, step.position);
  }

  function createTourBackdrop() {
    let backdrop = document.getElementById("tour-backdrop");
    if (!backdrop) {
      backdrop = document.createElement("div");
      backdrop.id = "tour-backdrop";
      backdrop.className =
        "fixed inset-0 bg-black/60 z-40 transition-opacity duration-200 opacity-0";
      backdrop.setAttribute("aria-hidden", "true");
      backdrop.addEventListener("click", () => endTour(false));
      document.body.appendChild(backdrop);
    }
    requestAnimationFrame(() => backdrop.classList.remove("opacity-0"));
  }

  function createTourTooltip(step, index) {
    let tooltip = document.getElementById("tour-tooltip");
    if (!tooltip) {
      tooltip = document.createElement("div");
      tooltip.id = "tour-tooltip";
      tooltip.className =
        "fixed z-[60] w-[calc(100vw-2rem)] md:w-80 bg-white rounded-2xl shadow-2xl border border-brand-100 p-5 transition-all duration-200 opacity-0 scale-95";
      tooltip.setAttribute("role", "dialog");
      tooltip.setAttribute("aria-live", "polite");
      document.body.appendChild(tooltip);
    }
    const steps = currentTourSteps();
    const isFirst = index === 0;
    const isLast = index === steps.length - 1;

    const actionButtons = (step.actions || [])
      .map(
        (action) => `
        <button type="button" data-tour-action="${action.key}" class="px-4 py-2 text-sm font-medium text-brand-700 bg-brand-50 rounded-lg hover:bg-brand-100 transition-colors">
          ${action.label}
        </button>
      `
      )
      .join("");

    tooltip.innerHTML = `
      <div class="flex items-start justify-between mb-3">
        <h4 class="font-bold text-brand-900">${step.title}</h4>
        <span class="text-xs text-brand-400 font-medium">${index + 1}/${steps.length}</span>
      </div>
      <p class="text-sm text-brand-700 mb-5 leading-relaxed">${step.text}</p>
      ${actionButtons ? `<div class="flex flex-wrap gap-2 mb-5">${actionButtons}</div>` : ""}
      <div class="flex items-center justify-between">
        <button type="button" id="tour-skip" class="text-sm text-brand-500 hover:text-brand-700 font-medium">Skip tour</button>
        <div class="flex items-center gap-2">
          ${!isFirst ? `<button type="button" id="tour-prev" class="px-3 py-2 text-sm font-medium text-brand-700 bg-brand-50 rounded-lg hover:bg-brand-100 transition-colors">Back</button>` : ""}
          <button type="button" id="tour-next" class="px-4 py-2 text-sm font-medium text-white bg-brand-600 rounded-lg hover:bg-brand-700 transition-colors">${isLast ? "Finish" : "Next"}</button>
        </div>
      </div>
    `;

    tooltip.querySelector("#tour-skip").addEventListener("click", () => endTour(false));
    const nextBtn = tooltip.querySelector("#tour-next");
    if (nextBtn) {
      nextBtn.addEventListener("click", () => {
        if (isLast) endTour(true);
        else runStep(index + 1);
      });
    }
    if (!isFirst) {
      tooltip.querySelector("#tour-prev").addEventListener("click", () => runStep(index - 1));
    }

    if (step.actions) {
      tooltip.querySelectorAll("[data-tour-action]").forEach((btn) => {
        btn.addEventListener("click", () => handleTourAction(step, btn.dataset.tourAction));
      });
    }

    requestAnimationFrame(() => tooltip.classList.remove("opacity-0", "scale-95"));
    return tooltip;
  }

  function handleTourAction(step, key) {
    if (currentTourName === "home") {
      localStorage.setItem(TOURS.home.seenKey, "true");
      endTour(false);
      if (key === "signup") {
        window.location.href = pageEl && pageEl.dataset.signupUrl ? pageEl.dataset.signupUrl : "/accounts/signup/";
      } else if (key === "tutors") {
        window.location.href = pageEl && pageEl.dataset.tutorsUrl ? pageEl.dataset.tutorsUrl : "/tutors/";
      }
    }
  }

  function positionTourTooltip(tooltip, target, preferred) {
    const margin = 12;
    const rect = target ? target.getBoundingClientRect() : null;
    const ttRect = tooltip.getBoundingClientRect();
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    let top, left;

    if (!rect) {
      top = (vh - ttRect.height) / 2;
      left = (vw - ttRect.width) / 2;
    } else {
      const placeBottom =
        preferred === "bottom" || (rect.top > vh / 2 && preferred !== "top");
      if (placeBottom) {
        top = rect.bottom + margin;
      } else {
        top = rect.top - ttRect.height - margin;
      }
      left = rect.left + rect.width / 2 - ttRect.width / 2;
    }

    left = Math.max(margin, Math.min(left, vw - ttRect.width - margin));
    top = Math.max(margin, Math.min(top, vh - ttRect.height - margin));
    tooltip.style.top = `${top}px`;
    tooltip.style.left = `${left}px`;
  }

  function clearTourUI() {
    if (currentTourTarget) {
      currentTourTarget.classList.remove(...HIGHLIGHT_CLASSES);
      currentTourTarget.style.position = "";
      currentTourTarget.style.zIndex = "";
      currentTourTarget.removeAttribute("tabindex");
      currentTourTarget = null;
    }
  }

  function endTour(completed) {
    clearTourUI();
    const backdrop = document.getElementById("tour-backdrop");
    if (backdrop) {
      backdrop.classList.add("opacity-0");
      setTimeout(() => backdrop.remove(), 200);
    }
    const tooltip = document.getElementById("tour-tooltip");
    if (tooltip) {
      tooltip.classList.add("opacity-0", "scale-95");
      setTimeout(() => tooltip.remove(), 200);
    }
    if (currentTourName) {
      if (completed) {
        localStorage.setItem(TOURS[currentTourName].seenKey, "true");
      }
      currentTourName = null;
    }
    sessionStorage.removeItem(TOUR_ACTIVE_KEY);
    sessionStorage.removeItem(TOUR_NAME_KEY);
    sessionStorage.removeItem(TOUR_STEP_KEY);
  }

  function handleTourKey(e) {
    if (sessionStorage.getItem(TOUR_ACTIVE_KEY) !== "true") return;
    const steps = currentTourSteps();
    if (e.key === "Escape") {
      endTour(false);
    } else if (e.key === "ArrowRight") {
      const stepIndex = parseInt(sessionStorage.getItem(TOUR_STEP_KEY) || "0", 10);
      if (stepIndex < steps.length - 1) runStep(stepIndex + 1);
      else endTour(true);
    } else if (e.key === "ArrowLeft") {
      const stepIndex = parseInt(sessionStorage.getItem(TOUR_STEP_KEY) || "0", 10);
      if (stepIndex > 0) runStep(stepIndex - 1);
    }
  }
  document.addEventListener("keydown", handleTourKey);

  buildUI();
  initTour();
})();
