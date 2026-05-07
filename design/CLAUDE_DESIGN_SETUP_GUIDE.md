# Claude Design — DABEIBA Setup Guide

**Purpose:** end-to-end walkthrough for setting up the DABEIBA design systems inside `claude.ai/design`, then generating prototypes from them. No coding skills needed.

**Two systems to register:**
1. **DABEIBA Web v1** — for HTML dashboards, weekly briefs, lead briefs, RAPTOR client docs
2. **DABEIBA Decks v1** — for equity valuation PPTX presentations

Do them in that order. Web first (simpler, used more often).

---

## PART 1 — Set up "DABEIBA Web v1"

You're on the **Set up your design system** page right now. Walk through it field-by-field.

### Field 1: Company name and blurb

You typed `DABEIBA Web v1`. Replace it with this expanded version (copy-paste):

```
DABEIBA Web v1 — Internal design system for client-facing HTML deliverables (weekly intelligence briefs, lead dossiers, dashboards, research one-pagers). Aesthetic: warm minimalism. Editorial / longform-magazine feel. Restrained type, generous whitespace, single accent color per section.
```

### Field 2: Provide examples (all optional — but use these)

You have 4 sub-options. Here's what to do with each:

#### A. Link code on GitHub

**Skip.** Your repo isn't public, and the design system tokens are already captured in the notes field below. Leave blank.

#### B. Link code from your computer (requires Chrome or Edge)

**Use this one.** This uploads selected files so Claude Design can read your existing palette.

1. Click "Link code from your computer"
2. Browser asks for folder access. Point it at: `~/Desktop/DABEIBA/dashboards/`
3. Select these specific files (do NOT upload the whole folder):
   - `equity-valuation-eval-review.html` ← the canonical palette + components
4. Confirm

This gives Claude Design a real reference for what "good" looks like in your house style.

#### C. Upload a .fig file

**Skip.** You don't have a Figma file. Leave blank.

#### D. Add fonts, logos and assets

**Skip for v1.** The fonts (Playfair Display + Inter + JetBrains Mono) are loaded from Google Fonts at runtime — no upload needed. No DABEIBA logo exists publicly, so no logo to add.

### Field 3: Any other notes?

**This is the most important field.** Paste this whole block (between the `===` lines):

```
===
DABEIBA WEB v1 — DESIGN SYSTEM RULES

PALETTE (locked — match exactly):
- bg: #faf9f5 (warm cream — page background)
- bg-soft: #f5f3ed (alt background)
- surface: #ffffff (cards)
- text: #141413 (warm near-black, main copy)
- text-muted: #b0aea5 (meta, captions)
- text-ghost: #d4d2c8 (timestamps, dividers)
- accent: #d97757 (coral — primary highlight, ONE per section)
- accent-hover: #c4613f
- green: #788c5d / green-bg: #eef2e8 (positive)
- red: #b85650 / red-bg: #fceaea (negative)
- amber: #b8862b / amber-bg: #f7efd9 (warning)
- info: #3b5a6b (neutral teal)
- header-bg: #141413 / header-text: #faf9f5 (dark inverse band)
- border: #e8e6dc / border-strong: #cfccc0

TYPOGRAPHY:
- Serif (headlines, titles, evidence card body): Playfair Display, Georgia, serif. Weight 400. Letter-spacing -0.02em.
- Sans (body, UI, labels): Inter, -apple-system, sans-serif. Weight 400 / 500.
- Mono (numbers, tickers, prices, code): JetBrains Mono, SF Mono, monospace. Tabular figures.
- Type scale (modular ratio 1.25, base 16): 12 / 14 / 16 / 20 / 25 / 31 / 39 / 49 px

SPACING (4px base):
4 / 8 / 12 / 16 / 24 / 32 / 48 / 64 / 96 px
- Section vertical rhythm: ≥48px between sections
- Card internal padding: 24px
- Page horizontal margin: 48px desktop, 24px mobile

RADIUS:
4 (tags) / 8 (buttons) / 12 (cards) / 16 (containers)

LAYOUT:
- Single column, never two. Comparison tables only when explicitly comparing.
- Max widths: 640px prose, 920px content/dashboards, 1200px wide reports
- One accent color per section. Restraint is the look.
- No gradients, no illustrations, no decorative icons, no stock photos. Type does the lifting.

COMPONENTS (build these as reusable patterns):
- Section header: eyebrow (12px sans all-caps, accent color, +0.06em tracking) + title (serif, 31px, weight 400) + subtitle (14px sans, text-muted)
- Stat block: large mono number (39px, weight 500) + label (16px sans) + caption (14px sans muted)
- Evidence card: surface bg, 24px padding, 12px radius, subtle shadow, 3px left border in accent color, serif body, sans source-cite footer
- Data table: surface bg, horizontal-only borders, header row in 12px sans all-caps muted, body cells 14px (sans for prose, mono for numbers), zebra-stripe even rows in bg-soft, numeric columns right-aligned tabular figures
- Inline tag (priority pill): 4px radius, 12px sans, padding 4px 12px, semantic color variants (P1=accent-soft bg / accent-deep text; P2=bg-soft bg; P3=transparent bg with border)
- Callout box: 3px left border in semantic color (success/warning/danger/info), 4% tint of that color as background, 16px / 24px padding, 14px sans body
- Footer evidence cite block: 12px sans muted, italic, list of sources with dates

VOICE & WRITING:
- Plain English. Acronyms spelled out on first use.
- Evidence cited (every claim has a source link or footnote).
- No emojis anywhere.
- No internal codenames in client-facing artifacts (the words DABEIBA, ORACLE, SOMA, MANTIS, CIPHER, RAPTOR, TITAN, COBALT, SPECTRE, DOCTRINE, PRISM, MUSKONOMY, BEACON, FORGE, VECTOR, SENTINEL, DOSSIER must NEVER appear in any output).
- Substitutes: "in-house ranking" / "internal quality screen" / "proprietary research" / "internal database" / "intelligence platform"
- Data over prose. Numbers > paragraphs.

ACCESSIBILITY:
- WCAG AA contrast on all text (4.5:1 body, 3:1 for ≥18pt)
- Verify text-muted (#b0aea5) on bg (#faf9f5) — borderline; only use for non-essential meta text

WHAT THIS DESIGN IS NOT:
- Not Anthropic Claude branding. Original tokens, original asset names, this is DABEIBA's internal house style.
- Not a brand identity (no logo, no marks, no public-facing brand).
- Not a CSS framework. Tokens + components only.

REFERENCE: dashboards/equity-valuation-eval-review.html (in production, matches this palette exactly).
===
```

