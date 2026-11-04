# Introduction Form Implementation Plan

> **For agentic workers:** Implement inline using superpowers:executing-plans, with test-first verification.

**Goal:** Disable introduction nicknames, guide introduction posts, and skip entry guidance when following the homepage invitation.

**Architecture:** Keep existing posts as text. Render four optional question fields and assemble answered questions into one post before the existing moderation flow. Use an explicit invitation query parameter for a single visit, without persisting a popup exemption.

**Tech Stack:** Existing Flask, SQLite, Jinja and browser JavaScript.

**Spec:** The user's follow-up request and `docs/superpowers/specs/2026-11-04-newcomer-introductions-design.md`.

## Constraints and review focus

- Deny nickname writes and hide existing introduction nicknames in all post views; preserve join/leave and other-community nicknames.
- Four guiding questions, each optional; at least one nonempty response or ordinary post content is needed. Questions ask about the person, interests, reasons for joining, and questions/learning.
- Support the default introduction selection on the homepage and changing the community selector; keep ordinary posts and draft moderation compatible.
- Only eligible newcomers using the homepage invitation skip entry guidance for that visit. Direct visits still show it.

## Tasks

- [x] Add regression tests and confirm missing functionality fails.
- [x] Block/hide nicknames and clear old introduction nicknames through the repeatable migration.
- [x] Add question fields, conditional composer state, server assembly and homepage invitation exception.
- [x] Run full tests, inspect diff, review changes and migrate local nickname data after backup.

## Verification

- Full suite: `python -m unittest discover -q` passes 106 tests, including 28 newcomer tests.
- JavaScript composer checks pass for general → introduction → general, disabled/hidden states and preserved draft values.
- Independent review found no blocking issues. Its JavaScript-disabled switching observation is covered by a new regression: if the ordinary content field is absent, visible question answers are assembled for the selected community rather than discarded.
- Guided answers preserve line breaks and display as plain text in introduction feeds, details and profiles. Existing moderation and draft editing remain in use.
- `git diff --check` passes (Git reports only existing repository line-ending normalization notices).
- Local database backup: `.local-deps/database.pre-introduction-form-20261104-024920.sqlite`. Migration ran twice; content and membership counts, other-community aliases, integrity and foreign key checks passed.

## Follow-up: basic homepage form and posting eligibility

The homepage must always use the basic post form. Render guided questions and their selector script only inside `/c/introduction`, for eligible newcomers. Ineligible users must not see its posting option or composer. Deny their submissions before moderation and recheck eligibility atomically with the insert to prevent concurrent duplicate introductions. Keep comments available so established users can welcome newcomers. Persist introduction history in `user_introductions` so deleting a post does not restore eligibility; backfill existing authors during migration.

- [x] Add failing regressions for basic homepage composer, age cutoff, duplicate introductions and hidden posting options.
- [x] Limit the guided composer to its community and enforce eligibility in the server insert.
- [x] Verify eligible and established users, moderation, existing functionality and concurrent submissions; update documentation.

Latest verification: all 114 tests pass, including simultaneous submissions, eligibility after deletion, and history backfill. Composer JavaScript checks and diff checks pass. Independent review found no issues. The local database was backed up to `.local-deps/database.pre-introduction-eligibility-20261104-025638.sqlite` and migrated twice with content and membership counts preserved; integrity, foreign key and route smoke checks pass.
