# Template gallery (previews)

Ancla doesn't design a CV layout from scratch — it fills an existing one
(see `docx-templates/README.md` for the `.docx` templates that actually
get filled and downloaded). This folder is upstream of that: the original
Canva designs, kept here only as PDF previews shown inline on the app's
Templates screen — never a redirect out to canva.com.

## Adding a template

Each entry is a pair of files with the same name:

- `<name>.pdf` — the template exported from Canva as a PDF, for preview only.
- `<name>.yaml` — a sidecar with one field, `nombre`: either a plain string
  (same name in both languages) or `{es: ..., en: ...}` for a different
  name per interface language, e.g.:

  ```yaml
  nombre:
    es: Corporativa Clásica
    en: Classic Corporate
  ```

Drop both files here and it shows up. No code change needed —
`ancla/design/gallery.py` discovers them by scanning this folder, and a
`.pdf` without its `.yaml` (or with one that fails to parse) is skipped
rather than breaking the screen for everyone else.

These previews aren't part of the codebase and aren't subject to the
selection engine's never-invent rules. They're design, managed by hand by
Daniel, the same way the final CVs are.
