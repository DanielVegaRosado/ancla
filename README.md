# Ancla

**Doesn't generate your CV. Selects from facts you've already verified.**

You keep a database of your experience and skills. For every job posting, the app
chooses what to show and tells you why. It never writes anything you didn't write
yourself, if the posting asks for something you don't have, it's flagged as a gap
instead of being invented.

Every adaptation is saved. Your base of facts grows, and your archive of
applications grows with it.

**[Try it online](https://ancla.onrender.com)** with no install at all. It runs against a shared
example profile. Free-tier hosting spins down after inactivity, so the first load can take up to
a minute. For your own data, download the app or run it locally.

- Runs **on your computer**. Your data never leaves it: no accounts, no cloud.
- Uses **your own AI key**. Groq has a free tier, and several paid providers
  (OpenAI, Anthropic, Mistral, OpenRouter, or any other with a compatible API) are
  also supported.
- Fills a ready-made template for you. Pick one of the [built-in
  designs](html-templates/README.md), see your CV laid out as a finished page, and
  save it as a PDF.
- Your whole profile downloads as a single `.zip` from Settings, whenever you want a
  backup or you're moving to another computer.
- Free and open source, and it stays that way. Paid features may show up later for
  the kind of thing that needs a server, like conversational support, but they'll be
  additions on top. What's free today stays free.

## Getting started

Two ways to run it. Pick one.

**Download it** (no Python, no terminal). Grab `Ancla.exe` for Windows,
`Ancla-macOS.zip` for macOS, or `Ancla-Linux.tar.gz` for Linux from
[Releases](../../releases/latest) and double-click it (on Linux, extract the
archive first and run the `Ancla` binary — mark it executable if your file
manager doesn't do it for you). Read *Desktop app* below first: the app isn't
code-signed yet, so Windows and macOS will warn you the first time you open it.

**Or run it from the source code**, if you'd rather:

1. Install Python 3.11 or newer if you don't already have it.
2. Clone this repository and open the `app/` folder.
3. Install the dependencies: `pip install -r requirements.txt`.
4. Start the app: `python run.py`. It opens on its own at `http://127.0.0.1:5000`.
5. Optional: run the test suite with `python -m pytest tests/ -q`.

Either way, once the app is open:

1. Go to Settings and pick an AI provider. Groq's free tier works out of the box,
   you just need an account and a key. Paste your key, and the model name too if
   you picked a provider other than Groq.
2. Fill in your profile, either by hand under "My profile" or by importing an
   existing CV (PDF or Word) and reviewing what it finds before saving it.
3. Paste a job posting under "Adapt" and generate the proposal.
4. Pick a template and see your CV laid out as a finished page. Save it as a PDF
   with your browser's own Ctrl+P. Ancla never generates the PDF itself, your
   browser does, the same as always.

## Status (v1)

| Piece                                                                        | Status |
| ---------------------------------------------------------------------------- | ------ |
| Data model and interfaces                                                    | ✅     |
| Profile store (YAML)                                                         | ✅     |
| Selection engine                                                             | ✅     |
| Web interface (bilingual ES/EN)                                              | ✅     |
| CV archive                                                                   | ✅     |
| Lay the proposal out as a printable page (browser → PDF)                    | ✅     |
| Support and template gallery                                                 | ✅     |
| Profile backup (download as`.zip`)                                         | ✅     |
| Sample profile to try the app with                                           | ✅     |
| Multiple AI providers (Groq, OpenAI, Anthropic, Mistral, OpenRouter, custom) | ✅     |

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
   templates](html-templates/README.md), never composing a page itself. Using your
   own template isn't supported yet.

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

## Desktop app

The `.exe`, `.app` and Linux binary from *Getting started* above are built with
[pywebview](https://pywebview.flowrl.com/), a single file, no installer, that
opens the app in its own window instead of a browser tab. On Linux, pywebview
uses the GTK backend (WebKitGTK), so building it there needs a few system
packages beyond `pip` — see the Linux command below.

Windows and macOS builds aren't code-signed yet, so both will warn you the
first time you open them. That's expected and doesn't mean anything is wrong.
On the regular SmartScreen prompt, click through ("more info" → "run anyway"
on Windows, right-click → open on macOS). If Windows blocks the app outright
without offering that option, you've hit Smart App Control, a stricter
Windows 11 feature that's on by default on new installs. The only way past it
right now is switching it off in Settings → Privacy & security → Windows
Security → App & browser control, and that's a one-way switch until Windows
gets reinstalled.

Prefer to build it yourself?

```bash
# Linux only — GTK + WebKit2 bindings pywebview needs, not on PyPI:
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-webkit2-4.1 gir1.2-soup-3.0

pip install -r requirements-desktop.txt
python desktop.py       # try it from source
pyinstaller --noconfirm desktop.spec   # builds dist/Ancla.exe, .app or the Linux binary
```

PyInstaller doesn't cross-compile for a different OS than the one running it: a
`.exe` is built on Windows, a `.app` on macOS, a plain binary on Linux.
`.github/workflows/build-desktop.yml` builds all three at once in the cloud
(one per OS) when triggered manually or when a `v*` tag is pushed.

## License

AGPL-3.0. If you run a modified version of Ancla as a network service, you
must make your changes available to its users, the same guarantee that
stops anyone from taking this code, closing it, and competing with it in
secret.
