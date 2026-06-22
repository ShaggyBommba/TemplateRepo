# Design System

This document defines the HTMX SaaS design system for the template browser
surface. Styling is built with Tailwind CSS v4 and daisyUI (no Node required)
from `src/presentation/htmx/static/css/input.css` into
`src/presentation/htmx/static/css/app.css`, which `layout.html` links. Shell
markup lives in `src/presentation/htmx/templates/layout.html` and
`src/presentation/htmx/templates/navbar.html`.

Build the stylesheet with `task css` (or `task css-watch` while iterating).
daisyUI is the default component layer; `input.css` should mostly define the
template shell, page grids, responsive table behavior, and small helpers that
compose daisyUI components.

Use this guide when adding or changing browser templates under
`src/presentation/htmx/templates/`.

## Principles

- Build application screens, not marketing pages.
- Keep the interface dark, quiet, and operational.
- Prefer dense, scannable information over oversized decorative sections.
- Keep behavior local to the feature that owns it.
- Use htmx for server interaction and Alpine.js for local state.
- Keep cards shallow. Do not put page sections inside decorative outer cards.
- Keep border radius at `.5rem` or less except fully rounded badges and dots.
- Do not introduce decorative orbs, bokeh, or one-off background art.

## Source Files

```text
src/presentation/htmx/
  static/
    css/
      input.css      # Tailwind v4 + daisyUI theme + layout helpers
      app.css        # built stylesheet, served at /static/css/app.css
    vendor/
      htmx.min.js    # pinned htmx 2.0.4
      alpinejs.min.js # pinned Alpine.js 3.14.8
  templates/
    layout.html      # document shell; links built CSS and vendored JS
    navbar.html      # sidebar shell and auth entrypoints
    admin/
      index.html     # admin websocket panel pattern
    home/
      index.html     # overview dashboard pattern
    system/
      index.html     # system console pattern
    auth/
      callback.html  # OAuth callback state pattern
```

## Tokens

Tokens are CSS custom properties on `:root`.

| Token | Value | Use |
| --- | --- | --- |
| `--bg` | `#08090d` | App background |
| `--surface` | `#0e1016` | Structural dark surface |
| `--panel` | `#141720` | Cards, panels, metric tiles |
| `--panel-soft` | `#10131a` | Code blocks and soft nested surfaces |
| `--line` | `#272b36` | Default borders and dividers |
| `--line-strong` | `#343a48` | Active and hover borders |
| `--text` | `#f4f6fb` | Primary text |
| `--muted` | `#9aa3b2` | Body copy and secondary labels |
| `--subtle` | `#687083` | Eyebrows, table headers, metadata |
| `--accent` | `#39d0b3` | Interactive accent and positive emphasis |
| `--focus` | `#8ab4ff` | Keyboard focus outline |

Rules:

- Add a token before adding a repeated raw color.
- Use daisyUI semantic utilities for state colors, such as `text-success`,
  `text-warning`, `alert-error`, `status-success`, and `status-warning`.
- Keep the dominant palette neutral dark with teal as the only primary accent.

## Typography

The shell uses system UI fonts:

```css
Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif
```

Scale:

| Element | Size | Notes |
| --- | --- | --- |
| `h1` | `2rem`, mobile `1.75rem` | Page title only |
| `h2` | `1rem` | Panel title |
| `h3` | `.95rem` | Panel row title |
| `.meta-label` | `.72rem` | Uppercase metadata |
| `.badge` | daisyUI scale | Compact status and count labels |
| `.metric-copy` | `.9rem` | Tile support text |

Rules:

- Use `letter-spacing: 0` for headings.
- Use uppercase only for metadata labels, not normal prose.
- Keep copy short and operational.

## Layout

The base shell is `.shell`:

- Desktop: two-column layout with a `16.5rem` sidebar and fluid workspace.
- Tablet and below: single-column layout.
- Main content width: `min(74rem, calc(100% - 2rem))`.
- Main padding: `1.5rem 0 3rem`.

Core layout classes:

| Class | Purpose |
| --- | --- |
| `.shell` | Page-level app frame |
| `.sidebar` | Sticky desktop navigation, stacked mobile navigation |
| `.workspace` | Main application content area |
| `.topbar` | Page utility row for status and auth actions |
| `.page-head` | Page title, eyebrow, lede, and primary actions |
| `.summary-grid` | Four metric tiles on desktop |
| `.dashboard-grid` | Primary content plus supporting panel |
| `.endpoint-grid` | Small grid of endpoint/action buttons |
| `.flow-stack` | Vertical spacing for labels and content |
| `.section-space` | Standard vertical spacing between sections |

