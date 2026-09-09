# Chess Proficiency System — Design Reference

> **Purpose:** this file records the conclusions of our design deliberations for the
> chess-proficiency features. Use it as the reference when implementing — each phase
> below is written so a fresh work session can pick it up without re-deriving the design.
> Implementation is done pair-style: the developer writes the code, guided by this doc.
>
> Last updated: 2026-08-26

---

## 1. Goals

- Track each student's progress over the quizzes they take.
- Be able to say **at any point in time what level of chess a student knows** — per motif,
  not just one global "beginner/intermediate/expert".
- Show a **bar chart on the student dashboard**: one bar per chess motif (mate in 1, pins,
  forks, …), height = proficiency level achieved.
- Support **difficulty tiers per motif** — e.g. "Mate in 1 / Easy", "Mate in 1 / Hard".
- Award **badges** for completing feats (e.g. passing "Mate in 1 — Easy"), displayed on
  the student's dashboard.
- **Eventually**: social features — students showcase badges, a feeds page, leaderboards.
  Design sketched in §7, but **not built yet**.

---

## 2. Current state of the codebase (verified facts)

Grounding for everything below — check these line numbers still hold before relying on them.

- `quiz/models.py` — 4 models: `Questionnaire`, `Qtaker`, `Question`, `Options`.
  - `Question` already has **uncommitted, unmigrated** fields at `quiz/models.py:64-77`:
    `question_motif` (choices PINS / "MATE EN 1") and `question_grade` (EASY/MEDIUM/HARD).
    ⚠️ The choice tuples are **inverted** — `("PINS", "pins")` stores `"PINS"` in the DB with
    label "pins" — and the defaults (`default="mate en 1"`) match no stored value.
    **Fixing this is the very first task (Phase 1).**
  - `Qtaker` (one quiz session) stores `current_score`, `scored_question_ids`,
    `current_question_set` (JSON list of question IDs), `skill`, `test_result`.
    **No per-question results are stored** — motif stats need them (see §3.4).
- Quiz flow (`quiz/views.py`):
  - `_build_session` (line 32): picks ≤ `QUESTIONS_PER_SESSION` (5) random approved questions
    from the `Questionnaire` whose **title equals the skill name** ("beginner" etc.).
  - `quiz_question_view` (line 126): GET renders `question.html`; POST grades
    (radio → `Options` pk; text → case-insensitive match).
  - `quiz_answer_view` (line 211): applies +1 score once per question via `scored_question_ids`.
  - `quiz_result_view` (line 271): computes %, pass if > `PASS_PERCENTAGE` (60, line 12);
    on pass pre-builds the next skill level's question set.
- Student dashboard: `accounts/views.py:153` `dashboard_view` →
  `templates/accounts/dashboard_student.html`. It already queries quiz history
  (`accounts/views.py:206`) — this is where the chart and badges cards go.
- Page-specific JS goes in `{% block extra_js %}` (`templates/base.html:301`); CDN libs are
  an accepted pattern (html2canvas in `templates/quiz/result.html:58`).
- **No chess libraries exist anywhere**: no `python-chess` in `requirements.txt`, no
  chessboard/chess.js in `package.json` or `static/js/`. Today a chess position can only
  appear as a static image inside the CKEditor5 question HTML.
- `accounts.User` (`accounts/models.py`) has `is_student` / `is_coach`; badges hang off it.
- Coaches submit questions via `quiz/views.py:341` `submit_question_view`
  (`CoachQuestionForm` in `quiz/forms.py`, template `templates/quiz/submit_question.html`);
  staff approve via `is_approved` in `quiz/admin.py`.

---

## 3. Agreed design decisions

### 3.1 Motif taxonomy

Extensible choice list (stored value, label):

```python
QUESTION_MOTIFS = [
    ("mate_in_1", "Mate in 1"),
    ("mate_in_2", "Mate in 2"),
    ("pins", "Pins"),
    ("forks", "Forks"),
    ("skewers", "Skewers"),
    ("discovered_attacks", "Discovered Attacks"),
    ("endgames", "Endgames"),
    ("openings", "Openings"),
    ("tactics", "Tactics"),
]
```

