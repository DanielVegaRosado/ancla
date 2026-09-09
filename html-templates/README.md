# HTML CV templates

A CV laid out here is printed to PDF by the user's own browser. This is the only way Ancla exports a CV.
The app never produces the PDF itself, and needs no native dependency to lay a CV out.

## The files

Each template is three files with the same name:

- `<name>.html` — a Jinja fragment (the CV itself, no `<html>` or `<head>`:
  the preview screen wraps it).
- `<name>.css` — its print stylesheet, served at
  `/plantillas-html/<name>.css`.
- `<name>.yaml` — the sidecar:

  ```yaml
  nombre:
    es: Visible name, Spanish interface
    en: Visible name, English interface
  capacidad_experiencias_min: 3
  capacidad_experiencias_max: 5
  ```

  `nombre` also accepts a plain string (same name in both languages).
  `capacidad_experiencias_min` is optional and defaults to 1 — most designs
  don't have a real lower bound, only a real upper one.

Drop them here and the template shows up on the Proposal screen and on any
saved CV. **No code change** , `ancla/export/html_templates.py` discovers
them by scanning this folder, and an `.html` without its `.yaml` (or with
one that fails to parse) is skipped rather than breaking the screen for
everyone else.

## Field catalog

Every tag a template can use, built by `ancla/export/fields.py::build_context`:

- `nombre`, `nombre_primero`, `nombre_resto` — the profile's name, whole and
  split on the first space (some designs style the first name differently
  from the rest; a template that doesn't need that keeps using `nombre`).
- `sobre_mi` — the "About me" text, in the proposal's language, gaps
  already filled in.
- `experiencias` — a list of `{puesto, empresa, fechas, bullets, stack}`.
  `empresa` is always empty: `Experience.title` already bundles "role ·
  company" together (see `ancla/profile/model.py`), so a template that
  wants them on separate lines has nothing to split them from.
- `skills`, `idiomas`, `skills_personales` — plain lists of names/lines, the
  chosen technical skills plus the personal skills and languages, which are
  always shown in full (never selected by the AI, see the root
  `CLAUDE.md`).
- `contacto` — the profile's contact lines (phone, email, city...).
- `titular` — the headline under the name, in the proposal's language.
- `educacion` — a list of `{titulo, centro, fechas}`.
- `foto` — the URL of the profile photo, empty string when there is none,
  so `<img src="{{ foto }}">` inside an `{% if foto %}` is all it takes.

## Range, not a single number

`capacidad_experiencias_min`/`_max` is the range of experiences the design
was **drawn for**, and the Proposal screen enforces it: the "experiences
that fit" field on that screen is clamped to `[min, max]` for whichever
template is selected. How many experiences there are is only half of what
decides whether the CV fits one page, though — see "One page, whatever the
user wrote" below for the other half.
With more experiences in the proposal than `max`, the extra ones are left
out of the print; dragging the experience cards on the Proposal screen
(same mechanism as reordering "Mi perfil") decides which ones make the
cut — nothing is picked automatically. With fewer than `min`, the CV still
prints with what there is — rule 1 forbids inventing an experience to pad
it — but the
screen says the design was meant for more, since a page that's too sparse
is a cosmetic risk, not a print-breaking one.

## One page, whatever the user wrote

A range of experiences is not enough to keep a CV on one page. How many
experiences fit is bounded; how long the user's "About me" is, is not, so
for any type size decided in advance there is a text long enough to
overflow it — and rule 2 rules out the other way of making it fit, since
the app never shortens or rewrites what the user wrote.

So the size is not decided in advance. `ancla/web/static/cv_fit.js` lays
the sheet out, measures the height its content asks for, and searches for
the largest scale that still fits one page. It is the whole reason for
laying a CV out in a browser: measuring is what the old `.docx` path could
not do without rendering it first.

A template owes it two things, both already in the stylesheets here:

- `--cv-alto-pagina`, the page height **in points**, on `.cv`. It is what
  the fitting is measured against.
- `--cv-escala`, a multiplier every vertical measurement in the main
  column is written against —
  `font-size: calc(10.5pt * var(--cv-escala, 1))`, and the same for
  leading, margins and the elastic gaps. Scale the whole column, not just
  its paragraphs: a design whose body text shrinks while its headings stay
  put stops being the design that was drawn. The sidebar is left out (its
  content comes from the profile, not from the proposal, so it does not
  grow with what the user writes), and so is the column's own padding, or
  the two columns would stop starting at the same height.

Both are checked by a test, so a design added later is fitted without
being calibrated by hand. There is no per-case table of sizes to read off
a printed PDF any more: a fixed number per case is exactly what could not
survive a longer "About me".

The search has a ceiling (1.2) and a floor (0.85). The ceiling is taste —
past it a CV with little in it reads as large print rather than as a
document. The floor is the point where body type reaches about 8pt, and
below it a CV that fits is worse than a CV that doesn't. When even the
floor does not fit, the preview screen says so before the user prints,
with the same reasoning as the experiences that don't make the cut:
nothing is trimmed and nothing happens silently, the user decides whether
to shorten their "About me" or to print two pages.

## Writing the stylesheet

- `@page { size: A4; margin: 0 }` if the design bleeds to the page edge, and
  then the design carries its own paddings.
- The fonts bundled with the app (IBM Plex Sans, 400/600/700) are already
  declared by `ancla/web/static/cv_preview.css`; just name the family. Any
  other font has to be hosted locally too — never a link to a font CDN (see
  the root `CLAUDE.md`: nothing about the user leaves their computer).
- `print-color-adjust: exact` is already set for the whole preview, so a
  colored panel prints without the user having to find the "background
  graphics" checkbox.
- A background that has to reach the bottom edge of **every** page (a
  full-height sidebar) cannot be painted by the sidebar element: its box
  ends where its content ends. Paint it with an empty element that is
  `position: absolute` on screen and `position: fixed` when printing —
  browsers repeat a fixed element on every printed page. See
  `corporativa-clasica.css`.

## Current templates

- **`corporativa-clasica`** — measured on the Canva export in
  `canva-templates/corporativa-clasica.pdf`: panel width and color, text
  colors, paddings, type sizes. Drawn in IBM Plex Sans, the font the app
  already ships, rather than the Aileron of the original Canva design,
  which is not bundled with the app.
- **`minimalista-calida`** — light grey sidebar with a terracotta accent,
  two-line name, each experience laid out as one running paragraph instead
  of bullets. Panel width, colors and the name treatment were traced by
  measuring pixels on `canva-templates/minimalista-calida.pdf`. This design
  is denser than Corporativa Clásica — a two-line name and a running
  paragraph eat more height than a single-line name and bullets — which
  shows up as a smaller scale for the same content rather than as anything
  to calibrate. It is drawn in IBM Plex Sans rather than the Montserrat of
  the original Canva design, which is not bundled with the app. The Canva
  original also shows a company address per experience and an "Interests"
  row of icons; neither exists on the profile (`empresa` is always empty,
  there is no hobbies
  catalog), so both are left out rather than invented, and the original
  has no "About me" section at all — one is kept here anyway since every
  profile in this app writes one.
