# Design System Rules — TQF System

This document captures the design system conventions for integrating Figma designs into this Flask/Jinja2 codebase.

---

## 1. Token Definitions

All design tokens are CSS custom properties defined in `:root` inside `static/css/style.css`. There is no token transformation pipeline — tokens are written and consumed directly as CSS variables.

```css
/* static/css/style.css — :root */

/* Colors */
--primary-color: #0f83a6;
--primary-hover: #0c6a85;
--bg-dark: #f5f7fb;          /* page background */
--bg-card: #ffffff;           /* card surfaces */
--text-main: #1c2434;
--text-muted: #607089;
--border-color: #d7dfec;
--accent-success: #12a150;
--accent-warning: #e19b0e;
--accent-danger: #d84949;
--surface-shadow: rgba(15, 131, 166, 0.12);
--frosted-highlight: rgba(255, 255, 255, 0.9);

/* Border Radius */
--radius-xl: 1.5rem;
--radius-lg: 1.25rem;
--radius-md: 1rem;
--radius-sm: 0.75rem;

/* Shadows */
--shadow-xl: 0 25px 45px -18px var(--surface-shadow);
--shadow-lg: 0 25px 60px -20px rgba(28, 36, 52, 0.25);
--shadow-md: 0 18px 35px -28px var(--surface-shadow);
--shadow-soft: 0 12px 28px -20px var(--surface-shadow);
```

**Rules:**
- Always reference these variables; never hard-code hex values for semantic colors.
- The body background uses a fixed radial/linear gradient composite — do not use a flat color on `body`.
- Semantic state colors map to: success = `--accent-success`, warning = `--accent-warning`, danger = `--accent-danger`, primary/info = `--primary-color`.

---

## 2. Component Library

There is no external component library. All UI components are hand-crafted CSS classes defined in `static/css/style.css` and rendered via Jinja2 templates. There is no Storybook or component documentation beyond this file and inline comments in the CSS.

### Key Component Patterns

#### Cards

```html
<!-- Primary content card (large) -->
<div class="glass-card glass">...</div>

<!-- Smaller card variant -->
<div class="glass-card-sm glass">...</div>

<!-- Feature/navigation card (clickable link) -->
<a href="..." class="feature-card">
    <h3>Title</h3>
    <p class="text-muted text-xs">Subtitle</p>
</a>

<!-- Course card -->
<div class="course-card">...</div>

<!-- Generic panel -->
<div class="panel">...</div>
<div class="panel-sm">...</div>
```

#### Buttons

```html
<!-- Primary action -->
<button class="btn btn-primary">Action</button>

<!-- Secondary/outline -->
<button class="btn btn-secondary">Action</button>

<!-- Success -->
<button class="btn btn-success">Action</button>

<!-- Ghost danger (destructive, low emphasis) -->
<button class="btn btn-ghost-danger">Delete</button>

<!-- Full-width hero button -->
<button class="btn btn-primary btn-xl">Submit</button>

<!-- Compact table/inline button -->
<button class="btn btn-primary btn-compact">Edit</button>
```

Button hover has a radial mouse-tracking shimmer effect driven by `--mouse-x`/`--mouse-y` CSS variables set via JS in `base.html`. This is automatic for all `.btn` elements.

#### Forms

```html
<div class="form-group">
    <label for="field">Label</label>
    <input type="text" id="field" name="field" class="form-control" placeholder="...">
</div>

<!-- Inline grid (input + button side by side) -->
<div class="form-inline-grid">
    <input class="form-control" ...>
    <button class="btn btn-primary">Go</button>
</div>

<!-- Two-column form grid -->
<div class="qtf-grid two">
    <div class="form-group">...</div>
    <div class="form-group">...</div>
</div>
```

#### Status Badges

```html
<!-- TQF document states -->
<span class="status-badge status-draft">Draft</span>
<span class="status-badge status-submitted">Submitted</span>
<span class="status-badge status-approved">Approved</span>

<!-- Role badges -->
<span class="status-badge role-admin">Admin</span>
<span class="status-badge role-head">Head</span>
<span class="status-badge role-academic">Academic</span>
<span class="status-badge role-instructor">Instructor</span>
```

#### Stat Cards (KPI)

```html
<div class="stat-grid">
    <div class="stat-card">
        <div class="stat-label">LABEL</div>
        <div class="stat-value">42</div>
    </div>
    <div class="stat-card success">...</div>
    <div class="stat-card danger">...</div>
</div>
```

#### Alerts / Flash Messages