Stored values are `lowercase_snake`; labels human-readable. This **fixes the inverted
tuples** in the current uncommitted code. Add motifs by extending the list — new motif =
new bar on the chart.

### 3.2 Difficulty tiers

```python
QUESTION_GRADES = [
    ("easy", "Easy"),
    ("medium", "Medium"),
    ("hard", "Hard"),
]
```

Difficulty is **per motif**, not global: a student can be "hard" at mate in 1 and "easy"
at endgames. This replaces (per motif) the existing global beginner/intermediate/expert
progression for the new quiz type; the old skill-based flow stays for legacy quizzes.

### 3.3 Quiz-level motif tagging

- `Questionnaire` gains `motif` + `difficulty` (same choice lists, `blank=True` for the 3
  existing legacy questionnaires).
- A quiz session draws questions from **one** questionnaire ⇒ every session is exactly one
  (motif, difficulty) pair — precisely the granularity the bar chart needs.
- ~~Per-question motif/difficulty fields~~ **Dropped (2026-08-27, developer decision):**
  redundant with the questionnaire tags — two copies of one fact can drift. Single source
  of truth: `Questionnaire.motif` / `.difficulty`. If mixed-motif questionnaires are ever
  wanted, re-add per-question fields then. The choice lists live on `Questionnaire`
  (`Questionnaire.QUESTION_MOTIFS` / `QUESTION_GRADES`).
- ✅ **Implemented in `quiz/migrations/0008`** (question-level fields removed again in 0009).

### 3.4 Per-question results

New model `QuestionResult` (in `quiz/models.py`, ✅ implemented 2026-08-27):

| field | type | notes |
|---|---|---|
| `qtaker` | FK → `Qtaker`, `on_delete=PROTECT` | which session; sessions can't be deleted while results exist |
| `question` | FK → `Question`, `on_delete=PROTECT` | motif/grade reachable via question → questionnaire; coaches un-approve instead of deleting |
| `correct` | bool | graded outcome frozen at answer time — never re-derive (grading differs per question type; questions get edited) |
| `answer_given` | CharField(2000), blank, default="" | the submitted answer text/move |
| `created_at` | auto_now_add | |

Written in `quiz_answer_view` where scoring already happens (once per question via an
`exists()` guard; first attempt stands). This makes motif stats
**survive score resets** and enables per-question analytics later.

**Progression (resolved 2026-08-27):** motif quizzes progress easy→medium→hard within
the same motif (`_next_difficulty` + `_prepare_next_session` in `quiz/views.py`);
`qtaker.skill` is untouched by motif quizzes, and the legacy skill-title progression only
runs for legacy sessions. The "View course" button is hidden for motif results.

### 3.5 Proficiency computation (the chart data)

Computed by aggregation — **no denormalized table initially** (keep it simple; cache later
if the dashboard gets slow).

New helper `quiz/proficiency.py`:

```python
def get_proficiency(user) -> list[dict]:
    # per motif: {"motif": "pins", "label": "Pins",
    #             "level": "easy"|"medium"|"hard"|None,   # highest difficulty PASSED
    #             "attempts": int, "best_score": float}
```

- Data source: `Qtaker` rows for the user (filter `user=user`; fall back to
  `email=user.email` as `dashboard_view` already does at `accounts/views.py:206`) joined to
  their questionnaire's motif/difficulty, plus `QuestionResult` for detail.
- **Level rule:** passing (≥ `PASS_PERCENTAGE` = 60) a motif quiz at a difficulty ⇒ that
  level is "achieved". Chart shows the highest achieved difficulty per motif;
  tooltip shows attempts + best score.
- Chart renders as a new card in `templates/accounts/dashboard_student.html` using
  **Chart.js from CDN** in `{% block extra_js %}` (same pattern as html2canvas in
  `result.html`).

### 3.6 Badges

Two models (in `quiz/models.py`):

- `Badge` — the catalogue: `name`, `slug` (unique), `description`, `icon` (emoji or image),
  `motif` (blankable), `difficulty` (blankable), `criteria` (how it's earned — start with
  "pass motif at difficulty"; slugs drive evaluation logic).