### Continue to generation

Click the orange "Continue to generation" button (top-right).

You'll land on a new page where you can describe what you want generated. **Don't generate anything yet — register the second design system first.**

---

## PART 2 — Set up "DABEIBA Decks v1"

Go back to the design systems list (click `← Back` then "Design systems" tab) and click **Set up design system** again.

### Field 1: Company name and blurb

```
DABEIBA Decks v1 — Internal design system for client presentation slides (PowerPoint .pptx). Audience: investment professionals, prospects, RBC. Aesthetic: Midnight Executive. Dark navy + gold, formal investment-bank tone. Print/projector quality.
```

### Field 2: Provide examples

#### A. Link code on GitHub
**Skip.**

#### B. Link code from your computer
**Use it.** Point at `~/Desktop/DABEIBA/skills/equity-valuation/` and select:
- `SKILL.md` (the locked deck rules)

#### C. Upload a .fig file
**Skip.**

#### D. Add fonts, logos and assets
**Skip.** Georgia and Calibri are system fonts — no upload needed.

### Field 3: Any other notes?

Paste this block:

```
===
DABEIBA DECKS v1 — DESIGN SYSTEM RULES (PPTX presentations)

PALETTE — Midnight Executive (locked per equity-valuation skill HG-1):
- Primary navy: #1A2744 (slide backgrounds, dark bands, headers)
- Accent gold: #D4AF37 (highlights, callout numbers, single-element-per-slide)
- Off-white: #F5F1E8 (light slide backgrounds, when used)
- Charcoal: #1A1A1A (body text on light, formula cells)
- Dim gray: #6B6660 (secondary text)
- Success green: #2D5F3F
- Danger red: #8B2E2E

FAST color coding (financial models — for cross-skill consistency):
- Inputs: #0000FF (blue)
- Formulas: #1A1A1A (black)
- Cross-references: #008000 (green)

TYPOGRAPHY:
- Headlines / titles: Georgia, weight bold, all-caps for slide titles, sentence-case for sub-titles
- Body / labels: Calibri, weight regular for body, weight bold for emphasis
- Numbers / tables: Calibri tabular figures, right-aligned in cells
- Type scale (pt): body 12 / sub-body 11 / footnote 9 / metric callout 32-44 / slide title 28 / section banner 36

SLIDE LAYOUT:
- 16:9 aspect ratio
- Margins: 0.5" all sides
- Title bar: top 1", dark navy bg with off-white text, gold accent rule
- Footer: bottom 0.4", page number + ticker + date stamp + "INTERNAL — DO NOT DISTRIBUTE" line
- Content: between, never crowded

LOCKED OPENING SEQUENCE (per equity-valuation skill HG-1):
- Slide 1: Title (ticker, company, date, analyst)
- Slide 2: Mission, Vision, Strategic Direction
- Slide 3: Business Lines & Development Roadmap (with timelines)
- Slide 4: Profitability, Growth & TAM by Business Line (with sources)
- Slide 5: Demonstrated Execution Capacity (chronological track record)
- Slide 6: Internal Valuation Cross-Check (uses neutral language, never "Oracle" by name)
- Slide 7: Executive Summary
- Then standard valuation flow

LAYOUT PATTERNS:
- Stat callouts: 32-44pt gold number, 12pt label below in off-white
- Tables: dark navy header row (off-white text), alternating row tint #1A2744 vs #243959, 11pt Calibri
- Waterfall chart: separate negative-bar labels (inside bar) from positive-bar labels (above bar) — never overlap category axis (per L14 lesson)
- Scenario contribution bars: equal-width grouped cards, never proportional widths (per L13 lesson)
- Roadmap items: explicit dates (YYYY-MM-DD or Qx YYYY) on every forward commitment

VOICE & WRITING:
- Investment-bank formal tone
- Acronyms spelled out on first use (FOMC, CPI, GDP, etc.)
- Specific dates and timelines on every catalyst, milestone, and roadmap item
- No internal codenames (NEVER: DABEIBA, ORACLE, SOMA, MANTIS, CIPHER, RAPTOR, TITAN, COBALT, SPECTRE, MUSKONOMY, PRISM, etc.)
- Substitutes: "in-house ranking", "internal quality screen", "proprietary research"
- No emojis. Geometric symbols only (· — → ↑ ↓ ⚪ ⬛)

VISUAL QA GATE (before declaring deck audited):
- Convert .pptx to PDF via libreoffice headless
- Inspect all chart slides, all tables >5 rows, all stacked text columns, the SOTP waterfall, sensitivity tables
- Run XML codename scrub on the .pptx file (extract XML, grep for codename list)
- Verify no thumbnail-visible formatting bugs

REFERENCE: skills/equity-valuation/SKILL.md (the locked HG rules — HG-0 codenames, HG-1 opening sequence, etc.)
===
```

