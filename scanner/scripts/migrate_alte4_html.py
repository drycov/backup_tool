"""One-off BS4/AdminLTE3 → BS5/AdminLTE4 markup migration for index.html."""
import re
from pathlib import Path

p = Path(__file__).resolve().parents[1] / "static" / "index.html"
text = p.read_text(encoding="utf-8")

replacements = [
    ('data-toggle="dropdown"', 'data-bs-toggle="dropdown"'),
    ('data-toggle="tab"', 'data-bs-toggle="tab"'),
    ('data-dismiss="modal"', 'data-bs-dismiss="modal"'),
    ('dropdown-menu-right', 'dropdown-menu-end'),
    ('font-weight-light', 'fw-light'),
    ('btn-default', 'btn-outline-secondary'),
    ('btn-block', 'w-100'),
    ('float-right', 'float-end'),
    ('text-right', 'text-end'),
    ('custom-control custom-switch', 'form-check form-switch'),
    ('custom-control custom-checkbox custom-control-inline', 'form-check form-check-inline'),
    ('custom-control custom-checkbox', 'form-check'),
    ('custom-control-input', 'form-check-input'),
    ('custom-control-label', 'form-check-label'),
    ('badge badge-secondary', 'badge text-bg-secondary'),
    ('badge badge-info', 'badge text-bg-info'),
    ('badge badge-success', 'badge text-bg-success'),
    ('badge badge-danger', 'badge text-bg-danger'),
    ('badge badge-warning', 'badge text-bg-warning'),
    ('badge badge-primary', 'badge text-bg-primary'),
    ('badge badge-light', 'badge text-bg-light'),
    ('badge badge-dark', 'badge text-bg-dark'),
    ('badge badge-orange', 'badge text-bg-warning'),
    ('data-widget="pushmenu"', 'data-lte-toggle="sidebar"'),
    ('data-widget="treeview"', 'data-lte-toggle="treeview"'),
    ('nav nav-pills nav-sidebar', 'nav sidebar-menu'),
    ('main-sidebar sidebar-dark-primary elevation-4', 'app-sidebar bg-body-secondary shadow'),
    ('main-header navbar navbar-expand navbar-white navbar-light border-bottom', 'app-header navbar navbar-expand bg-body border-bottom'),
    ('content-wrapper', 'app-main'),
    ('content-header', 'app-content-header'),
    ('section class="content"', 'div class="app-content"'),
    ('class="wrapper"', 'class="app-wrapper"'),
    ('hold-transition', 'layout-fixed sidebar-expand-lg bg-body-tertiary'),
]
for old, new in replacements:
    text = text.replace(old, new)

text = re.sub(r"\bmr-(\d)", r"me-\1", text)
text = re.sub(r"\bml-(\d)", r"ms-\1", text)
text = re.sub(r"\bpr-(\d)", r"pe-\1", text)
text = re.sub(r"\bpl-(\d)", r"ps-\1", text)

text = text.replace(
    '<button type="button" class="close" data-bs-dismiss="modal"><span>&times;</span></button>',
    '<button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>',
)

# input-group-prepend/append → flat BS5
text = re.sub(
    r'<div class="input-group-prepend">\s*',
    "",
    text,
)
text = re.sub(
    r'<div class="input-group-append">\s*',
    "",
    text,
)
text = re.sub(
    r'</div>\s*(?=\s*<input type="search" id="global-search")',
    "",
    text,
    count=1,
)

p.write_text(text, encoding="utf-8")
print(f"Updated {p}")