- `UserBadge` — an award: `user` FK, `badge` FK, `qtaker` FK (evidence), `awarded_at`;
  `unique_together(user, badge)` so a badge can't be earned twice.

Award logic in a new `quiz/badges.py`: `evaluate_badges(qtaker)` called from
`quiz_result_view` **after a pass**. Starter catalogue:

- "Mate in 1 — Easy" … one badge per (motif, difficulty) pass.
- "Tactician" — all motifs passed at easy.
- (Extend later: streaks, perfect scores, speed.)

Both models registered in `quiz/admin.py`; catalogue seedable via a fixture
(see `quiz/fixtures/` for the existing pattern). Dashboard gets a "Badges" card: earned
badges in colour, unearned greyed out.

### 3.7 Interactive chessboard & FEN

- **Frontend:** [Chessground](https://github.com/lichess-org/chessground) (lichess's board
  library — display *and* move input, ~30 KB, no deps) + `chess.js` (move legality).
  ✅ **Implemented via jsdelivr CDN** (`chessground@9`, ESM + 3 CSS assets) rather than
  vendoring — consistent with the project's html2canvas/Chart.js CDN precedent. chess.js
  not needed yet (display-only phase); server-side legality is covered by python-chess.
  Shared partials: `templates/quiz/_chessboard.html` (board div) and
  `templates/quiz/_chessboard_init.html` (module script); board orientation faces the
  side to move. ✅ **Theme overrides (2026-09-07):** `static/css/chessboard.css` —
  deeper walnut square colors (light `#e6c88f`, dark `#a06a35`) replacing the washed-out
  default brown theme, and corrected coordinates (chessground's reference `brown.css`
  parity rules make half the rank/file labels invisible on a standalone board; the
  override pins the strips to the board edges and fixes the colors). Loaded via
  `templates/quiz/_chessboard_assets.html` after the three CDN stylesheets.
- **Backend:** `pip install python-chess` → `requirements.txt`. Used for:
  - validating FEN in `CoachQuestionForm` (`chess.Board(fen)` raises on invalid input);
  - grading interactive answers: `Question.solution_uci` (e.g. `"g1f3"`) vs the move played
    on the board.
- `Question` gains `fen = CharField(max_length=300, blank=True, default="")` and
  `solution_uci = CharField(max_length=10, blank=True, default="")` — ✅ implemented 2026-08-27.
- Start **display-only** (board shows the position; answer stays text/radio → existing
  grading untouched). Interactive "play the move on the board" grading is a follow-up once
  display works.

### 3.8 Lichess integration

