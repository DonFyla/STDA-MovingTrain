# Google Analytics, Google Ads, Campaign Launch, and SEO Guide

## Purpose

This guide covers the complete setup for Moving Train Chess Academy:

1. Measure visitor behavior with Google Analytics 4 (GA4).
2. Measure successful booking purchases with Google Ads conversion tracking.
3. Verify the tracking on the production website.
4. Launch paid campaigns that attract prospective students and parents.
5. Improve unpaid (organic) search visibility with Google Search Console and SEO.

> **Important:** Google Ads can place paid advertisements in search results, but paying for ads does **not** directly improve the website's organic rankings. Paid acquisition and organic SEO are separate workstreams.

---

## 1. Understand the tools

| Tool | Purpose |
| --- | --- |
| Google Analytics 4 | Shows visitors, page views, traffic sources, engagement, and user behavior. |
| Google Ads | Runs paid campaigns and measures advertising costs, clicks, and purchases. |
| Google Tag Manager | Optional tool for deploying and managing tags. It is not an analytics reporting tool. |
| Google Tag Assistant | Helps verify that Google tags are present and firing. |
| Google Search Console | Shows organic search queries, impressions, clicks, indexing, and technical search issues. |

The recommended initial setup uses GA4 directly, without adding Google Tag Manager. This keeps the implementation simple.

---

## 2. Current website integration

The project already contains the required integration points:

- `app/settings.py` reads:
  - `GOOGLE_ANALYTICS_ID`
  - `GOOGLE_ADS_CONVERSION_ID`
  - `GOOGLE_ADS_CONVERSION_LABEL`
  - `GOOGLE_TAG_MANAGER_ID` (optional)
- `web/context_processors.py` exposes these values to templates.
- `templates/base.html` loads GA4 when `GOOGLE_ANALYTICS_ID` is configured and Google Tag Manager is not being used.
- `templates/base.html` loads the Google Ads library when `GOOGLE_ADS_CONVERSION_ID` is configured.
- Recurring and special booking confirmation pages send purchase events only when `payment_status` is `paid` and the logged-in viewer is the student.
- Successful points purchases send the same events when the student reaches the dashboard after payment. The verified amount and completed transaction ID are carried through the server-side session.
- The Google Ads `conversion` event requires both Ads conversion settings. The separate GA4 `purchase` event requires `GOOGLE_ANALYTICS_ID` and includes one ecommerce item.
- Both events contain the amount, `NGN`, and a stable transaction reference. Pending payments and coach/staff page views do not fire them.
- An `analytics_tracked_at` timestamp on the booking or point transaction ensures that each payment is emitted at most once, even if the confirmation page is refreshed or opened again later.

---

## 3. Prepare the accounts and requirements

Before starting, make sure you have:

- A Google account that should own the academy's analytics and advertising assets.
- Access to [Google Analytics](https://analytics.google.com/).
- Access to [Google Ads](https://ads.google.com/).
- Access to [Google Search Console](https://search.google.com/search-console/).
- Permission to edit the production `.env` on the VPS.
- A payment method for Google Ads billing when you are ready to launch campaigns.
- A privacy policy that accurately describes analytics/advertising cookies and data use.
- A consent mechanism where required by the visitor's location and applicable law.

Use the same Google account for GA4, Google Ads, and Search Console where practical. This makes linking and administration easier.

---

## 4. Create and configure GA4

### 4.1 Create the GA4 property

1. Open Google Analytics.
2. Go to **Admin**.
3. Create an account for the academy, or select the existing academy account.
4. Create a **GA4 property** for `themovingtrain.org`.
5. Select the appropriate reporting time zone and currency. Use Nigerian Naira if that matches how the business reports revenue.
6. Complete the business information questions.

### 4.2 Create a web data stream

1. In the property, open **Data streams**.
2. Choose **Web**.
3. Enter:
   - Website URL: `https://themovingtrain.org`
   - Stream name: `Moving Train Website`
4. Create the stream.
5. Copy the **Measurement ID**. It looks like `G-XXXXXXXXXX`.

Keep enhanced measurement enabled for basic page-view and engagement tracking unless there is a specific reason to change it.

### 4.3 Decide whether to use Google Tag Manager

For the simplest setup:

- Configure `GOOGLE_ANALYTICS_ID` directly.
- Leave `GOOGLE_TAG_MANAGER_ID` unset.

If `GOOGLE_TAG_MANAGER_ID` is already configured in production, the base template suppresses its direct GA4 loader. In that case, create and publish a GA4 Google tag inside Tag Manager instead. Do not load the same GA4 property through both GTM and the direct template integration, or page views may be duplicated.

---

## 5. Create the Google Ads purchase conversion

1. Open Google Ads.
2. Open the conversion/goals area and choose to create a **new conversion action**.
3. Select **Website** as the conversion source.
4. Choose manual conversion setup when asked how to create the action.
5. Select **Purchase** as the goal/category.
6. Use a clear name such as `Successful Booking Purchase`.
7. Configure the important settings:
   - **Value:** use different values for each conversion, because bookings have different prices.
   - **Count:** count every purchase, not just one per visitor.
   - **Currency/reporting:** ensure the account and campaign reporting are appropriate for the business.
   - **Conversion windows and attribution:** start with Google's recommended defaults unless there is a documented reason to change them.
8. Save the conversion action.
9. When Google presents the tag details, copy:
   - The **Conversion ID**, which looks like `AW-123456789`.
   - The **Conversion label**, which is a separate alphanumeric string.

The conversion ID and label identify the tag; they are not payment API secrets. Nevertheless, keep the production `.env` file private.

Do not create a second purchase conversion for the same action unless there is a clear measurement plan. Duplicate purchase goals can distort reporting and automated bidding.

---

## 6. Configure production

1. Open the production project on the VPS:

   ```bash
   cd /home/don/STDA-MovingTrain
   ```

2. Edit `.env` and set the real values:

   ```bash
   GOOGLE_ANALYTICS_ID=G-XXXXXXXXXX
   GOOGLE_ADS_CONVERSION_ID=AW-123456789
   GOOGLE_ADS_CONVERSION_LABEL=your_conversion_label
   ```

3. Recreate only the `web` service so it reads the updated environment:

   ```bash
   docker compose -f docker-compose.prod.yml up -d --force-recreate web
   ```

4. Run Django's checks:

   ```bash
   docker compose -f docker-compose.prod.yml exec web python manage.py check
   ```

5. Confirm that the website and Nginx remain healthy.

Changing only these environment values requires no CSS build, database migration, or new Python package. Deploying the GA4 purchase implementation itself does require applying the `scheduling/0011` and `payments/0003` migrations before serving the updated views.

---

## 7. Verify tracking before advertising

### 7.1 Verify GA4

1. Open the website in a normal browser session.
2. Visit several public pages, such as Home, Courses, Tutors, and Quiz.
3. In GA4, open **Reports → Realtime**.
4. Confirm that your visit and page views appear.
5. Check again with a mobile device or mobile browser emulation.

Realtime data can appear quickly, but standard GA4 reports can take longer to update.

### 7.2 Verify the Google Ads tag

1. Open [Google Tag Assistant](https://tagassistant.google.com/).
2. Start a diagnosis for `https://themovingtrain.org`.
3. Confirm that the `AW-...` Google tag loads.
4. Resolve any installation errors before launching campaigns.

### 7.3 Verify a purchase conversion

1. Use a provider-approved test method, or a carefully controlled live payment. A live test may involve real charges and payment-provider fees.
2. Complete a recurring or special booking payment as a student.
3. On the confirmation page, use Tag Assistant or browser developer tools to confirm that the `conversion` event fires.
4. Verify that the event contains:
   - `send_to`: the correct `AW-ID/LABEL` combination;
   - `value`: the amount paid;
   - `currency`: `NGN`;
   - `transaction_id`: the payment reference.
5. Confirm that a pending booking does not fire the purchase event.
6. Confirm that viewing the same confirmation as a coach or staff member does not fire it.

Ads conversion reports may take several hours, and sometimes up to a day, to reflect a conversion. Do not treat an immediate empty report as proof that tracking failed.

### 7.4 Verify GA4 ecommerce purchases

The same eligible payment paths send a separate GA4 `purchase` event with the transaction reference, NGN value, and one ecommerce item. In Tag Assistant or GA4 DebugView, confirm that this event is sent to the `G-...` measurement ID. GA4 standard reports may take longer to update than Realtime reports.

Each payment is claimed once using its database `analytics_tracked_at` field, so refreshing or revisiting a confirmation page must not emit another purchase. Google Ads and GA4 use different attribution models, so their totals will not necessarily match.

Avoid importing the GA4 purchase into Google Ads while also using the direct Ads purchase conversion as a primary bidding goal, or purchases may be counted twice.

---

## 8. Link GA4 and Google Ads

1. In GA4, go to **Admin → Product links → Google Ads links**.
2. Select the academy's Google Ads account.
3. Enable the recommended linking options.
4. Confirm that Google Ads auto-tagging is enabled so ad clicks carry the `gclid` needed for attribution.
5. Keep the direct Google Ads purchase conversion as the primary purchase goal for campaigns.

Linking allows the products to share eligible data. It does not replace the purchase conversion tag.

---

## 9. Prepare the website and campaign economics

Before spending money, define what a successful campaign must achieve.

### 9.1 Set the business targets

Record:

- The main programme to promote.
- The locations you can serve.
- The target audience, such as parents looking for online chess coaching.
- The monthly advertising budget.
- The average purchase value.
- The maximum acceptable cost to acquire a paying student.
- The number of new students the coaches can realistically accommodate.

A useful budgeting relationship is:

```text
Estimated monthly budget = average daily budget × 30.4
```

Actual charges depend on campaign delivery and billable interactions. Advertising spend does not guarantee purchases.

### 9.2 Prepare the landing pages

Review the pages that will receive advertising traffic:

- Explain the programme and who it is for.
- Show the coach's experience and trust signals.
- Make pricing or the booking process clear.
- Use a strong call to action, such as **Book a Class** or **View Courses**.
- Make the page fast and usable on mobile devices.
- Remove broken links and outdated information.
- Ensure the payment and confirmation journey works end to end.

Send each advert to the most relevant course or booking page rather than sending every visitor to the homepage.

---

## 10. Build the first campaign

A Search campaign is a sensible starting point because it can reach people actively looking for chess lessons.

### 10.1 Campaign settings

1. In Google Ads, create a new campaign.
2. Choose a sales/leads objective that supports the purchase goal, then select **Search**.
3. Select `Successful Booking Purchase` as a campaign conversion goal.
4. Name the campaign clearly, for example `Search - Online Chess Coaching - Nigeria`.
5. Start with Search traffic only. Consider leaving Display Network expansion and Search Partners off until baseline performance is understood.
6. Target only locations the academy can serve. Use the location option for people **present in** the targeted locations, rather than people merely showing interest in them.
7. Set the appropriate language targeting, normally English for the initial campaign.
8. Set a daily budget derived from the approved monthly budget.
9. For a new account with little conversion history, use a controlled clicks-based bidding approach while validating tracking and traffic. Consider conversion-based bidding after purchases are being recorded consistently and there is enough data to assess performance.
10. Keep the campaign paused while finishing the keywords, ads, and final review.

Because the academy teaches children, direct the advertising toward parents and guardians. Follow Google's policies concerning minors and personalized advertising.

### 10.2 Create focused ad groups

Use a small number of tightly themed ad groups, for example:

- Online chess classes for children
- Private chess coaching
- Beginner chess lessons

Possible high-intent keyword themes include:

- `online chess classes for kids`
- `chess coach for children`
- `private chess lessons online`
- `beginner chess classes`
- `chess academy Nigeria`

Start with phrase and exact match rather than relying entirely on broad match. Review actual search terms after launch.

Add irrelevant terms as negative keywords when observed. Possible examples include job searches, software downloads, and people looking only for a chess game to play. Avoid blocking searches that could still represent prospective students.

### 10.3 Write the advertisements

For each ad group, create a responsive search ad with:

- Headlines that closely match the ad group's keywords.
- Clear descriptions of online coaching, programme level, and booking action.
- A relevant final URL.
- Accurate claims only.

Examples of messages to adapt:

- `Online Chess Classes for Children`
- `Learn With an Experienced Chess Coach`
- `Beginner to Advanced Chess Training`
- `Book a Chess Class Online`

Add relevant assets/sitelinks such as Courses, Tutors, Quiz, and Contact. Do not claim guaranteed results or rankings.

---

## 11. Final review and launch

Complete this checklist before enabling the campaign:

- [ ] GA4 realtime reporting works.
- [ ] The Google Ads tag loads correctly.
- [ ] A test purchase has been verified.
- [ ] The campaign uses the purchase conversion goal.
- [ ] Auto-tagging is enabled.
- [ ] The landing pages work on mobile.
- [ ] Locations, language, budget, and bidding are correct.
- [ ] Billing is configured.
- [ ] Ad copy and keywords comply with Google policies.
- [ ] Coaches have capacity for new students.
- [ ] The team understands that spend can occur without generating sales.

Enable the campaign only after these checks pass. Google must review the ads before they can serve; review and delivery are not always immediate.

---

## 12. Monitor and improve the campaigns

During the first few days:

- Check that ads are approved and serving.
- Check spend, clicks, and search terms.
- Add clearly irrelevant search terms as negatives.
- Confirm that any recorded purchases match real bookings.

On a recurring weekly basis, review:

- Impressions and clicks.
- Click-through rate.
- Cost per click.
- Purchases and purchase value.
- Cost per purchase.
- Conversion value relative to advertising cost.
- Search-term quality.
- Performance by landing page, location, and device.

Do not optimize only for cheap clicks. A campaign with fewer clicks but more paying students may be performing better.

Avoid making many large changes simultaneously. Change one major variable at a time, allow enough data to accumulate, and document each significant change. Pause keywords, ads, or campaigns that spend without producing useful results, and expand the themes that produce profitable bookings.

---

## 13. Improve organic rankings with Search Console and SEO

This work is separate from paid campaigns.

### 13.1 Configure Search Console

1. Open Google Search Console.
2. Add `themovingtrain.org` as a property.
3. Prefer a **Domain property** and verify it with the DNS provider so all protocol and subdomain variants are covered.
4. Submit the existing sitemap:

   ```text
   https://themovingtrain.org/sitemap.xml
   ```

5. Confirm that `https://themovingtrain.org/robots.txt` is accessible.
6. Use URL Inspection on the homepage, course pages, tutor page, and important articles.
7. Request indexing for important new or substantially updated pages.

The project already generates a sitemap for static pages, courses, and blog posts.

### 13.2 Improve on-page SEO

For every important page:

- Use a unique, descriptive title and meta description.
- Have one clear main heading.
- Explain the topic thoroughly in natural language.
- Match the page to a real search intent, such as online chess classes for children.
- Link internally to relevant courses, coaches, articles, and booking pages.
- Use descriptive image alternative text where appropriate.
- Keep URLs readable and canonical URLs correct.

### 13.3 Publish useful content

Build a content plan around questions prospective parents and students ask, for example:

- How to choose a chess coach for a child.
- What beginners learn in their first chess lessons.
- How online chess classes work.
- How much chess practice a child needs.
- How to prepare for a first chess tournament.

Prioritize original, useful content over publishing large numbers of shallow keyword pages. Connect each article to a relevant course or booking action.

### 13.4 Improve technical SEO and authority

- Monitor Page Experience/Core Web Vitals and mobile usability.
- Test important pages with [PageSpeed Insights](https://pagespeed.web.dev/).
- Keep HTTPS, sitemap, robots rules, and canonical URLs working.
- Fix broken links and redirect chains.
- Seek genuine mentions and links from relevant schools, chess organizations, partners, and community publications.
- Do not buy spam links or use guaranteed-ranking schemes.
- If the business has an eligible physical presence, complete and maintain an appropriate Google Business Profile.

Review Search Console queries and page performance regularly. Organic SEO normally requires sustained work over months; neither Google Ads nor Search Console can guarantee a particular ranking.

---

## 14. Recommended order of execution

1. Create GA4 and its web data stream.
2. Create the Google Ads purchase conversion.
3. Configure the three production environment values.
4. Recreate `web` and verify GA4 and purchase tracking.
5. Link GA4 and Google Ads.
6. Verify Search Console and submit the existing sitemap.
7. Prepare landing pages, targets, budget, keywords, and ads.
8. Review the campaign checklist and launch.
9. Optimize campaigns using purchase and profitability data.
10. Continue content, technical SEO, and authority building in parallel.

The first immediate action is to create the GA4 property and copy its `G-...` Measurement ID.