```html
<div class="alert alert-success">...</div>
<div class="alert alert-warning">...</div>
<div class="alert alert-danger">...</div>
<div class="alert alert-info">...</div>
```

Flash categories must match exactly: `success`, `warning`, `danger`, `info`.

#### Tables

```html
<!-- Standard data table -->
<div class="table-wrapper">
    <table class="data-table">
        <thead><tr><th>...</th></tr></thead>
        <tbody><tr><td>...</td></tr></tbody>
    </table>
</div>

<!-- Compact variant -->
<table class="data-table data-table--compact">...</table>

<!-- Scrollable table panel (max-height 50vh) -->
<div class="table-scroll-panel">
    <table class="data-table">...</table>
</div>

<!-- TQF editor table (full-bordered) -->
<div class="qtf-table-wrapper">
    <table class="qtf-table">...</table>
</div>
```

#### Modals

```html
<div class="modal" id="myModal">
    <div class="modal-card">
        <div class="modal-header">
            <h3>Title</h3>
            <button>X</button>
        </div>
        <div class="modal-body">...</div>
        <div class="modal-actions">
            <button class="btn">Cancel</button>
            <button class="btn btn-primary">Confirm</button>
        </div>
    </div>
</div>
```

Toggle visibility with JS: `modal.style.display = 'block'` / `'none'`.

#### Accordion / Collapsible Sections

```html
<details class="accordion-card glass">
    <summary>
        Section Title
        <span class="accordion-divider"></span>
    </summary>
    <div class="mt-3">...content...</div>
</details>
```

#### Navigation

The navbar is defined in `templates/base.html` and styled in `static/css/style.css` under `.navbar`. It is sticky, glassmorphic, and includes a hamburger toggle for mobile (breakpoint: 1024px). Do not duplicate navbar markup; it lives only in `base.html`.

---

## 3. Frameworks & Libraries

| Layer | Technology |
|---|---|
| Backend | Python 3.10, Flask, Flask-Login |
| Templates | Jinja2 (server-side rendering) |
| CSS | Vanilla CSS — no Tailwind, no Sass, no CSS Modules |
| JS | Vanilla JavaScript — no React, Vue, or bundler |
| Fonts | Inter (Latin) + Sarabun (Thai) loaded from Google Fonts |
| Icons | Unicode emoji characters used inline (no icon library) |
| Database | Google Cloud Firestore (no SQL) |

**No build step.** All CSS/JS is authored directly and served as static files.

---

## 4. Asset Management

```
static/
  css/
    style.css    ← single stylesheet; ALL styles go here
```

- There is only one CSS file. Do not create additional stylesheets; append new styles to `static/css/style.css`.
- No image assets are used. Visuals rely on CSS gradients, emoji, and text-based avatars.
- No CDN for static assets — Flask serves them via `url_for('static', filename='...')`.
- Google Fonts are loaded in `base.html` with `preload` + `media="print"` async pattern for performance.

---

## 5. Icon System

There is no icon library. Icons are conveyed via:

1. **Unicode emoji** — rendered inline as text, e.g. `📋`, `✅`, `⚠️`, `🔒`
2. **Text abbreviations** — e.g. the nav logo badge "TQF"
3. **CSS-generated content** — the accordion disclosure arrow uses `content: "‹"` in CSS

When implementing Figma icons, map them to the closest Unicode emoji or reproduce them with CSS `::before`/`::after` pseudo-elements. Do not introduce an SVG sprite or an icon font library.

---

## 6. Styling Approach

### Methodology
- **Global single stylesheet** (`static/css/style.css`) — BEM-lite class naming with semantic prefixes.
- No scoped styles, no CSS Modules, no CSS-in-JS.
- Class naming conventions:
  - Layout utilities: `.flex-between`, `.flex-end`, `.flex-center-gap`, `.layout-grid-two`, `.layout-grid-aside`
  - Spacing utilities: `.mt-2` through `.mt-6`, `.mb-0` through `.mb-3`, `.gap-sm`, `.gap-md`
  - Column widths: `.col-48`, `.col-80`, ..., `.col-60p`, `.col-65p` (fixed px or %)
  - Text utilities: `.text-xs`, `.text-sm`, `.text-xxs`, `.text-mono`, `.text-center`, `.text-primary`, `.text-muted`, `.text-warning`, `.text-success`, `.text-danger`
  - Component namespacing: `.qtf-*` (TQF editor), `.summary-*` (TQF5 summary), `.nav-*` (navbar), `.stat-*` (KPI cards)

### Glassmorphism

The visual theme is glassmorphism on a light background. Apply the `.glass` utility class to give any element a frosted-glass appearance:

```css
.glass {
    background: var(--frosted-highlight);   /* rgba(255,255,255,0.9) */
    backdrop-filter: blur(16px);
    border: 1px solid rgba(15, 131, 166, 0.08);
    box-shadow: var(--shadow-xl);
}
```

### Responsive Design

Breakpoints (no framework, custom media queries):

| Breakpoint | Behavior |
|---|---|
| `max-width: 1200px` | Nav inner wraps |
| `max-width: 1100px` | Summary layout collapses to single column |
| `max-width: 1024px` | Hamburger nav shown; aside grids collapse |
| `max-width: 980px` | `.layout-grid-aside` collapses |
| `max-width: 640px` | `.form-inline-grid` collapses |
| `max-width: 600px` | Nav avatar shrinks; KPI grid adjusts |

Use `repeat(auto-fit, minmax(..., 1fr))` grid patterns for most multi-column layouts — they are inherently responsive without explicit breakpoints.

---

## 7. Project Structure

```
QualificationsFramework/
├── app.py                        # All Flask routes (~3600 lines), CLI commands
├── models.py                     # Firestore dataclasses (FirestoreModel base)
├── firestore_db.py               # Firestore client singleton
├── static/
│   └── css/
│       └── style.css             # Single global stylesheet — all styles here
├── templates/
│   ├── base.html                 # Shared layout: navbar, flash messages, fonts, global JS
│   ├── login.html
│   ├── choose_role.html
│   ├── account.html
│   ├── admin/                    # Admin role pages
│   │   ├── dashboard.html
│   │   ├── users.html
│   │   ├── faculties.html
│   │   ├── programs.html
│   │   └── courses.html
│   ├── academic/                 # Academic role pages
│   │   ├── dashboard.html
│   │   ├── manage_terms.html
│   │   ├── open_course.html
│   │   ├── term_documents.html
│   │   └── term_program.html
│   ├── head/                     # Head role pages
│   │   ├── dashboard.html
│   │   ├── review.html
│   │   ├── term_documents.html
│   │   └── tqf5_summary.html
│   ├── instructor/               # Instructor role pages
│   │   ├── dashboard.html
│   │   ├── edit_tqf3.html
│   │   └── edit_tqf5.html
│   └── shared/                   # Read-only views shared across roles
│       ├── tqf3_readonly.html
│       └── tqf5_readonly.html
└── requirements.txt
```

### Template Pattern

Every page extends `base.html`:

```html
{% extends "base.html" %}

{% block title %}Page Title{% endblock %}

{% block content %}
<div class="section-lead">
    <h2>Page Heading (Thai primary)</h2>
    <p>Subtitle / description</p>
</div>

<!-- Page content here -->
{% endblock %}

{% block scripts %}
<!-- Optional page-specific JS -->
{% endblock %}
```

### Page Layout Patterns

**Dashboard/feature grid:**
```html
<div class="card-grid">
    <a href="..." class="feature-card">...</a>
</div>
```

**Content + sidebar:**
```html
<div class="layout-grid-aside">
    <div><!-- main content --></div>
    <div><!-- sidebar / filters --></div>
</div>
```

**Two-column equal grid:**
```html
<div class="layout-grid-two">
    <div>...</div>
    <div>...</div>
</div>
```

**Page header with action button:**
```html
<div class="page-header">
    <div class="section-lead mb-0">
        <h2>Title</h2>
        <p>Subtitle</p>
    </div>
    <a href="..." class="btn btn-primary">+ Add</a>
</div>
```

---

## 8. Figma-to-Code Integration Guidelines

When translating Figma designs to this codebase:

1. **Map colors to CSS variables** — never use raw hex values; find the closest token from `:root`.
2. **Use existing component classes** — before creating a new class, check if `.glass-card`, `.feature-card`, `.qtf-card`, `.stat-card`, etc. already match the design intent.
3. **Add styles to `static/css/style.css`** — all new styles go at the bottom of this single file.
4. **Thai language first** — all user-facing copy is bilingual; Thai text is primary. Preserve existing Thai strings.
5. **No build step** — do not introduce Tailwind, Sass, PostCSS, webpack, or any bundler.
6. **Glassmorphism aesthetic** — light backgrounds, frosted white surfaces, soft teal (`--primary-color`) accents, large border-radii, layered shadows.
7. **Responsive by default** — use `auto-fit` grids and the existing breakpoints; avoid fixed-width layouts below 1200px.
8. **Flash messages** — use Flask `flash(message, category)` with categories `success`, `warning`, `danger`, `info` — rendered automatically by `base.html`.