- **Content seeding (build this):** the public
  [Lichess puzzle database](https://database.lichess.org/#puzzles) — a free CSV of ~4M
  puzzles with FEN, solution moves, themes (`mateIn1`, `pin`, `fork`, …) and ratings.
  **No API key needed.** A management command
  `quiz/management/commands/import_lichess_puzzles.py` filters by theme (→ our motifs) and
  rating band (→ easy/medium/hard) and creates approved `Question` rows with `fen` +
  `solution_uci`. This instantly fills the motif quizzes with real content.
  Question text is simply `"{side} to play — {motif} ({difficulty})."` — no lichess
  branding/tag (changed 2026-09-07); puzzle ID is kept only in the import log.
- **Deferred:** Lichess OAuth account-linking, game import, live puzzle API. A much bigger
  commitment (token storage on `accounts.User`, background jobs) — revisit after badges ship.

---

## 4. Implementation phases (pair-style guide)

Each phase: what to build → files to touch → questions to think through → how to verify.
Do them in order; each phase leaves the site working.

### Phase 1 — Data model foundation

- **Build:** fix `QUESTION_MOTIFS`/`QUESTION_GRADES` tuples and defaults; expand motif list;
  add `motif`+`difficulty` to `Questionnaire`; add `fen`+`solution_uci` to `Question`;
  add `QuestionResult` model; make + run migration.
- **Files:** `quiz/models.py`, new migration.
- **Think about:** what happens to rows created before the fix? (DB is sqlite dev + fixture
  data — check `quiz/fixtures/initial_quiz.json` still loads.)
- **Verify:** `python manage.py makemigrations quiz && python manage.py migrate`;
  `python manage.py test quiz` stays green; admin shows the new fields.

### Phase 2 — Motif-aware quiz sessions

- **Build:** `_build_session` accepts optional motif/difficulty and filters the question
  pool (fall back to current skill-title behaviour when absent — legacy flow and tests must
  keep working); new entry URL e.g. `/quiz/motif/<motif>/<difficulty>/`; record
  `QuestionResult` rows in `quiz_answer_view`.
- **Files:** `quiz/views.py`, `quiz/urls.py`, `quiz/tests.py`.
- **Think about:** what if a questionnaire has < 5 approved questions? What stops a student
  retaking the same quiz to farm badges? (Badges are unique-per-user, but scores still
  record — fine.)
- **Verify:** old `QuizTemplateTests` pass; new tests: session only contains questions of the
  requested motif; `QuestionResult` rows written per answer.

### Phase 3 — Proficiency chart

- **Build:** `quiz/proficiency.py::get_proficiency(user)`; add `proficiency` to
  `dashboard_view` context; new "Chess Proficiency" card in
  `templates/accounts/dashboard_student.html` with Chart.js bar chart.
- **Files:** `quiz/proficiency.py` (new), `accounts/views.py`,
  `templates/accounts/dashboard_student.html`.
- **Think about:** what does the chart show for a motif never attempted? (Empty/zero bar vs
  hidden — decide and note it.) Colour per level or per motif?
- **Verify:** unit-test `get_proficiency` with fabricated Qtaker/QuestionResult data;
  manual: take a motif quiz as a logged-in student, see the bar appear.

### Phase 4 — Badges

- **Build:** `Badge`/`UserBadge` models + migration; `quiz/badges.py::evaluate_badges`;
  call it from `quiz_result_view` on pass; admin registration; badge fixture; "Badges" card
  on the dashboard.
- **Files:** `quiz/models.py`, `quiz/badges.py` (new), `quiz/views.py`, `quiz/admin.py`,
  `quiz/fixtures/badges.json` (new), `accounts/views.py`,
  `templates/accounts/dashboard_student.html`.
- **Think about:** badge awarding must be idempotent (unique_together + `get_or_create`);
  should coaches see student badges? (Later — coach dashboard.)
- **Verify:** tests: passing "mate_in_1/easy" grants exactly one badge, retaking grants none;
  dashboard renders earned vs locked badges.

### Phase 5 — Chessboard UI & FEN authoring

- **Build:** vendor Chessground + chess.js into `static/js/`; `pip install python-chess`;
  display-only board in `question.html`/`answer.html` when `question.fen` is set; FEN input
  + live preview in `CoachQuestionForm` / `submit_question.html` (uses `{{ form.media }}`
  pattern) and `QuestionAdmin`.
- **Files:** `static/js/` (new vendored files), `requirements.txt`,
  `templates/quiz/question.html`, `templates/quiz/answer.html`, `quiz/forms.py`,
  `templates/quiz/submit_question.html`, `quiz/admin.py`.
- **Think about:** CSP/script ordering with `extra_js`; board orientation (side to move
  from the FEN); mobile sizing.
- **Verify:** create a question with a FEN as a coach, take the quiz, board renders the
  position; invalid FEN rejected by the form with a clear error.

### Phase 6 — Lichess puzzle seeding

- **Build:** `import_lichess_puzzles` management command: stream the puzzle CSV, filter by
  theme/rating, map themes→motifs and rating bands→grades, create approved questions
  (idempotent — skip existing lichess puzzle IDs).
- **Files:** `quiz/management/commands/import_lichess_puzzles.py` (new).
- **Think about:** how many puzzles per (motif, grade)? Store the lichess puzzle ID
  somewhere to dedupe (e.g. in the question HTML comment or a dedicated field — decide).
- **Verify:** run with a small `--limit`; questions appear in admin with correct
  motif/grade/fen; re-running doesn't duplicate.

### Phase 7 — Interactive move grading (✅ single-move implemented 2026-08-27)

- ✅ Students play the move on the board (Chessground + chess.js legal-move dests,
  `templates/quiz/_chessboard_interactive.html`); the move is written as UCI into the
  hidden `answer` field, so the POST contract of `quiz_question_view` is unchanged.
- ✅ Grading via `_answer_is_correct` (`quiz/views.py`): exact UCI match against
  `solution_uci`, falling back to option-text matching (SAN for imported puzzles).
- Caveats: single-move puzzles only; promotion defaults to queen; board locks after a
  move until "Reset board" is used.
- **Still deferred:** multi-move puzzles ("mate in 2") need server-side reply state on
  `Qtaker` (JSONField, same pattern as `current_question_set`) — design when needed.

---

## 5. What "what level is this student?" means

Per motif, one of: **not attempted → easy → medium → hard**, where a level means
"passed (≥60%) a quiz of that motif at that difficulty". The dashboard chart is exactly
this table rendered as bars. An overall summary (e.g. "Intermediate tactician") can be
derived later as a simple roll-up — deliberately not specced yet.

---

## 6. Social & future features

**✅ Built 2026-09-07** (privacy decisions resolved first — students may be minors):

- **Activity feed** (`/quiz/feed/`) — `quiz.Activity` model (user/kind/badge/text/created_at,
  text frozen at write time). Events: badge awards and first-time passes of a
  (motif, difficulty) pair ("level-ups"), written in `quiz_result_view` after grading.
  Visible to **logged-in users only**; students identified by **username only**.
- **Per-motif leaderboard** (`/quiz/leaderboard/<motif>/`) — ranked by level (highest
  difficulty passed) → best score → fewest attempts, aggregated over `QuestionResult`;
  anonymous attempts excluded; top 20; username only; logged-in only.
- **Coach session notes** (`/scheduling/coach/notes/`) — `scheduling.SessionNote`
  (coach FK, student FK, session_date, content, timestamps). Free-standing (not tied to a
  booking) so a student's learning history survives coach changes; append-and-keep, never
  edited/deleted; attributed by coach name. **Coaches only** — students never see notes.
  Student picker = users linked via session notes or any booking channel
  (`Booking.student_email`, `FlexibleBooking.user`, `SpecialBooking.student`); searchable.
  The student's proficiency chart (`quiz/_proficiency_chart.html` partial, shared with the
  student dashboard) sits next to the note form on the detail page.

