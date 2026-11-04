# Newcomer Introductions Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Give newcomers an introduction community and encourage kind replies.

**Architecture:** Reuse Flask routes, SQLite membership records and server-rendered native dialogs. Share the newcomer SQL predicate between migration and request handling.

**Tech Stack:** Python, Flask, SQLite, Jinja, native HTML dialog.

**Spec:** `docs/superpowers/specs/2026-11-04-newcomer-introductions-design.md`

## Global Constraints

- Eligibility: account younger than seven days and no introduction post.
- Canonical route `/c/introduction`; typo alias `/c/introducton`.
- Preserve existing general membership and moderation behavior; add no dependencies.
- Use the requested welcome message for entry and comment reminders.

## Review Focus

- Seven-day boundary and absent creation dates: do not qualify.
- Repeated migrations: preserve opt-outs and existing posts.
- Direct entry and direct comment POSTs: show reminders.
- Confirmations: prevent tampering, replay and use by another account.
- Draft editing and JavaScript-disabled clients: retain text without publishing.

### Task 1: Eligibility, default membership and homepage

Files: `newcomers.py`, `migrate_communities.py`, `app.py`, `templates/feed.html.j2`, `test_newcomers.py`, `tests_communities.py`.

- [x] Add and run failing integration tests for migration backfill, newcomer homepage defaults and eligibility boundaries.
- [x] Implement shared eligibility predicate, repeatable migration and signup memberships.
- [x] Implement homepage invitation and selected community; add direct entry dialog and alias.
- [x] Verify focused tests and update existing community-count expectation for the additional built-in community.

### Task 2: Comment reminder and verification

Files: `app.py`, `templates/newcomer_comment_warning.html.j2`, `templates/newcomer_guidance.html.j2`, `test_newcomers.py`, `README.MD`.

- [x] Add and run failing tests for confirmation before insert, editing, token binding and replay, established authors, self-comments and missing posts.
- [x] Implement signed single-use comment confirmation with native dialog and form fallback.
- [x] Run the full unittest suite, check diff formatting, review requirements and document migration usage.

## Verification and implementation decisions

- `python -m unittest discover -q`: 94 passing tests, including 16 newcomer tests.
- `git diff --check`: passes.
- Independent review caught a redirect to the POST-only comment URL and replay using an older signed session cookie. Regression tests reproduced both failures before their fixes.
- Ruling: always redirect comment submissions to the post detail page so the confirmation page cannot become the redirect destination.
- Ruling: consume confirmation nonces in SQLite, atomically with comment insertion. Tokens remain usable across tabs; replay fails even with an older session cookie. Prune receipts older than one day; tokens expire after 15 minutes.
- Local database backed up under `.local-deps/database.pre-introduction-20261104-023726.sqlite`. Migration applied twice; user/post/comment/reaction counts unchanged, integrity and foreign key checks pass.
- Local route smoke checks: homepage, community list and introduction return 200; typo alias redirects.
