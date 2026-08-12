# Branding & Design System Guide

> **Purpose:** A portable design language extracted from **Music Studio**, so a *different*
> application can adopt the same look and feel. Hand this file to a new session as the single
> source of truth. Nothing here is app-specific — it's tokens, rules, and component recipes.

**Identity in one line:** a **"studio console after dark"** — a committed, single dark theme with
an amber tube-glow accent, calm slate surfaces, tabular-numeric readouts, and pill/chip controls.

---

## 1. Design principles

1. **One committed dark theme.** No light mode. The mood is a piece of pro audio/console gear at
   night — dark slate, warm amber glow. Don't add a light variant unless explicitly asked.
2. **Warm accent, cool neutrals.** A single amber accent does the emotional work against
   blue-grey slate surfaces. A restrained teal is the *only* secondary accent (links, "loading",
   subtle highlights) — never a third bright color competing with amber.
3. **Layered surfaces, not borders alone.** Depth comes from 4 stacked surface shades plus hairline
   borders — soft radial glows in the page background, never heavy drop-shadows.
4. **Readouts feel like instruments.** Anything numeric (costs, balances, durations, meta) uses the
   monospace font with `font-variant-numeric: tabular-nums`.
5. **Restraint.** Rounded corners, hairline borders, fast (~120ms) transitions, tiny translate on
   press. No bounce, no large shadows, no gradients except the primary button and background glow.
6. **Accessible & calm.** Visible focus rings, `prefers-reduced-motion` honored, uppercase micro-
   labels for structure.

---

## 2. Color tokens

Drop these into `:root`. Names are intentionally generic/reusable.

```css
:root {
  /* Backgrounds & surfaces (darkest → lightest) */
  --bg:            #0d0e12;   /* page base */
  --surface:       #15161d;   /* primary panel */
  --surface-2:     #1c1e27;   /* nested/section surface */
  --surface-3:     #242732;   /* raised controls (secondary buttons) */

  /* Borders */
  --border:        #2a2d38;   /* hairline default */
  --border-strong: #3a3e4c;   /* hover / open / emphasis */

  /* Text (high → low emphasis) */
  --text:  #ecedf2;           /* primary */
  --muted: #969cae;           /* secondary / labels */
  --faint: #686e7e;           /* placeholders / notes */

  /* Accent — amber "tube glow" (primary brand color) */
  --accent:        #e8a24a;
  --accent-strong: #d5872f;             /* pressed / gradient end */
  --accent-soft:   rgba(232,162,74,0.13); /* tint fills, focus ring glow */
  --accent-ink:    #1c1408;             /* text ON amber (near-black brown) */

  /* Secondary accent — restrained teal (links, loading, subtle marks) */
  --accent-2: #4fc8bd;

  /* Status */
  --success: #63d68f;   /* green */
  --warn:    #f2c14e;   /* yellow */
  --danger:  #ff6f6f;   /* red */
}
```

### Status colors use a consistent tinted-pill pattern

Each state = colored text + 30–40% alpha border + ~8–10% alpha background fill of the same hue:

```css
/* success */ color:var(--success); border-color:rgba(99,214,143,.30); background:rgba(99,214,143,.08);
/* warn    */ color:var(--warn);    border-color:rgba(242,193,78,.35); background:rgba(242,193,78,.08);
/* danger  */ color:var(--danger);  border-color:rgba(255,111,111,.40); background:rgba(255,111,111,.10);
```

### Usage rules
- **Amber** = brand + primary action + active/selected state + focus. Use it *sparingly* so it
  stays a highlight; large amber areas only for the primary button.
- **Teal (`--accent-2`)** = hyperlinks, "loading" status text, and a few small interactive accents.
  Never use it as a second primary button.
- **Never** put text directly on amber except `--accent-ink`.

---

## 3. Typography

```css
:root {
  --sans: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  --mono: ui-monospace, "Cascadia Code", "SF Mono", "JetBrains Mono", Menlo, Consolas, monospace;
}
```

- **No web fonts.** System UI stack only — fast, zero network, native on every OS. Keep it that way
  unless a brand font is explicitly requested.
