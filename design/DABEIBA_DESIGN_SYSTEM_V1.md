# DABEIBA Design System V1

**Purpose:** Locked visual design tokens for all client-facing deliverables. Anthropic-inspired aesthetic — warm neutral palette, restrained typography, generous whitespace, plain English. This file is the single source of truth; deliverables reference these tokens, never invent their own.

**Version:** v1.0 — locked 2026-05-05
**Reference style:** warm minimalism (Claude / Linear / Stripe Press / NYT Magazine longform)

---

## 1. Color tokens (locked — aligned to `dashboards/equity-valuation-eval-review.html` palette already in production)

```
/* Backgrounds */
--bg:              #faf9f5   /* page background, warm cream */
--bg-soft:         #f5f3ed   /* alternate background, slightly darker */
--surface:         #ffffff   /* cards, surfaces */
--bg-subtle:       #efeee6   /* subtle highlight, hover state */

/* Text */
--text:            #141413   /* main copy, warm near-black */
--text-muted:      #b0aea5   /* meta, captions, supporting */
--text-ghost:      #d4d2c8   /* timestamps, ghost text, dividers */

/* Accent */
--accent:          #d97757   /* coral / burnt orange — primary highlight */
--accent-hover:    #c4613f   /* hover / pressed state */
--accent-soft:     #f4e0d6   /* light tint, for backgrounds */
--accent-deep:     #8a3d20   /* dark tint, for text on accent backgrounds */

/* Semantic */
--green:           #788c5d   /* success, positive */
--green-bg:        #eef2e8   /* success card background */
--red:             #b85650   /* danger, negative */
--red-bg:          #fceaea   /* danger card background */
--amber:           #b8862b   /* warning */
--amber-bg:        #f7efd9   /* warning card background */
--info:            #3b5a6b   /* info / neutral muted teal */

/* Inverse (for header bands, dark callouts) */
--header-bg:       #141413   /* dark band */
--header-text:     #faf9f5   /* on dark band */

/* Lines */
--border:          #e8e6dc   /* warm light gray for dividers, table cells */
--border-strong:   #cfccc0   /* stronger separator */

/* Shadow */
--shadow-card:     0 1px 2px rgba(20, 20, 19, 0.04), 0 4px 12px rgba(20, 20, 19, 0.03);
```

**Why these exact values:** matches `dashboards/equity-valuation-eval-review.html` already in production. Single palette across all HTML deliverables.

**Rule:** never use pure `#FFFFFF` text on `#000000` background or vice versa. Warm tints only — keeps the page feeling like paper, not a screen.

**Single-accent rule:** one element per section can be in `--accent-primary`. Restraint is the look.

---

## 2. Typography

**All fonts are free Google Fonts. No commercial fonts. No licensing required.**

```
/* Font stacks */
--font-serif:      "Playfair Display", "Georgia", serif;                              /* Google Fonts */
--font-sans:       "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; /* Google Fonts */
--font-mono:       "JetBrains Mono", "SF Mono", "Consolas", monospace;                /* Google Fonts */

/* Type scale (modular, ratio 1.25, base 16px) */
--text-xs:    12px;  --leading-xs:  16px;
--text-sm:    14px;  --leading-sm:  20px;
--text-base:  16px;  --leading-base: 24px;
--text-lg:    20px;  --leading-lg:  28px;
--text-xl:    25px;  --leading-xl:  32px;
--text-2xl:   31px;  --leading-2xl: 40px;
--text-3xl:   39px;  --leading-3xl: 48px;
--text-4xl:   49px;  --leading-4xl: 56px;
```

