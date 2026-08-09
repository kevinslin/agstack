---
name: event-report
description: Research verified local events and create ranked, source-linked activity reports.
dependencies: []
---

# Event Report

Research activities people can actually attend, distinguish confirmed events from recurring communities, and produce useful, source-backed recommendations.

## When to use

Use for requests involving local events, activity reports, weekend plans, workshops, classes, clubs, meetups, festivals, volunteer opportunities, retreats, family activities, or recurring communities. Apply it to one subject or several, including specialized requests such as salsa workshops or silent meditation retreats.

Read `./references/research-workflow.md` before researching. Read `./references/report-template.md` when creating or updating a durable report, comparing multiple subjects, or producing a detailed event inventory.

## Resolve the request

Identify:

- Subject and any required subtype, such as salsa instruction rather than a dance social.
- City, nearby regions, acceptable travel distance, and the location's time zone.
- Exact target dates and the current local time; resolve “tonight,” “tomorrow,” “this weekend,” and “next weekend” explicitly.
- Preferences such as beginner friendliness, age, budget, accessibility, family attendance, experience, equipment, or silent practice.
- Whether the user wants a chat recommendation, a durable report, several category reports, or both.
- The requested output path, an established project reports directory, or another clearly applicable existing convention.

Preserve user-specified dates even when they differ from the upcoming calendar weekend. If the user asks for events today, exclude already-finished activities from the actionable shortlist. Ask a clarifying question only when missing information materially prevents useful work.

## Research and verify

1. Identify active organizers, venues, clubs, instructors, public agencies, and recurring communities in the requested region.
2. Search the web using exact dates, year, location, activity, and relevant subtypes. Event schedules and pricing change; do not rely on memory alone.
3. Prioritize current organizer or venue pages, official public calendars, organizer-owned registration, and first-party schedules. Use aggregators only for discovery or clearly attributed secondary evidence.
4. Verify each occurrence, local start and end times, address, price, registration, eligibility, availability, and cancellations. Check conflicting dates against the actual weekday and year.
5. Label evidence accurately: organizer-confirmed, first-party weekly recurrence without date confirmation, secondary-only, sold out, waitlisted, canceled, ended, or uncertain.
6. Distinguish the precise activity requested from adjacent activities, and separate substantive workshops or retreats from short introductory lessons or entertainment.
7. Rank by actual availability, source quality, fit, accessibility, travel, cost, and suitability for the user's preferences.

Never invent a missing price, address, end time, age limit, skill level, capacity, or registration status. Explain meaningful source conflicts and provide the organizer's direct event or registration link.

## Delegate only when authorized

Use subagents only when the user explicitly requests delegation or parallel agents, or applicable instructions explicitly require delegation. When authorized and the work naturally separates, assign one agent per subject, date, geography, or event format with clear ownership; integrate their findings and reconcile conflicts before reporting.

## Produce the right output

For a concise request, respond with a small ranked shortlist and enough details to attend. For a report, create a durable, readable Markdown artifact following `./references/report-template.md`. For multiple requested categories, normally write one report per category and provide a short cross-category summary.

Use the user-provided directory first. Otherwise reuse an existing project `reports/` directory when context clearly establishes it. Choose descriptive kebab-case filenames such as `salsa-workshops.md`, `silent-meditation-retreats.md`, or `volunteering.md`. Preserve unrelated existing files and edits.

Include:

- Exact dates, local times, time zone, organizer, venue, full address, price, eligibility, and direct source or registration links.
- Ranked, genuinely actionable events separated from recurring venues, future opportunities, and unverified leads.
- Confidence, booking deadlines, capacity, prerequisite, parking, weather, smoke, cancellation, and accessibility caveats when material.
- Honest alternatives when no strong matching event is verified; do not pad the recommendations with loosely related activities.
- A practical day-by-day plan when the user asks what to attend.

Browse registration pages read-only. Do not reserve, register, contact an organizer, purchase a ticket, or otherwise act externally without an explicit request.

## Final verification

Before reporting completion, confirm that requested files exist, source links are present, dates and weekdays agree, local times are identified, stale or unavailable events are not presented as open, and reported uncertainty is visible. Return clickable absolute local-file links when a report was created.