- **Monospace** for all numeric readouts, code/prompt boxes, and metadata.

### Type scale & weights (as used)

| Role | Size | Weight | Notes |
| --- | --- | --- | --- |
| App title (h1) | 18px | 650 | `letter-spacing:-0.01em`, icon in accent |
| Section title | 14px | 700 | UPPERCASE, `letter-spacing:0.08em` |
| Micro-label / group head | 12px | 700 | UPPERCASE, `letter-spacing:0.09em`, muted → accent when active |
| Label / legend | 12.5px | 600 | `--text` |
| Body / input text | 13–13.5px | 400–500 | |
| Hint / meta | 11.5px | 400 | `--muted` / `--faint`, often mono |
| Badge / version | 11px | 600 | pill, accent tint |

**Convention:** structural labels are **UPPERCASE + wide letter-spacing + muted**; they turn
**amber** when their section is active/open.

---

## 4. Shape, spacing & motion

```css
:root {
  --radius:    14px;  /* panels, cards */
  --radius-sm:  9px;  /* nested groups, inputs-as-blocks */
  --gap:       16px;  /* base layout gap */
}
```

- **Radii:** 14px panels · 9px nested/buttons · 8px inputs · `999px` pills/chips.
- **Borders:** always 1px. `--border` at rest, `--border-strong` on hover/open.
- **Layout width:** centered, `max-width: 1100px`, `margin: 0 auto`, padding `var(--gap)`.
- **Transitions:** fast and subtle — `0.12s` for color/border/filter, `0.18s` for rotations.
  Buttons press with `transform: translateY(1px)` on `:active`.
- **Focus ring:** `border-color: var(--accent)` + `box-shadow: 0 0 0 3px var(--accent-soft)`.
- **Reduced motion:** always include the `prefers-reduced-motion` reset (see §8).

### Page background (signature detail)
Two soft radial glows over the base color — subtle warmth top-corners, never a flat fill:

```css
body {
  background:
    radial-gradient(1100px 500px at 12% -12%, #1a1c27 0%, transparent 60%),
    radial-gradient(900px 480px at 100% -6%, #171a24 0%, transparent 55%),
    var(--bg);
}
```

---

## 5. Iconography

- **Library:** [Lucide](https://lucide.dev) icons, **inlined as SVG paths** (no icon-font, no
  runtime dependency). Copy only the inner paths into a small map and wrap them.
- **Standard wrapper** — 24×24 viewBox, `currentColor` stroke so icons inherit text color:

