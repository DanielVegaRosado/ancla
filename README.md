# Ancla

**Doesn't generate your CV. Selects from facts you've already verified.**

You keep a database of your experience and skills. For every job posting, the app
chooses what to show and tells you why. It never writes anything you didn't write
yourself: if the posting asks for something you don't have, it's flagged as a gap
instead of being invented.

Every adaptation is saved. Your base of facts grows, and your archive of
applications grows with it.

**[Try it online](https://ancla.onrender.com)** — no install needed, runs against a shared
example profile. Free-tier hosting spins down after inactivity, so the first load can take up to
a minute. For your own data, run it locally (see below) or use the desktop app.

- Runs **on your computer**. Your data never leaves it: no accounts, no cloud.
- Uses **your own AI key**. Groq has a free tier, and several paid providers
  (OpenAI, Anthropic, Mistral, OpenRouter, or any other with a compatible API) are
  also supported.
- Fills a ready-made template for you. Pick one of the [built-in
  designs](canva-templates/README.md) and download a finished `.docx`,
  already laid out — no copy-pasting into another tool.
- **Your whole profile in one file.** Download it as a `.zip` from Settings
  any time — a backup, or a way to move to another computer.
- **Free and open source, and it stays that way.** Your data never leaves your
  computer, no accounts, no cloud. Future paid features (the kind that need a
  server, like conversational support) will be optional additions — never a
  limit on what's free today.

## Getting started

1. Clone this repository and open the `app/` folder.
2. Install Python 3.11 or newer if you don't already have it.
3. Install the dependencies: `pip install -r requirements.txt`.
4. Start the app: `python run.py`. It opens on its own at `http://127.0.0.1:5000`.
5. Go to Settings and pick an AI provider. Groq's free tier works out of the box,
   you just need an account and a key. Paste your key, and the model name too if
   you picked a provider other than Groq.
6. Fill in your profile, either by hand under "My profile" or by importing an
   existing CV (PDF or Word) and reviewing what it finds before saving it.
7. Paste a job posting under "Adapt" and generate the proposal.
8. Pick a template and export it: a ready-made `.docx` downloads, already
   filled in and laid out. Open it in Word, LibreOffice or Google Docs and
   export to PDF from there — Ancla doesn't generate the PDF itself.

If you'd rather not touch a terminal, the desktop version skips steps 2 to 4 once
it's ready (see *Desktop app* below). It's still work in progress today.

## Status (v1)

| Piece | Status |
|---|---|
| Data model and interfaces | ✅ |
| Profile store (YAML) | ✅ |
| Selection engine | ✅ |
| Web interface (bilingual ES/EN) | ✅ |
| CV archive | ✅ |
| Import from an existing CV (PDF/Word) | ✅ |
| Fill a `.docx` template with the proposal | ✅ |
| Support and template gallery | ✅ |
| Profile backup (download as `.zip`) | ✅ |
| Sample profile to try the app with | ✅ |
| Multiple AI providers (Groq, OpenAI, Anthropic, Mistral, OpenRouter, custom) | ✅ |

Tested end to end, locally: creating experience and skills, defining the "About me"
template, pasting a job posting and generating the proposal with a real Groq key.
`perfil-ejemplo/` ships a complete fictional profile (experience, skills, languages
and "About me" template, in Spanish and English) so anyone who clones the repo can
try the app without writing their whole profile first.

## What this app guarantees

1. "Never invents" isn't a marketing promise. It's open source, so you can read
   `ancla/selection/engine.py` yourself and confirm that an ID missing from your profile is
   discarded no matter what the model returns.
2. An explicit reason behind every choice, not just a score.
3. Zero account, zero cloud. Also verifiable by reading the code, not a line like
   "securely synced to the cloud."
4. Free, no paywall, using your own key. Groq's free tier costs nothing to start with.
5. Doesn't design a layout from scratch. It fills one of the [built-in
   `.docx` templates](canva-templates/README.md), never composing a page itself.
   Using your own template isn't supported yet.

## What criteria the AI follows

There are two moments where an AI model makes decisions, and both follow the same
principle: **the guarantee comes from the code, not from an instruction the model
could ignore.**

### Adapting your profile to a job posting (`ancla/selection/`)

