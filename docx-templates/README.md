# .docx export templates

Each template is a pair of files with the same name:

- `<name>.docx` — the actual Word document, with Jinja tags (`docxtpl`) in
  place of the content.
- `<name>.yaml` — a sidecar with two fields:

  ```yaml
  nombre:
    es: Visible name, Spanish interface
    en: Visible name, English interface
  capacidad_experiencias: 4
  ```

  `nombre` also accepts a plain string (same name in both languages)
  instead of the `{es, en}` mapping.

Drop both files here and the template shows up on the Proposal screen's
export dropdown. No code change needed — `ancla/export/templates.py`
discovers them by scanning this folder, and a `.docx` without its `.yaml`
(or with one that fails to parse) is skipped rather than breaking the
screen for everyone else.

## Field catalog

The template can use these Jinja tags; everything else in the proposal is
never sent to the fill step:

- `{{ nombre }}` — the user's own name, from Ajustes.
- `{{ nombre_primero }}` / `{{ nombre_resto }}` — `nombre` split on the
  first space, for a design that styles the first name differently from
  the rest (formatting lives on the run, not on the text, so a single tag
  can't express that). A template that doesn't need the split just keeps
  using `{{ nombre }}` whole.
- `{{ titular }}` — the profile's headline (job title / degree), always
  complete, in the proposal's language.
- `{{ sobre_mi }}` — the composed "About me" text.
- `{{ experiencias }}` — repeatable block, one item per chosen experience,
  each with `puesto`, `empresa` (see note below), `fechas`, `bullets`
  (a list), and `stack` (the tech-stack line, may be empty). Use
  `{%tr for exp in experiencias %}` / `{%tr endfor %}` in their own table
  rows to repeat a row per experience (see `tests/fixtures/prueba.docx`).
- `{{ skills }}` — list of chosen technical skill names.
- `{{ idiomas }}` — list of `"Name — Level"` strings, always complete.
- `{{ skills_personales }}` — list of personal skill names, always complete.
- `{{ contacto }}` — list of the profile's contact lines, always complete,
  in the order set in Ajustes. Loop over it (`{%p for linea in contacto %}`)
  rather than assuming a fixed count or order.
- `{{ educacion }}` — repeatable block, one item per education entry, each
  with `titulo`, `centro` and `fechas`, always complete (never selected by
  the engine — a real CV doesn't trim its education by job posting).
- `{{ foto }}` — an `InlineImage`, or an empty string if the profile has no
  photo. Wrap the tag in `{%p if foto %}` / `{%p endif %}` so a profile
  without one doesn't leave a broken image placeholder. Any other picture
  added to the template by hand (a logo, a decorative shape) needs its Alt
  Text description set to `ancla:decorativo`, or `fill.py` will treat it as
  the profile photo and crop it into a circle (see the sidebar-color note
  below for the same mechanism applied to a background shape).

**`empresa` is always empty.** The profile has no separate company field:
`puesto` already carries "Role · Company" together, the same way it is
shown everywhere else in the app. A template that wants them on separate
lines has nothing to split them from today.

### Section header labels (bilingual)

Section headers ("Contact", "About me"...) are plain text you type
directly into the template, not a single tag — but the proposal can be
generated in Spanish or English, so a header hardcoded in one language
will clash with content in the other. Use these tags instead of typing the
label yourself, and `fill.py` fills in the right language automatically:

- `{{ etiqueta_contacto }}`, `{{ etiqueta_educacion }}`,
  `{{ etiqueta_skills_personales }}`, `{{ etiqueta_idiomas }}`,
  `{{ etiqueta_sobre_mi }}`
- `{{ etiqueta_skills_tecnicas }}` or `{{ etiqueta_skills }}` — pick
  whichever reads better for the design. Minimalista Cálida uses the
  second, as a standalone header.
- `{{ etiqueta_tecnicas }}` / `{{ etiqueta_personales }}` — bare
  subtitles ("Technical" / "Personal"), for a design that groups a single
  `{{ etiqueta_skills }}` header with both skill lists under it instead of
  two independent sections (Corporativa Clásica does this, matching its
  Canva original).
- `{{ etiqueta_experiencia_relevante }}` or `{{ etiqueta_experiencia }}` —
  same idea.

Adding a header this catalog doesn't cover is a code change (a new entry
in `fill.py::_ETIQUETAS`), not something to leave as fixed text — a fixed
label always ends up wrong in the other language.

## Repeating the experience block

`docxtpl` needs **three table rows**, not two, to repeat a single row:

1. A row whose only content is `{%tr for exp in experiencias %}` — it
   disappears from the rendered document.
2. The real row: `{{ exp.puesto }}`, `{{ exp.bullets|join(...) }}`, etc.,
   with no `tr` tag anywhere in it. This is the one that repeats, once per
   experience.
3. A row whose only content is `{%tr endfor %}` — also disappears.

Putting `for` and `endfor` in the same row breaks with
`TemplateSyntaxError: Encountered unknown tag 'endfor'` — `docxtpl` strips
the `<w:tr>` around each marker independently, and if they share a row the
first strip already consumes the row the second one needed. All three
templates in this folder follow the three-row pattern; copy it rather than
rediscovering it.

## Overflow

`capacidad_experiencias` never trims silently. If the proposal has more
experiences than the template declares room for, the app asks the user to
either keep only the most relevant ones or include all of them (the extra
rows overflow onto the next page in Word — the app does not paginate
anything itself).

## Current templates

Only real, user-facing templates live in this folder — they show up in the
export dropdown for anyone using the app. The minimal test template
(`prueba.docx`, deliberately plain, exercises every field and both
overflow answers) lives in `tests/fixtures/` instead, precisely so it
never appears as a choice for a real CV; it's still the reference for the
three-row loop trick above.

- **`minimalista-calida.docx`** and **`corporativa-clasica.docx`** —
  rebuilt from the two Canva designs (`canva-templates/README.md`) to
  match their layout and colors: light sidebar with a terracotta accent
  for the first, dark navy sidebar for the second. Every run uses Open
  Sans, matching the Canva originals. Contact, education and the photo are
  Jinja tags like everything else in the field catalog above — filled from
  the user's own profile at render time, never baked into the `.docx`
  itself. Nothing personal lives in this folder (see root `CLAUDE.md`:
  nothing personal goes in `app/`).

  **The sidebar color reaches every edge of the page** via a solid
  rectangle picture anchored to the page itself (behind the text, full
  page height), not by stretching the table row — a table row tall enough
  to reach the page edge risks spilling a blank second page (Word reserves
  space for an implicit paragraph mark after the last table that doesn't
  show up in any arithmetic based on page size and margins). If you add
  your own picture to a template by hand in Word (a logo, an accent shape,
  anything that isn't the profile photo), give it that same treatment —
  right-click → **Edit Alt Text** → set the description to
  `ancla:decorativo`. Without it, `ancla/export/fill.py::_recortar_a_circulo`
  will treat your picture as the profile photo and mangle it into a
  circle.