```js
function icon(name, size = 16) {
  return `<svg class="ic" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" ` +
    `stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" ` +
    `aria-hidden="true">${ICONS[name] || ""}</svg>`;
}
```

- **Rules:** stroke style only (never filled), `stroke-width:2`, round caps/joins, `size` 16 default
  / 20 for the title. Icons take the accent color in the title and headings, otherwise inherit.
- **Favicon:** an inline SVG data-URI using the amber accent (`stroke='%23e8a24a'`).

---

## 6. Component recipes

### Panel / card
```css
.panel { background:var(--surface); border:1px solid var(--border); border-radius:var(--radius); }
```

### Buttons
```css
.btn {
  border:1px solid var(--border); background:var(--surface-3); color:var(--text);
  padding:10px 16px; border-radius:9px; font-size:13.5px; font-weight:600; cursor:pointer;
  display:inline-flex; align-items:center; justify-content:center; gap:7px;
  transition:filter .12s, transform .04s, border-color .12s;
}
.btn:hover { filter:brightness(1.15); border-color:var(--border-strong); }
.btn:active { transform:translateY(1px); }
.btn:focus-visible { outline:2px solid var(--accent); outline-offset:2px; }
.btn.primary {                       /* the ONE amber gradient in the UI */
  background:linear-gradient(180deg, #f2b062, var(--accent-strong));
  border-color:transparent; color:var(--accent-ink); font-weight:700;
}
.btn.ghost  { background:var(--surface-3); }
.btn.small  { padding:7px 12px; font-size:12.5px; }
.btn.danger { color:var(--danger); }
.btn:disabled { opacity:.5; cursor:not-allowed; filter:none; }
```

### Pills / chips (selectable tags — the signature control)
```css
.chip {
  border:1px solid var(--border); background:var(--bg); color:var(--muted);
  border-radius:999px; padding:6px 12px; font-size:12.5px; cursor:pointer;
  user-select:none; transition:all .12s ease;
}
.chip:hover  { border-color:var(--accent); color:var(--text); }
.chip.active { background:var(--accent); border-color:var(--accent); color:var(--accent-ink);
               font-weight:600; box-shadow:0 0 0 3px var(--accent-soft); }
.chip.disabled { opacity:.32; cursor:not-allowed; }
.chip.exp { border-style:dashed; }        /* "experimental/provisional" variant */
.chip.exp.active { border-style:solid; }
```

### Status pill (balance / key status)
Green by default, amber `.low`, red `.critical` — see §2 tinted-pill pattern. `border-radius:999px`,
`font-variant-numeric:tabular-nums` for numbers.

### Inputs
```css
input, select, textarea {
  background:var(--bg); border:1px solid var(--border); color:var(--text);
  border-radius:8px; padding:9px 11px; font-size:13.5px; font-family:inherit; width:100%;
  transition:border-color .12s, box-shadow .12s;
}
input:focus, select:focus, textarea:focus {
  outline:none; border-color:var(--accent); box-shadow:0 0 0 3px var(--accent-soft);
}
input::placeholder { color:var(--faint); }
:where(input[type=checkbox]) { accent-color:var(--accent); }
```

### Collapsible section (`<details>`-based group)
- Container: `--surface-2`, `--radius-sm`, 1px border → `--border-strong` when `[open]`.
- Header: UPPERCASE muted title that turns **amber** when open; custom chevron (a rotated
  border-box) instead of the default marker; optional muted sub-label on the right.

### Sticky top bar
Translucent + blurred: `background:rgba(13,14,18,.82); backdrop-filter:blur(10px);` sticky top,
1px bottom border. Title left (icon in accent + optional version pill), status pills right.

### Sticky action bar (primary CTA footer)
Sticks to bottom of a form with a gradient fade into the surface and `backdrop-filter:blur(8px)`;
buttons `flex:1`.

### Loading spinner
```css
.spinner { width:14px; height:14px; border:2px solid rgba(255,255,255,.22);
  border-top-color:var(--accent-2); border-radius:50%; animation:spin .8s linear infinite; }
@keyframes spin { to { transform:rotate(360deg); } }
```

---

## 7. Responsive

- Single centered column, `max-width:1100px`.
- Two-column rows (`.row`, `grid-template-columns:1fr 1fr`) collapse to one column at
  `max-width:560px`. Three-column at the same breakpoint.
- Hide secondary sub-labels on narrow screens rather than wrapping.

---

## 8. Global boilerplate to carry over

```css
* { box-sizing: border-box; }
[hidden] { display: none !important; }   /* wins over any display:flex/grid utility */
body { -webkit-font-smoothing: antialiased; }

@media (prefers-reduced-motion: reduce) {
  * { animation-duration:.001ms !important; transition-duration:.001ms !important; }
}
```

---

## 9. Quick "do / don't"

**Do:** dark slate surfaces layered by lightness · amber for actions & active state · teal only for
links/loading · pills for choices · mono + tabular-nums for any number · UPPERCASE muted micro-
labels · hairline borders · fast subtle transitions · visible focus rings.

**Don't:** add a light theme · introduce a third bright hue · use filled icons or an icon font ·
add web fonts · use heavy drop-shadows or large radii · put plain text on amber · animate big/bouncy.

---

## 10. Fastest path to reuse

1. Copy the `:root` block from **§2 + §3 + §4** into the new project's stylesheet.
2. Copy the global boilerplate (**§8**).
3. Copy the component recipes you need from **§6** (buttons, chips, inputs, panel are the core).
4. Copy the `icon()` helper (**§5**) and pull whatever [Lucide](https://lucide.dev) glyphs you need.
5. Keep the principles in **§1** and the do/don't in **§9** in front of you while building.

*Extracted from Music Studio's `public/styles.css`, `index.html`, and `app.js`.*