The model only returns *IDs* from your catalogue, never new text, so whatever ends
up on your CV is, literally, something you wrote yourself. Rules:

1. **Never suggests anything that isn't in your profile.** If an ID doesn't exist in
   your catalogue, the code discards it before it reaches the screen. This isn't a
   request made to the model, it's a check applied after its response.
2. **Never rewrites your bullet points.** They're shown exactly as you wrote them.
3. **Every choice comes with a reason**, so you can judge the proposal instead of
   signing off on it blindly.
4. **Whatever the posting asks for that you don't have goes to "gaps"**, never onto
   the CV. Making things up is exactly what this tool refuses to do.
5. Given several candidate experience entries, it prioritises ones covering
   **different** requirements over repeating the same tech stack.

### Importing an existing CV (`ancla/profile/importer.py`)

Here the risk isn't the model inventing a gap: it's **over-paraphrasing** while
reading your CV (turning "collaborated with the team" into "led a team of 5"). The
guarantee here is procedural: nothing is saved to your profile without you
confirming it, field by field.

1. **Text extraction is 100% deterministic** (a library, no AI): the model never
   "reads" the PDF or Word file directly, it analyses the exact text already pulled
   from the file. That way it can't misread a word without it being noticed.
2. **Only extracts what's literally in the text.** It doesn't add responsibilities,
   achievements or dates that aren't there.
3. **If a field is missing, it's left blank.** Never filled in with a reasonable
   guess.
4. **Translates whichever language is missing**, literally, so you don't have to
   write both languages by hand. *(See Next version improvements below for a
   planned change to how this translation works.)*
5. **When in doubt between an experience entry or a standalone skill, it suggests a
   skill.** Inventing an experience entry around a passing mention is a worse
   mistake than missing a real one.
6. Nothing is saved until you review, edit and confirm each candidate on the review
   screen.

**Technical note on the model:** `gpt-oss-120b` (the default model) "reasons" before
answering, and on Groq's free tier (8,000 tokens/minute) that reasoning has to be
kept to a minimum or it runs out of budget before finishing. This was tested
explicitly with an ambiguous case (a personal project with no clear dates, a
technology mentioned only in passing) and minimal reasoning classified everything
correctly. This isn't a quality trade-off, it's the only thing that works reliably
within this limit. *(See Next version improvements below: a non-reasoning-constrained
open source model will be evaluated longer term.)*

## Next version improvements (v1.1)

This list is not final. It grows as real feedback comes in from using the app on
actual job applications. Anything that doesn't make it into v1.1 moves to a later
version once v1.1 itself is done.

- Evaluate an open source model that isn't limited by "reasoning" burning through
  Groq's free-tier token budget before finishing (see *What criteria the AI
  follows* above for why `gpt-oss-120b` needs minimal reasoning today).
- Back the CV-import translation with a dictionary, such as Oxford or Cambridge,
  instead of leaving it entirely to the model's judgement.
- Log the real feedback from each company (what stage you were rejected at, what
  they told you) so the system can suggest concrete improvements to your profile.
- Restore a profile from a `.zip` backup. The download side is done (see
  *Status* above); restoring needs its own confirmation screen first, since
  it replaces whatever profile is already on that computer.

## Development

```bash
pip install -r requirements.txt
python -m pytest tests/ -q
python run.py  # serves the web app at http://127.0.0.1:5000
```

## Desktop app

Work in progress: a single executable (no installer) that opens the app in its own
window instead of a browser tab, using [pywebview](https://pywebview.flowrl.com/).
No release has been published yet — `.github/workflows/build-desktop.yml` builds
both a `.exe` and a `.app` when a `v*` tag is pushed.

```bash
pip install -r requirements-desktop.txt
python desktop.py       # try it from source
pyinstaller --noconfirm desktop.spec   # builds dist/Ancla.exe (or .app on macOS)
```

PyInstaller doesn't cross-compile for a different OS than the one running it: a
`.exe` is built on Windows, a `.app` on macOS. `.github/workflows/build-desktop.yml`
builds both at once in the cloud (one per OS) when triggered manually or when a
`v*` tag is pushed.

## License

AGPL-3.0. If you run a modified version of Ancla as a network service, you
must make your changes available to its users — the same guarantee that
stops anyone from taking this code, closing it, and competing with it in
secret.