Click **Continue to generation**.

---

## PART 3 — Generate your first prototype

Now you have both systems registered. Go to the main Claude Design page → click **New prototype** → **High fidelity** → name: `Weekly Intelligence Brief — Test 1`.

In the prompt field, paste this:

```
Generate a single-page HTML weekly intelligence brief for institutional investors. 
Use the DABEIBA Web v1 design system.

Sections (in order):

1. HEADER — eyebrow "WEEK ENDING MAY 9, 2026", title "Intelligence Brief — Equities & Macro", subtitle "Internal research summary"

2. REGIME — stat block with current regime label "Bull · Low Vol · Easing", change-vs-last-week "(unchanged)" subtitle, caption "Composite 13-series classification"

3. TOP 5 SIGNALS THIS WEEK — data table with columns: Ticker | Signal Type | Horizon | Score | Date. 
Five rows of plausible institutional-grade examples (NVDA, PLTR, TSM, COIN, ASML). 
Use horizon tags: tactical (info color), thematic (amber color), structural (green color).

4. NEW THESES — three evidence cards. Each has:
- A "Thesis" tag (top-left)
- A date (top-right)
- A short serif-prose claim (e.g. "Robotaxi commercialization timeline pulled forward by 9 months following Q1 fleet expansion data")
- A source citation footer (e.g. "— Q1 earnings call transcript, Section 4")

5. CONVERGENCE MOVERS — small data table: Company | Platforms | Convergence Score Δ vs last week. 
Three rows.

6. STRUCTURAL WATCH — bullet list of three items, each as a mini evidence card with a callout color (info / amber / green based on regime band)

FOOTER — small muted text, generated timestamp, "Internal research — for decision-making support".

Constraints:
- One column layout, max-width 920px
- Single accent color per section (use the coral #d97757 sparingly — only the eyebrow + one stat number)
- No emojis, no decorative icons, no gradients
- No internal codenames anywhere (avoid the words DABEIBA, ORACLE, SOMA, MANTIS, CIPHER, RAPTOR, etc.)
- Plain English, acronyms spelled out
- Mono font for all numerical values (prices, scores, percentages)
- Serif font for headlines and evidence-card body text
- WCAG AA contrast throughout
```

Click **Create**.

