# Семьи экранов и эталоны

| Семья | Где живёт | Рамка в макете | Особенности | Эталон |
|---|---|---|---|---|
| Детское приложение (PWA) | `frontend/src` | телефон 410×864 | 17px, `.wrap` max-width 540px, safe-area, холмы, кнопки с тенью | `docs/mockups/home-menu.html` (общий каркас), `docs/mockups/home-today.html` (главный экран «Сегодня» и нижние вкладки) |
| Кабинет родителя (Telegram Mini App) | `admin/app/templates/cabinet_*.html`, `cabinet.css` | телефон + шапка Telegram `.tgh`, радиус рамки 48px | 15px, без safe-area, списки `.trow`, чипы `.chip`, скелетон `.sk` | `docs/mockups/parent-cabinet-progress.html` (экран), `docs/mockups/parent-topic-access.html` (строка темы и переключатель — по коду, свежее) |
| Админка (бэк-офис) | `admin/app/templates/base.html`, `admin.css` | окно браузера `.win` с адресной строкой; `.win.ph` для узкого | десктоп, `.amain` 1180px, таблица `table.pt`, акцентного цвета кнопки нет | `docs/mockups/admin-parents.html` |
| Бот | `backend/bot/texts.py` | телефон с интерфейсом Telegram iOS | раскадровка диалога, свои `--t-*` переменные, токены Мзико почти не нужны | `docs/mockups/bot-registration.html` |
| Лендинг для родителей | `site/template.html`, `scripts/build_site.py` | сайт с переключателем ширины 390/1100 | container queries, скриншоты из `docs/general/parent-guide/`, плейсхолдер `.ph` для битой картинки | `docs/mockups/parent-landing.html` |

Кабинет и админка сознательно на тех же токенах, что и детское приложение:
отдельного визуального языка у них нет, отличие в плотности и в том, что
детские кнопки с тенью там не используются.

**Иконка** одна на все оболочки: солнце с буквой მ, источник
`frontend/public/icons/icon.svg` (буква контуром, цвета значениями), растр
`icon-192.png` и `icon-512.png` из него. Сайт, админка и кабинет ссылаются на
`/icons/…` абсолютным путём. Варианты и причины выбора —
`docs/mockups/site-favicon.html`, устройство — `docs/features/app-icon.md`.
