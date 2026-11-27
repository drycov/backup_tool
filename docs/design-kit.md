# Design kit integration

Source: https://github.com/drycov/design-kit (v0.3 CSS).
The six upstream CSS entry points are vendored under scanner/static/css/vendor/design-kit.
Load order: AdminLTE, upstream kit, legacy structural styles, compatibility bridge.
Bootstrap remains responsible for modal, dropdown, treeview and existing application behavior.
Both data-bs-theme and data-tg-theme are synchronized before first paint and on theme changes.
Workspace section filtering does not alter permission visibility. Existing API and DOM IDs are retained.

## Verification
- Test light, dark and automatic themes, login and TOTP.
- Verify all ten navigation sections with administrator and restricted roles.
- Verify dropdowns, modals, backup and restore, inventory, scan, provisioning, security, audit and settings.
- Test mobile sidebar and keyboard navigation.
- Run existing scanner CI; browser regression tests are still required.

## Unified workspace (stage 2)
Grouped navigation, permission-aware section visibility, dashboard KPI cards and an inventory device workspace. Device actions delegate to existing configuration, version and MikroTik backup handlers. No new API or database migrations. Browser and integration verification pending.

## Unified Backup Center (stage 3)
The Oxidized page now provides a node-scoped consolidated Git/Binary/RSC history, type filters, per-source error reporting, configuration acquisition, native backups, download and existing restore/diff workflows. Binary/RSC operations require the Python engine and RouterOS support. No global job persistence or aggregate history endpoint has been added. Runtime browser and network tests remain pending.

## Stage 4 — persistent manual backup jobs
POST /api/backup/jobs enqueues a Python-engine configuration or RouterOS backup for an enabled inventory device. GET ?device=NAME lists 50 scoped jobs. The existing BackgroundTask worker executes jobs, rechecks the initiating user's current permissions and device identity, and records outcomes without configuration contents. One active manual job per device; no automatic replay after worker loss. Existing direct endpoints remain unchanged. Schedule management and cross-engine support are not implemented.

## Stage 5 — Backup Operations Center
Global scoped manual-job list, status/type filters, cursor pagination, counts and polling every 10 seconds while the backup page is active. Pending jobs can be cancelled atomically; running jobs cannot. The existing Oxidized schedule and group policies remain authoritative. Automatic engine runs are not included in the manual-job journal.

## Consolidated operations
The Python engine records scheduled runs in the existing task journal; the source filter distinguishes automatic and manual entries. Per-device nonblocking locks coordinate Python fetch, scheduled backup, native backup and restore (PostgreSQL advisory locks; SQLite single-process fallback). Effective policy is shown from existing group/global settings without exposing credentials. Existing group policy editing remains in Settings. No site-specific policy editor or full AdminLTE replacement is included. External Ruby engine runs are not captured.

## Native shell and regression fixes
The main UI loads Bootstrap 5 directly instead of AdminLTE CSS/JS, with a responsive native grid, keyboard-dismissable mobile sidebar and compatibility rules. Scoped job filtering uses numeric JSON IDs, stale workers cannot overwrite a terminal state, and Git writes are serialized within the process and committed by explicit path. Device group hints no longer render passwords or unescaped profile names. Bootstrap remains for modal/tab/dropdown compatibility; browser verification is required. Cross-process Git coordination with other repository writers is not covered by the in-process lock.

## Tabbed workspace
Sidebar opens up to ten reusable, session-local tabs. Only one page panel is visible; switching preserves the existing DOM and forms, with settings dirty confirmation. Tabs support arrow keys, Home/End, Delete and explicit refresh. Permission-filtered sidebar remains the source of available pages. Page refreshes have a 15-second freshness window; not all legacy API calls are deduplicated or cancellable. No persistent tab storage or backend changes.

## Backup-focused workspace
Removed the provisioning page, navigation item, UI handlers and controller code. Legacy provisioning API, task processing and database tables are retained for compatibility; this change does not disable external API access. TOTP provisioning URI is unrelated and retained.
