# Токены — дословно

Источник: `frontend/src/styles.css:2-24`. Те же значения продублированы в
`admin/app/static/cabinet.css`, `admin/app/static/admin.css`,
`site/template.html` — при правке токена меняются все четыре файла и этот (`references/tokens.md`).

Блок для `<style>` макета, копировать как есть:

```css
/* tokens: verbatim from frontend/src/styles.css */
:root {
  --bg: #e4f1ff; --surface: #ffffff; --ink: #2a1a48; --muted: #6a5e86; --line: #d3e2f4;
  --grape: #5b2e8c;
  --pom: #e23b55; --pom-dark: #b8243d; --pom-soft: #ffe3e8;
  --sun: #ffc531; --sun-dark: #e0a300;
  --mint: #1fb386; --mint-dark: #13875f; --mint-soft: #ddf7ee;
  --hill1: #a4db86; --hill2: #72c36b;
  --blob-edge: rgba(42, 26, 72, 0.14);
  --word-color: var(--grape);
  --safe-top: env(safe-area-inset-top, 0px); --safe-bottom: env(safe-area-inset-bottom, 0px);
  --safe-left: env(safe-area-inset-left, 0px); --safe-right: env(safe-area-inset-right, 0px);
}
@media (prefers-color-scheme: dark) { :root:not([data-theme='light']) {
  --bg: #131634; --surface: #1e2250; --ink: #f3efff; --muted: #aba5d3; --line: #2f3572;
  --mint-soft: #113d35; --pom-soft: #44182a; --hill1: #27523a; --hill2: #1c4030;
  --blob-edge: rgba(255, 255, 255, 0.22); --word-color: var(--sun);
} }
:root[data-theme='dark'] {
  --bg: #131634; --surface: #1e2250; --ink: #f3efff; --muted: #aba5d3; --line: #2f3572;
  --mint-soft: #113d35; --pom-soft: #44182a; --hill1: #27523a; --hill2: #1c4030;
  --blob-edge: rgba(255, 255, 255, 0.22); --word-color: var(--sun);
}
```

Что чем является:

- `--grape` — бренд, заголовки, грузинское слово в светлой теме. Не меняется в тёмной.
- `--pom` / `--pom-dark` — главная кнопка «Играть», неверный ответ, ошибка.
- `--mint` / `--mint-dark` — верный ответ, «Дальше», прогресс.
- `--sun` / `--sun-dark` — монеты, кнопка «Послушать», грузинское слово в тёмной теме.
- `--*-soft` — фон тостов и мягких плашек той же семантики.
- `--hill1/2` — декоративные холмы внизу детских экранов, `--blob-edge` — кромка цветного пятна под картинкой слова.
- Белый текст на цветных кнопках — `#fff` (в коде так и захардкожено, переменной нет).

Радиусы и тени в переменные не вынесены. Принятые значения: карточка 24px,
плитка 26px, кнопка «Играть» 22px, плитки-кнопки 14–16px, карточки кабинета и
админки 16px, круглые элементы 50%. Тень — только «псевдо-3D» под кнопкой:
`box-shadow: 0 Npx 0 var(--x-dark)` или `0 5px 0 var(--line)` у нейтральных
плиток. Размытых теней в продукте нет.


## Шрифты

```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Nunito:wght@500;700;800;900&family=Noto+Sans+Georgian:wght@600;800&display=swap" rel="stylesheet">
```

```css
body { font-family: 'Nunito', system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif; font-size: 17px; line-height: 1.45; color: var(--ink); background: var(--bg); }
.ka { font-family: 'Noto Sans Georgian', 'Sylfaen', 'DejaVu Sans', sans-serif; font-weight: 800; }
```

Любой грузинский текст — в `.ka`. Всегда. Кириллическая транслитерация идёт
вторым слоем: мельче (`.tr` 18px) и `--muted`. Порядок «сначала оригинал,
потом подсказка» не нарушается.

Подключать Google Fonts в макет обязательно там, где смотрим на буквы, слова
или кнопки; в макетах таблиц и списков допустим системный фолбэк, но это
называется в отчёте.
