# Каркас макета

Макет — одна HTML-страница-галерея, самодостаточная (без сборки; сеть только
на Google Fonts). Структура:

1. `<h1>` — название задачи. `<p class="lead">` — «Как сейчас» со ссылками
   `файл:строка` на текущий код.
2. Для каждого состояния: `<h2>N · Название состояния</h2>`, `<p class="lead">`
   с физикой решения (что появилось, что нажато, почему), затем
   `<figure><figcaption>…</figcaption><div class="fw"><div class="dev phone">…</div></div></figure>`.
   Светлая и тёмная тема рядом, сеткой `.cols`.
3. `<h2>Решения в спорных местах</h2>` — `<ul class="lead">` с пунктами вида
   `<b>Заголовок.</b> Обоснование`. Один пункт обязателен: **что уступает при
   нехватке места**.
4. `<h2>Чего нет на макете</h2>` — что сознательно не нарисовано и почему.
5. Замеченный существующий баг помечается: «не часть этой задачи — показано,
   чтобы не было сюрпризом».

Рамка телефона (из `home-menu.html:161-171`):

```css
.mk { max-width: 1440px; margin: 0 auto; padding: 24px; }
.cols { display: grid; grid-template-columns: repeat(auto-fit, minmax(340px, 1fr)); gap: 24px; }
.dev.phone { width: 410px; height: 864px; border: 10px solid #0d0d12; border-radius: 54px; overflow: hidden; position: relative; --safe-top: 47px; --safe-bottom: 34px; background: var(--bg); }
.fw { width: 328px; height: 691px; }      .fw .phone { transform: scale(0.8); transform-origin: top left; }
.fw.sm { width: 246px; height: 519px; }   .fw.sm .phone { transform: scale(0.6); }
```

Данные на макете — правдоподобные, но выдуманные; темы и слова берутся из
`content/topics/*.yaml`, а не придумываются. Эмодзи — инлайн-символ в
`<span class="emoji" role="img" aria-hidden="true">🍎</span>`; приложение
рисует их из Twemoji, макет — системным шрифтом, и это допустимая разница.
Картинки как `data:` — только когда макет и есть сверка картинок.

### Только изменяемая часть

Общее правило объёма макета — в агенте `designer` (`~/.claude/agents/designer.md`); здесь — как это выглядит в Мзико. Остальной экран — рамка-контекст, а не копия приложения:

```css
.ctx { background: var(--line); opacity: .55; border-radius: 16px; min-height: 48px;
       display: grid; place-items: center; color: var(--muted); font-size: 13px; }
```

Блок `.ctx` подписывается тем, что он замещает: «шапка — как сейчас»,
«список уроков — как сейчас». Шапка, меню, холмы и соседние карточки, которые
задача не трогает, остаются такими блоками.
