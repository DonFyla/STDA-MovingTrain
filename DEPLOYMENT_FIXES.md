# Deployment Fixes — STDA-MovingTrain Backend

> Goal: fix bugs and harden the project so it can be deployed safely to production.

## Legend

- `[ ]` = not started
- `[-]` = in progress
- `[x]` = done

---

## 🔴 Critical — Must Fix Before Launch

These affect money, data integrity, or security.

### [x] C1. Duplicate PointTransactions on every Paystack purchase
**What:** When a user buys points, `buy_points_view` creates a pending `PointTransaction`. The callback and webhook then call `add_points()`, which creates *another* completed transaction, and the pending one is also marked completed.  
**Files:** `payments/views.py`, `payments/webhook_views.py`, `payments/points_service.py`  
**Fix:** Added `complete_pending_transaction()` which updates the existing pending transaction in place and credits the user's balance without creating a second row.

### [x] C2. Race condition / double-spend in points bookings
**What:** `FlexibleBooking` rows were created before `use_points()` was called, with no atomic block or row lock. Concurrent requests could double-spend points; if deduction failed, orphan confirmed bookings remained.  
**File:** `scheduling/views.py`  
**Fix:** Wrapped slot creation + point deduction in `transaction.atomic()` and locked `UserPoints` with `select_for_update()`.

### [x] C3. Insecure defaults for SECRET_KEY and DEBUG
**What:** `SECRET_KEY` had a hardcoded fallback in `app/settings.py`; `DEBUG` defaulted to `True`; `docker-compose.yml` hardcoded a dev secret.  
**Files:** `app/settings.py`, `docker-compose.yml`, `app/test_settings.py`  
**Fix:** `SECRET_KEY` is now required from env (raises `UndefinedValueError` if missing); `DEBUG` defaults to `False`; dev compose uses env interpolation; test settings inject a test-only key before importing base settings.

### [x] C4. Paystack redirect callbacks do not verify paid amount
**What:** Recurring and special-booking callbacks trusted Paystack status only. They didn't compare the verified kobo amount to `booking.monthly_amount * 100` / `booking.total_amount * 100`.  
**Files:** `payments/views.py`  
**Fix:** Callbacks now compare `result["amount"]` with the expected kobo amount and reject mismatches.

---

## 🟠 High — Fix Before Launch if Possible

### [x] H1. Quiz score can be inflated by refreshing the answer page
**What:** `quiz_answer_view` incremented `current_score` every time it was rendered.  
**File:** `quiz/views.py`, `quiz/models.py`  
**Fix:** Added `Qtaker.scored_question_ids` JSONField and only increment score the first time a question is answered correctly.

### [x] H2. Quiz is fully open (no auth/ownership)
**What:** Anyone with a `qtaker_id` could view/answer/see results for any attempt.  
**Files:** `quiz/views.py`, `quiz/models.py`  
**Fix:** Added `Qtaker.user` FK; registration ties attempts to logged-in users; anonymous attempts are tied to the creating session; question/answer/result views enforce ownership.

### [x] H3. Booking confirmation pages lack ownership checks
**What:** Any logged-in user could view any booking confirmation by UUID.  
**Files:** `scheduling/views.py`  
**Fix:** Added ownership checks for recurring, flexible, and special booking confirmations (student/coach/superuser).

### [x] H4. Booking forms don't validate against availability or existing bookings
**What:** Server trusted client-side slot selection; double-booking was possible.  
**Files:** `scheduling/forms.py`, `scheduling/views.py`, `scheduling/availability.py`  
**Fix:** Added `is_slot_available()` helper; `PointsBookingForm` and `SpecialBookingForm` now validate every selected slot against coach availability, blocked dates, and existing bookings.

### [x] H5. Race conditions in point credit/debit
**What:** `add_points`, `use_points`, `refund_points` didn't lock `UserPoints`.  
**File:** `payments/points_service.py`  
**Fix:** Use `select_for_update()` inside each `transaction.atomic()` block.

### [x] H6. Award/bonus points recorded as "purchase"
**What:** `add_points()` hardcoded `type="purchase"`.  
**Files:** `payments/points_service.py`, `payments/management/commands/award_points.py`, `payments/admin_views.py`  
**Fix:** Added `transaction_type` parameter to `add_points()`; awards and bonuses are now recorded as `"bonus"`.

### [x] H7. Invalid `"rejected"` status on PointTransaction
**What:** `PointTransaction.STATUS_CHOICES` lacked `"rejected"`, but admin code set it.  
**Files:** `payments/models.py`  
**Fix:** Added `"rejected"` to `STATUS_CHOICES` and created migration `0002_alter_pointtransaction_status`.

### [x] H8. Unsafe `int()` parsing in admin portal
**What:** Manual POST parsing raised `ValueError` on bad input.  
**Files:** `admin_portal/views.py`  
**Fix:** Added `_parse_int()` helper and replaced unsafe `int()` calls in `coach_edit_view` and `schedule_view`.

---

## 🟡 Medium — Fix Soon After Launch

### [x] M1. Secret fragments logged
**What:** `PAYSTACK_SECRET_KEY` prefix was logged.  
**Files:** `payments/views.py`, `payments/management/commands/check_paystack.py`  
**Fix:** Logs now only indicate whether the key is configured; no secret substrings are printed.

### [x] M2. Webhook returns 500 when Paystack key missing
**What:** Returned HTTP 500 when key was missing; webhook tests failed without a dummy key.  
**Files:** `payments/webhook_views.py`, `app/test_settings.py`  
**Fix:** Returns 503 when not configured; test settings provide a dummy key so tests pass out of the box.