Responsive breakpoints:

- `max-width: 980px`: sidebar becomes a top section; major grids become two
  columns.
- `max-width: 720px`: major grids become one column; table rows become stacked
  key-value cards.

## Components

### Sidebar

Use `navbar.html` for global navigation. It owns:

- brand mark and product name
- workspace navigation links
- active route state
- session affordance with login/logout

Do not duplicate global navigation inside feature templates.

### Buttons

Use daisyUI buttons for links and native buttons:

```html
<a class="btn btn-sm btn-outline" href="/status">Status</a>
<button class="btn btn-sm btn-primary" type="button">Refresh</button>
```

Buttons must:

- have visible text
- keep icons optional and decorative with `aria-hidden="true"`
- preserve focus-visible styles
- use disabled state for active async work

### Badges And Status

Use daisyUI `.badge` for compact metadata such as status, counts, and version.
Use daisyUI `.status` for small health dots.

Status color conventions:

| Class | Meaning |
| --- | --- |
| `.text-success`, `.status-success` | Ready, healthy, successful |
| `.text-warning`, `.status-warning` | Degraded, unavailable, pending |
| `.alert-error`, `.text-error` | Error or failed |

### Metrics

Use `.metric` inside `.summary-grid` for top-level dashboard facts. Each metric
should contain:

1. `.meta-label`
2. `.value`
3. `.metric-copy`

Use metrics for stable, high-value state such as status, version, identity, and
enabled platform capabilities.

### Panels

Use daisyUI `.card card-border bg-base-200` with `.panel` for grouped
operational content. Use `.panel-head` for title and metadata. Use
`.panel-list` and `.panel-item` for repeated rows.

Panel rows should be short and scannable:

```html
<li class="border border-base-300 bg-base-100 rounded-box panel-item row">
  <div class="flow-stack">
    <h3>Presentation</h3>
    <p>FastAPI HTMX routes render feature-owned templates.</p>
  </div>
  <span class="badge badge-outline">ready</span>
</li>
```

### Tables

Use daisyUI `.table` for dense data inside a `.card card-border table-panel`.
Add `data-label` to every body cell so mobile rows can become stacked key-value
cards.

```html
<td data-label="Status"><span class="text-success">Ready</span></td>
```

Avoid snapshot-like tables that expose implementation details only. Table rows
should describe observable app or runtime state.

### Callback State

Use the auth callback pattern in `auth/callback.html` for transient async
states:

- `authenticating`
- `success`
- `error`

The page uses htmx to call `/auth/callback/verify` on load and Alpine.js to
toggle visible state.

## Interaction

Use htmx for server interaction when a route returns HTML or transport status.
Use Alpine.js for local UI state such as loading, error messages, and status
refresh.

Current interaction conventions:

- `hx-trigger="load"` for OAuth callback verification.
- `fetch("/status")` inside Alpine.js for local dashboard refresh.
- `new WebSocket(...)` inside Alpine.js for the admin job-status stream.
- `aria-live="polite"` on status regions that change after refresh.
- `:aria-busy="loading.toString()"` for async sections.

Do not put business decisions in templates. Templates may format transport
state already supplied by the route.

## Accessibility

Minimum requirements:

- Every navigation group must have a semantic container or accessible label.
- Every interactive element must have visible text.
- Decorative icon spans must use `aria-hidden="true"`.
- Async status regions should use `aria-live="polite"`.
- Disabled async controls should expose `aria-busy`.
- Keyboard focus must remain visible through `:focus-visible`.
- Mobile layouts must not require horizontal scrolling for primary workflows.

## Extending The System

For a new feature page:

1. Extend `layout.html`.
2. Keep global navigation in `navbar.html`.
3. Start with `.topbar` and `.page-head`.
4. Use `.summary-grid` for page-level facts.
5. Use `.dashboard-grid`, daisyUI `.card`, `.panel`, and `.panel-item` for
   operational content.
6. Use `.table-panel` only when comparison across rows matters.
7. Add focused presentation tests for rendered shell text and behavior wiring.

Add a new shared class only when at least two feature templates need it or when
it represents a stable design-system concept.
