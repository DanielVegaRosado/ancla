# HTML CV templates

A CV laid out here is printed to PDF by the user's own browser (Ctrl+P →
Save as PDF), the same way the `.docx` is exported from their own Word. The
app never produces a PDF, and needs no native dependency to do any of this.

The point of laying a CV out in HTML rather than only in `.docx` is the page
break. A `.docx` cannot be measured without rendering it, so
`ancla/export/fill.py` estimates line wrapping from character-width tables
and a geometry declared by hand in each template's `.yaml` — and a CV still
spills onto a second page now and then. A browser measures its own text, so
where a page ends is *stated* (`break-inside: avoid`) instead of guessed.

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
saved CV. **No code change** — `ancla/export/html_templates.py` discovers
them by scanning this folder, and an `.html` without its `.yaml` (or with
one that fails to parse) is skipped rather than breaking the screen for
everyone else.

Unlike the `.docx` sidecar, there is no `geometria` block: nothing about the
page has to be declared, because nothing about it is being estimated.

## Field catalog

Exactly the same as the `.docx` one — see `docx-templates/README.md`. Both
paths are filled by `fill.build_context`, so a field one can show the other
can show too, and neither can drift.

The one difference is `{{ foto }}`: here it is the URL of the profile photo
(empty string when there is none), so `<img src="{{ foto }}">` inside an
`{% if foto %}` is all it takes.

## Range, not a single number

`capacidad_experiencias_min`/`_max` is the range of experiences the design
was **drawn for**, and the Proposal screen enforces it: the "experiences
that fit" field on that screen is clamped to `[min, max]` for whichever
template is selected, so **the preview can never run onto a second page** —
unlike the `.docx` path, which still can (see `docx-templates/README.md`).
With more experiences in the proposal than `max`, the extra ones are left
out of the print and named on screen instead, with their selection reason,
so nothing disappears silently; dragging the experience cards on the
Proposal screen (same mechanism as reordering "Mi perfil") decides which
ones make the cut. With fewer than `min`, the CV still prints with what
there is — rule 1 forbids inventing an experience to pad it — but the
screen says the design was meant for more, since a page that's too sparse
is a cosmetic risk, not a print-breaking one.

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

- **`corporativa-clasica`** — the HTML counterpart of the `.docx` of the
  same name, from the same Canva design. Every measurement (panel width and
  color, text colors, paddings, type sizes) comes from the spec measured on
  that PDF in `herramientas/construir-corporativa-clasica.py`, so both
  versions of the template stay comparable. It is drawn in IBM Plex Sans,
  the font the app already ships, rather than the Aileron of the `.docx`,
  which is not bundled with the app.

- **`minimalista-calida`** — the HTML counterpart of the `.docx` of the
  same name: light grey sidebar with a terracotta accent, two-line name,
  each experience laid out as one running paragraph instead of bullets.
  Panel width, colors and the name treatment were traced by measuring
  pixels on `canva-templates/minimalista-calida.pdf`; the three type
  scales (`.cv-escala-3/4/5` in its CSS) come from printing the template
  itself with real content and reading off the result, the same method as
  Corporativa Clásica but its own numbers — this design is denser (a
  two-line name and a running paragraph eat more height than a single-line
  name and bullets), so its scales spread wider between the 3- and 5-case.
  It is drawn in IBM Plex Sans rather than the Montserrat of the `.docx`,
  which is not bundled with the app. The Canva original also shows a
  company address per experience and an "Interests" row of icons; neither
  exists on the profile (`empresa` is always empty, there is no hobbies
  catalog), so both are left out rather than invented, and the original
  has no "About me" section at all — one is kept here anyway since every
  profile in this app writes one.