### [ ] M3. No rate limiting on auth / admin / payment endpoints
**What:** Login, signup, admin, and payment endpoints can be hammered.  
**Files:** `accounts/views.py`, `payments/views.py`, `admin_portal/views.py`  
**Fix:** Add Django Ratelimit or nginx-level rate limiting. **Recommended before public launch.**

### [x] M4. No `.dockerignore`
**What:** `COPY . .` could pull in `.env`, `.git`, `node_modules`, `db.sqlite3`, `staticfiles`, `media`.  
**File:** `.dockerignore`  
**Fix:** Created `.dockerignore` excluding secrets, build artifacts, and local environment files.

### [-] M5. nginx production config has no HTTPS
**What:** Port 443 is exposed but no SSL server block exists.  
**Files:** `docker/nginx.conf`, `docker-compose.prod.yml`  
**Fix:** Add HTTPS server block (with certificates from Certbot or another provider) or terminate SSL upstream (e.g., Cloudflare, AWS ALB). **Required for production traffic.**

### [x] M6. Debug static files served from empty `STATIC_ROOT`
**What:** In `DEBUG`, static URLs pointed at `STATIC_ROOT`, which is empty until `collectstatic`.  
**File:** `app/urls.py`  
**Fix:** Debug static URLs now serve from `STATICFILES_DIRS[0]`.

### [x] M7. No `LOGIN_URL` / redirect settings
**What:** Relied on default string URL.  
**File:** `app/settings.py`  
**Fix:** Added `LOGIN_URL = reverse_lazy("accounts:login")` and `LOGIN_REDIRECT_URL`.

### [ ] M8. CKEditor 4 security warning silenced
**What:** `SILENCED_SYSTEM_CHECKS = ["ckeditor.W001"]` hides a known issue.  
**File:** `app/settings.py`  
**Fix:** Migrate to `django-ckeditor-5` or plain textarea. **Recommended for long-term maintenance.**

### [ ] M9. N+1 queries in dashboards
**What:** Loops access related objects without `select_related`/`prefetch_related`.  
**Files:** `accounts/views.py`, `admin_portal/views.py`, `scheduling/views.py`  
**Fix:** Optimize querysets. **Performance improvement, not a blocker.**

---

## 🟢 Low — Polish / Cleanup

### [x] L1. Duplicate `div` template filter
**What:** `payments/templatetags/payments_extras.py` and `scheduling/templatetags/scheduling_extras.py` both defined `div`.  
**Fix:** Removed `payments_extras.py`; updated `templates/payments/buy_points.html` to load `scheduling_extras`.

### [ ] L2. `Options` model name is plural
**File:** `quiz/models.py:72`  
**Fix:** Rename to `Option` and update references. **Low priority.**

### [x] L3. Duplicate `CKEDITOR_UPLOAD_PATH` assignment
**File:** `app/settings.py`  
**Fix:** Removed duplicate assignment.

### [ ] L4. Hardcoded business contact / bank details
**Files:** `payments/views.py`, templates (`base.html`, `web/home.html`, etc.)  
**Fix:** Move to settings or a configurable model. **Low priority.**

### [ ] L5. `unique_together` on `CoachBlockedDate` allows duplicate full-day blocks
**File:** `scheduling/models.py:341`  
**Fix:** Use `UniqueConstraint` and handle `NULL` full-day blocks correctly. **Low priority.**

### [ ] L6. No database-level constraints on points balance or session counts
**Files:** `payments/models.py:13-15`, `scheduling/models.py:260-261`  
**Fix:** Add `CheckConstraint`s. **Low priority.**

---

## Deployment Readiness Checklist

- [x] All critical items fixed
- [x] All high items fixed
- [ ] `.env` created from `.env.example` with strong production values
- [x] `.dockerignore` added
- [ ] `docker-compose.prod.yml` tested on the target VPS
- [ ] `python manage.py check --deploy` passes with no warnings after setting SSL/HSTS flags
- [x] Full test suite passes: `python manage.py test --settings=app.test_settings`
- [ ] Static files build and collect correctly (`npm run build:css`, `collectstatic`)
- [ ] Migrations run cleanly on production DB
- [ ] HTTPS/cookie security flags configured
- [ ] Paystack webhook endpoint reachable and verified
- [ ] Backups configured

---

## Verification Commands

```bash
# Run the test suite
python manage.py test --settings=app.test_settings

# Check for missing migrations
python manage.py makemigrations --check --dry-run --settings=app.test_settings

# Deployment check (set env vars first)
SECRET_KEY=<strong-key> DEBUG=False ALLOWED_HOSTS=yourdomain.com \
  python manage.py check --deploy --settings=app.test_settings
```

## Remaining Work Before Going Fully Live

1. **SSL/TLS**: Configure nginx with real certificates or use an upstream SSL terminator.
2. **Production env**: Create `.env` with strong secrets, production hosts, and email/Paystack credentials.
3. **Rate limiting**: Add Django Ratelimit or nginx rate limiting.
4. **Static build**: Run `npm run build:css` and `python manage.py collectstatic` before building the Docker image.
5. **Paystack webhook**: Set the webhook URL in Paystack dashboard and verify signature handling.
6. **Backups**: Configure PostgreSQL backups.
7. **CKEditor**: Plan migration to a maintained editor.

**Current status: code-level critical and high bugs are fixed; remaining items are infrastructure/configuration.**