Remaining from the 2026-08-27 list:

1. **Coach visibility into student progress** — partially covered by session notes +
   proficiency chart; a dedicated per-student badge/progress view on the coach dashboard
   is still open if wanted.
2. **Badge showcase** (public profile of earned badges) — still pending; the privacy
   decisions above (logged-in only, username-only) are the template for it.
3. **Multi-move puzzles ("mate in 2")** — the deferred half of Phase 7. Needs server-side
   reply moves and puzzle state on `Qtaker` (JSONField, same pattern as
   `current_question_set`). Only when mate-in-2 quizzes go live.

---

## 7. Open questions (owner: the developer)

1. Exact badge catalogue — names, icons, and which feats earn them beyond the starter set.
2. Backfill: legacy questionnaires (beginner/intermediate/expert) are **untagged by rule**:
   `motif=""`/`difficulty=""` means "legacy, excluded from chart and badges".
   `Questionnaire.motif`/`difficulty` have `default=""` (changed 2026-08-27 after tests
   exposed that a non-empty default made every new questionnaire claim to be
   mate_in_1/easy). ⚠️ Existing dev-DB rows were stamped `mate_in_1`/`easy` by migration
   0008 — ✅ blanked 2026-09-07 (the three legacy questionnaires in the dev DB now have
   `motif=''`/`difficulty=''`, so they're excluded from the chart and badges as intended).
3. Anonymous quiz-takers: `Qtaker.user` is nullable today and anonymous play is supported.
   Proficiency charts and badges need a logged-in user — restrict motif quizzes to
   logged-in students, or keep an anonymous mode that just doesn't record stats?
4. Chart presentation for unattempted motifs (zero-height bar vs hidden) and colour scheme.
5. Multi-move puzzle UX (Phase 7) — how the server replies to the student's move.
