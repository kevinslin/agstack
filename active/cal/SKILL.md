---
name: cal
description: Preview available meeting options and create Google Calendar invites with attendee availability and room booking after confirmation. Use when directly invoked via $cal or when asked to schedule a meeting.
dependencies: []
---

# cal

Use this skill to schedule a Google Calendar meeting end to end: resolve attendees, find mutual free slots, preview viable options, let the user choose, book a room when requested, create the invite, and verify the final event state.

## Defaults

- Timezone: `America/Los_Angeles` unless the user specifies another timezone or the attendee calendars clearly require one.
- Duration: 30 minutes unless the user specifies another duration or there is a clear precedent.
- Start time: begin meetings 5 minutes after the hour or half-hour (for example, 09:05 or 09:35) unless the user explicitly requests a different start time.
- Search window: the next 5 business days during normal work hours, 09:00-17:00 local time, unless the user provides a narrower window.
- Lunch window: avoid scheduling meetings that overlap 12:00-13:00 local time. If every available option overlaps lunch, ask the user before creating the invite.
- Title: use a concise `<Person A> / <Person B>` title for a 1:1 unless the user provides a title.
- Meeting link: add Google Meet by default unless the user asks for in-person only.
- Visibility: use Google Calendar default visibility unless the user explicitly requests private visibility.

## Workflow

1. Resolve people and calendars.
- Get the authenticated Calendar profile to identify the current user.
- Resolve named attendees with Google Contacts first; use Slack user search as a fallback for workspace email addresses.
- If there are multiple plausible people, ask before creating the invite.

2. Determine constraints.
- Normalize relative dates into explicit dates and include the weekday, date, time, timezone, and duration in reasoning.
- If the user says "when we are both available" without a window, use the default search window.
- If the user asks for rooms, use OfficeSpace to resolve each attendee's office/seat when available.

3. Find candidate rooms.
- Prefer rooms in the same site as the attendees.
- Prefer the same floor as either attendee, then adjacent floors in the same site.
- Use OfficeSpace room lists to get human room names.
- Do not assume an OfficeSpace room ID is a Google Calendar resource calendar.
- To reserve a room in Calendar, use a resource calendar email. If Calendar does not expose a room directory, mine recent primary-calendar events for the room's `resource.calendar.google.com` attendee address, then verify it with free/busy.
- If no resource calendar can be resolved, create the event only after telling the user that the room would be location text only; do not claim it is booked.

4. Check availability.
- Use Google Calendar free/busy for all attendee calendars and any candidate resource calendars.
- For flexible scheduling, generate candidate start times 5 minutes after the hour or half-hour and calculate the end time from the full requested duration.
- Only offer slots that cover the full requested duration for every attendee and room resource.
- Ignore openings shorter than the requested duration.
- Exclude openings that overlap the lunch window. If no non-lunch opening exists in the requested or default search window, ask the user before scheduling over lunch.
- If a shared attendee slot has no verified room, continue searching for slots that include a verified room when the user asked to book rooms.

5. Preview options and get confirmation.
- When the user provides a time range or flexible window, present 2-3 distinct viable options within that window before creating an event.
- Include the weekday, explicit date, start and end time, timezone, and verified room label or booking limitation for each option.
- Recommend one option when useful, but do not treat the recommendation as the user's selection.
- Ask the user to choose an option and wait for explicit confirmation before creating the event.
- If only one viable option exists, preview that option and still ask for confirmation.
- Skip the preview only when the user provides one exact slot and explicitly asks to book it.
- After the user chooses, re-check attendee and room availability and search for an equivalent event immediately before creating the invite.
- If the chosen option is no longer available, do not silently choose another. Present refreshed options and ask again.

6. Create the event.
- Create the event with attendee emails and room resource emails in `attendees`.
- Put the human room label in `location`.
- Include a short description only when useful; do not add noisy scheduling notes.
- Set `self_attendance: accepted`.
- Add Google Meet unless the user said not to.

7. Verify after creating.
- Re-read the event by ID.
- Check free/busy for each room resource over the meeting window after creation.
- Report whether each room resource shows busy and whether the event attendee response is `accepted`, `declined`, or `needsAction`.
- If the room shows `needsAction` but free/busy is busy for the created window, say exactly that; do not overstate final room acceptance.

## Safety

- Do not create duplicate invites if an equivalent event already exists in the target window; search before creating when the request resembles a retry.
- Do not infer permission to choose a slot from a request to schedule within a range; preview the available options and wait for the user's selection.
- Do not delete or reschedule existing events unless the user explicitly asks.
- Treat "book rooms for both of us" as "book a suitable shared room near both attendees" when both people are in the same site; if they are in different sites, book one room per site when resource calendars can be verified.
- If a write fails after a partial create, read/search the calendar before retrying so duplicates are not created.

## Final Report

Report the created event with:

- Title
- Weekday, date, start and end time, timezone
- Attendees
- Room labels and booking state
- Google Meet link when present
- Calendar event URL when available
