# Design kit

Backup Tools UI (AdminLTE) подключается к [@drycov/design-kit](https://github.com/drycov/design-kit).

## Файл

`scanner/static/css/design-kit.css` — токены `--tg-*` и bridge для legacy переменных.

## Подключение

В `scanner/static/index.html` **перед** `style.css` и AdminLTE:

```html
<html lang="ru" class="enterprise-ui" data-tg-theme="dark">
...
<link rel="stylesheet" href="/static/css/design-kit.css">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/admin-lte@4.0.0/dist/css/adminlte.min.css">
<link rel="stylesheet" href="/static/css/style.css">
```

В скрипте темы синхронизируйте:

```js
document.documentElement.setAttribute("data-tg-theme", theme); // light|dark
document.documentElement.setAttribute("data-bs-theme", theme);
```

Кнопки `.btn-primary` подкрашиваются в `#2aabee` через design-kit.
