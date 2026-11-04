# Newcomer introductions

Implement design claims 18, 19 and 21 as described in the request, using the existing Flask, SQLite and Jinja application.

- A newcomer has an account younger than seven days and has never published in `/c/introduction`. Unknown account creation dates do not qualify. Persist introduction history so deleting a post does not restore newcomer status; backfill existing introduction posts through the migration.
- Create `/c/introduction` through the repeatable communities migration. Add eligible existing accounts once and automatically join new accounts, preserving the existing general membership.
- Select introduction by default in the newcomer's homepage composer and show an “Introduce yourself” invitation until eligibility ends.
- Show an entry dialog on ordinary visits to introduction, including direct URLs. Skip it for the current visit when a newcomer follows the homepage invitation (`introduce=1`). Copy: “Welcome newcomers warmly. Basic questions and mistakes are normal. Respond kindly without mocking or being dismissive.”
- Before publishing a comment on a newcomer's post, show the same reminder in a confirmation dialog. Apply it in every community, except comments on one's own posts. Preserve drafts on edit/cancel and support browsers without JavaScript.
- Use `/c/introduction` as the canonical spelling; redirect `/c/introducton` to it.

Implementation choice: extend the existing server-rendered forms and native dialog pattern. A JavaScript-only reminder would not cover direct submissions; a separate onboarding application would add unnecessary infrastructure. Entry dialogs use native controls, and comment confirmation uses signed, expiring, single-use tokens bound to the sender, post and content.

No new dependencies. Only newcomers may create introduction posts: accounts younger than seven days that have never introduced themselves. This is enforced by the server and checked atomically during insertion, with introduction history recorded in the same transaction. Established users can still browse introduction and welcome newcomers in comments. Memberships remain user-controlled after the automatic join. Verify eligibility boundaries, migration repeatability, homepage defaults, direct entry, comment confirmation, editing, and existing behavior using temporary databases.

Follow-up: introduction does not support nicknames. Hide its nickname editor, reject nickname updates, ignore old aliases in every post view and clear them through the migration. Keep its membership controls. Inside the introduction community only, structure the composer using four optional questions: what the user would like others to know, interests/hobbies, what brought them here, and what they want to learn or ask. Join nonempty answers into one text post before moderation. The homepage and all other community pages keep the basic post form, regardless of the selected posting community. Hide introduction as a posting destination for ineligible accounts and hide its composer on their introduction visits. Preserve freeform posting compatibility for eligible existing clients and moderation draft editing.
