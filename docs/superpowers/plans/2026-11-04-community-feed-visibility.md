# Community Feed Visibility

Use the existing Flask/SQLite architecture to move homepage visibility from the wilderness name check into a database field.

- Add `communities.show_in_main_feed INTEGER NOT NULL DEFAULT 1 CHECK(show_in_main_feed IN (0, 1))` through the repeatable migration.
- Initially set introduction and wilderness to `0`; all other communities default to `1`. Preserve database changes on later migration runs.
- Filter all homepage sorts and Following with `c.show_in_main_feed = 1` before pagination/limits. Direct community pages, post details and profiles remain accessible.
- Do not add UI fields or update actions; existing create/description forms must ignore attempts to write the flag.
- Verify built-in defaults, arbitrary-community flag changes, migration repeatability, all six homepage filter combinations, and direct community access.

Completed: regression tests were observed failing before implementation; schema and feed query changes are implemented. All 118 tests pass, including all six feed filter combinations, direct community access, database-only configuration, and repeated migrations preserving changed flags. An existing seven-day age fixture now matches signup's whole-second timestamp precision to eliminate clock-dependent failures.

Local migration applied twice after backup to `.local-deps/database.pre-feed-visibility-20261104-143914.sqlite`. General and secret are visible; introduction and wilderness are hidden. Existing content and membership counts were preserved. Database integrity, foreign keys, route smoke checks and diff checks pass.