Claude Design generates a prototype. Iterate by typing follow-ups in the same chat:
- *"The stat block feels too small — make the regime label 49px"*
- *"Tighten the table — reduce row padding by 4px"*
- *"The evidence cards need more breathing room between them"*
- *"Move the eyebrow above the title, smaller, all-caps"*

When you're happy with the look, click **Export** (or copy the HTML).

---

## PART 4 — Hand the result to Sonnet

Once Claude Design produces an HTML mockup you like, you don't write code yourself. Give it to Sonnet:

1. Save the exported HTML somewhere local (e.g. `~/Desktop/weekly_brief_mockup.html`)
2. Open a fresh Sonnet chat
3. Paste this:

```
I've created an HTML mockup for the weekly intelligence brief in Claude Design. 
The file is at ~/Desktop/weekly_brief_mockup.html.

Read tasks/SOMA_INTEL_RESUME_WEEKLY_BRIEF_DESIGN.md for full context.

I want you to:
1. Extract the CSS from my mockup → save as ~/Desktop/DABEIBA/shared/design/dabeiba.css
2. Update shared/soma/intel/weekly_brief.py so it generates HTML using this exact styling
3. Inline the CSS for emailability (--inline-css flag default true)
4. Run the generator and save the new output to cipher/outputs/
5. Take a screenshot of the result and ping me with it

Follow the design tokens exactly. Don't deviate. Surface to me if anything's unclear.
```

4. Sonnet does the wiring. Reviews come back with screenshots.
5. If approved, ship.

---

## PART 5 — RAPTOR Lead Brief (next deliverable)

After the weekly brief is live, repeat the workflow for RAPTOR's lead brief. Same DABEIBA Web v1 system; different content sections.

In Claude Design → New prototype → High fidelity → name: `RAPTOR Lead Brief — Test 1`.

Prompt:

```
Generate a single-page HTML lead brief for an institutional sales prospecting workflow.
Use the DABEIBA Web v1 design system.

Sections (in order):

1. HEADER — eyebrow "PROSPECT DOSSIER", title "[Company Name]", subtitle "[industry] · [geography] · [employee count] employees"

2. SCORE BLOCK — one large stat card with:
- Primary number: overall lead score (e.g. "82") in mono 49pt
- Three sub-scores below: Fit / Intent / Capacity, each with a smaller mono number and label

3. WHY THIS PROSPECT — three evidence cards, each with:
- Tag "Reason" (top-left)
- Short serif claim ("Recently expanded into APAC, signals capacity for new advisor relationships")
- Citation footer ("— company press release, 2026-04-15")

4. DECISION-MAKER MAP — data table: Name | Role | Background | Last Touchpoint. Five rows.

5. RECOMMENDED APPROACH — short prose paragraph followed by 3 bullet points of conversation hooks

6. RISK FLAGS — callout box (amber color) with 1-2 flags, OR an empty success-green callout if clean

7. FOOTER — generated timestamp, opaque internal_id hash, "Internal use only"

Constraints (same as before):
- One column, max-width 920px
- Single accent per section
- No emojis, no decorative icons
- NO internal codenames (RAPTOR, DABEIBA, etc.)
- Plain English, acronyms expanded
- WCAG AA contrast
```

Iterate, export, hand to Sonnet with `tasks/RAPTOR_DESIGN_PHASE_BRIEF.md` referenced.

---

## Quick reference — the workflow loop

```
1. Open Claude Design → /design                          (no code)
2. Pick design system: DABEIBA Web v1 or Decks v1        (locked rules)
3. New prototype → describe what you want in plain English
4. Iterate visually until happy
5. Export HTML
6. Hand to Sonnet with the appropriate brief file        (mechanical wiring)
7. Sonnet returns screenshots
8. Approve → ships into production
9. Ping back to Opus chat for next move
```

You stay in the visual / language space. Sonnet handles the code. Opus handles the architecture decisions.

---

## Common mistakes to avoid

- **Using Tiempos / Styrene fonts.** They're commercial. Stick to Playfair Display + Inter + JetBrains Mono (all free Google Fonts).
- **Pasting "Anthropic" or "Claude" as references in the design system.** Don't — describe the aesthetic family ("warm minimalism, editorial / longform-magazine") without naming a brand.
- **Adding emojis or decorative icons** in the prompts. The system explicitly forbids them. Geometric Unicode (· — →) is fine.
- **Letting Claude Design name your sections with codenames** like "ORACLE Insights" or "SOMA Brief". Always specify the substitute in the prompt ("internal research summary", "in-house ranking").
- **Generating two designs at once** — work on one prototype at a time so feedback loops are tight.
