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