**Pairing rules:**
- **Headlines / titles:** serif, sizes ≥ `--text-xl`, weight 400 (don't bold serif headlines — let size carry)
- **Body / UI:** sans, `--text-base`, weight 400
- **Numerals in data tables / metrics:** mono, tabular figures
- **Captions / meta:** sans, `--text-sm`, `--text-secondary` color
- **Code / tickers / prices:** mono inline

**Letter-spacing:**
- Headlines: `-0.02em` (slight negative, tightens serif)
- All-caps eyebrow labels: `+0.06em` (slight positive)
- Body: `0`

---

## 3. Spacing (4px base unit)

```
--space-1:   4px;
--space-2:   8px;
--space-3:   12px;
--space-4:   16px;
--space-6:   24px;
--space-8:   32px;
--space-12:  48px;
--space-16:  64px;
--space-24:  96px;
--space-32:  128px;
```

**Section-rhythm rules:**
- Vertical space between major sections: `--space-12` (48px) minimum
- Card-internal padding: `--space-6` (24px)
- Inline gap between related items: `--space-3` or `--space-4`
- Page horizontal margin: `--space-12` (desktop), `--space-6` (mobile)

---

## 4. Other tokens

```
/* Radius */
--radius-sm:   4px;    /* tags, pills */
--radius-md:   8px;    /* buttons, inputs */
--radius-lg:   12px;   /* cards */
--radius-xl:   16px;   /* containers */

/* Max widths */
--width-prose:    640px;   /* longform reading */
--width-content:  920px;   /* dashboards, briefs */
--width-wide:     1200px;  /* full reports */
```

---

## 5. Component patterns

### 5.1 Section header
```html
<header class="section-header">
  <p class="eyebrow">REGIME</p>
  <h2 class="title">Bull · Low Vol · Easing</h2>
  <p class="subtitle">As of week ending May 9, 2026</p>
</header>
```
- `.eyebrow`: sans, `--text-xs`, all-caps, `--accent-primary` color, letter-spacing `+0.06em`
- `.title`: serif, `--text-2xl`, weight 400, `--text-primary`
- `.subtitle`: sans, `--text-sm`, `--text-secondary`

### 5.2 Stat block
```html
<div class="stat">
  <p class="stat-value">68.7%</p>
  <p class="stat-label">In-sample precision</p>
  <p class="stat-caption">May 2024 – Aug 2025 · 33,537 signals</p>
</div>
```
- `.stat-value`: mono, `--text-3xl`, weight 500, tabular figures, `--text-primary`
- `.stat-label`: sans, `--text-base`, `--text-primary`
- `.stat-caption`: sans, `--text-sm`, `--text-secondary`

### 5.3 Evidence card
```html
<article class="evidence-card">
  <header class="evidence-header">
    <span class="evidence-tag">Thesis</span>
    <time class="evidence-date">May 7, 2026</time>
  </header>
  <p class="evidence-body">Quote or claim text here, in serif for prose feel.</p>
  <footer class="evidence-source">— Source: 10-K, p.43</footer>
</article>
```
- Background `--bg-surface`, padding `--space-6`, radius `--radius-lg`, shadow `--shadow-card`
- Left border 3px solid `--accent-primary`
- Body text: serif, `--text-base`, leading 1.6
- Source: sans, `--text-sm`, `--text-tertiary`

### 5.4 Data table
- Background `--bg-surface`, full-width, border-collapse
- Header row: `--text-xs` sans all-caps, `--text-secondary`, padding `--space-3 --space-4`
- Body cells: `--text-sm` sans (prose) / mono (numerals), padding `--space-3 --space-4`
- Numeric columns right-aligned, mono, tabular figures
- Borders: only horizontal, `--border` color, no vertical lines
- Zebra: even rows `--bg-cream-soft`

### 5.5 Inline tag (priority pill)
```html
<span class="tag tag-p1">P1</span>
```
- Padding `--space-1 --space-3`, radius `--radius-sm`, `--text-xs` sans
- P1: `--bg-subtle` bg, `--accent-deep` text
- P2: `--bg-cream-soft` bg, `--text-primary` text
- P3: transparent bg, `--border` 1px, `--text-secondary` text
- HORIZON tactical/thematic/structural: ghost variants in `--info` / `--warning` / `--success` low opacity

### 5.6 Callout box
- Left border 3px in semantic color (`--success` / `--warning` / `--danger` / `--info`)
- Background tinted 4% of that color
- Padding `--space-4 --space-6`
- Body sans `--text-sm`

---

## 6. Layout principles

1. **One column, never two.** Briefs are read top-to-bottom. Resist the urge to put data side-by-side unless it's a comparison table.
2. **Whitespace is content.** Don't fill empty space. Section breaks should breathe.
3. **One accent per section.** Use `--accent-primary` for the single most important element on each section. More than one and it stops being a hierarchy.
4. **Type does the lifting.** Headers / size / weight establish hierarchy — not boxes, not borders, not color changes.
5. **Mono for numbers, serif for prose, sans for UI.** This triad keeps the page legible and credible.
6. **No decorative graphics.** No gradients, no illustrations, no stock-photo header images. The closest to "graphic" you go is a single thin rule-line or accent stripe.

---

## 7. Hard constraints (carried from existing DABEIBA rules)

- Zero internal codenames in any client-facing surface (`feedback-no-internal-codenames-in-client-deliverables`)
- Zero emojis (`feedback-no-emojis-ever`) — use semantic tags + geometric symbols (· — → ↑ ↓) instead
- Acronyms spelled out on first use (`feedback-no-acronyms`)
- Evidence cited (every claim links to source)
- Accessibility: WCAG AA contrast on all text (verify with a checker tool — the warm palette is close to threshold in places)

---

## 8. Asset list (HTML/CSS implementations)

When this design system is applied to a deliverable, the implementer creates:
- `design/dabeiba.css` — the locked token + base + component styles, single file
- `design/dabeiba.fonts.css` — `@font-face` declarations or Google Fonts imports (free fallbacks: Playfair Display + Inter + JetBrains Mono)
- One example HTML per template type (brief / dashboard / report) at `design/templates/`

These assets are reusable across deliverables. The weekly brief, RAPTOR client docs, and any future client surface link to the same `dabeiba.css`.

---

## 9. What this is NOT

- Not a copy of Anthropic's Claude visual identity. It's an *aesthetic family* — warm neutrals, restrained type, plain English — that's been a recognizable design tradition long before Claude (NYT, Stripe Press, Apple's HI guidelines, longform-magazine print). Original token values, original asset names.
- Not a brand identity. DABEIBA has no public brand; this is purely a visual design system for client-facing artifacts.
- Not a CSS framework. It's tokens + components, locked and minimal.
