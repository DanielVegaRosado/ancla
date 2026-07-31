# CV Adaptativo

**Doesn't generate your CV. Selects from facts you've already verified.**

You keep a database of your experience and skills. For every job posting, the app
chooses what to show and tells you why. It never writes anything you didn't write
yourself: if the posting asks for something you don't have, it's flagged as a gap
instead of being invented.

Every adaptation is saved. Your base of facts grows, and your archive of
applications grows with it.

- Runs **on your computer**. Your data never leaves it: no accounts, no cloud.
- Uses **your own AI key**. Groq has a free tier, and several paid providers
  (OpenAI, Anthropic, Mistral, OpenRouter, or any other with a compatible API) are
  also supported.
- Gives you the text. The design stays yours (Canva or any other tool). If you don't
  have a CV design yet, there are [two starting templates](plantillas/README.md).

## Status (v1)

| Piece | Status |
|---|---|
| Data model and interfaces | ✅ |
| Profile store (YAML) | ✅ |
| Selection engine | ✅ |
| Web interface (bilingual ES/EN) | ✅ |
| CV archive | ✅ |
| Import from an existing CV (PDF/Word) | ✅ |
| Support and templates | ✅ |
| Sample profile to try the app with | ✅ |
| Multiple AI providers (Groq, OpenAI, Anthropic, Mistral, OpenRouter, custom) | ✅ |

Tested end to end, locally: creating experience and skills, defining the "About me"
template, pasting a job posting and generating the proposal with a real Groq key.
`perfil-ejemplo/` ships a complete fictional profile (experience, skills, languages
and "About me" template, in Spanish and English) so anyone who clones the repo can
try the app without writing their whole profile first.

## What competitors do that this doesn't

Checked against BetterCV, Mi CV Ideal, Rezi, Kickresume and Teal. All five share the
same pattern:

- The AI **writes or rewrites** the user's content (Kickresume generates whole
  sections "from a job title", and Rezi rewrites bullet points so they "don't sound
  templated"). That's exactly what this project refuses to do.
- Account and cloud storage are mandatory. Your application data lives on their
  server.
- A paywall: you can build the CV for free but pay to save or download it (Mi CV
  Ideal is explicit about this).
- They optimise for a "match score"/ATS number, with no readable reason behind any
  given choice.
- Templates and design *are* the product.

**What CV Adaptativo can offer instead, verifiably, not just as a claim:**

1. "Never invents" isn't a marketing promise. It's open source, so you can read
   `seleccion/motor.py` yourself and confirm that an ID missing from your profile is
   discarded no matter what the model returns.
2. An explicit reason behind every choice. None of the five competitors above
   offer this, only a score.
3. Zero account, zero cloud. Also verifiable by reading the code, not a line like
   "securely synced to the cloud."
4. Free, no paywall, using your own key. Groq's free tier costs nothing to start with.
5. Doesn't compete on templates. It leaves that to Canva (a better design tool
   than any of the five) and focuses only on the selection problem.

**One honest caveat:** "never invents, only selects from verified facts" is not, on
its own, a technical moat. It's copyable in a week. What's genuinely hard to copy
is the business model: BetterCV, Mi CV Ideal, Rezi and the rest need your data on
their cloud and a subscription to survive as companies. Free, local and no account
is commercially unviable for them, not out of ignorance, but because they'd stop
making money if they did it. That's the one real advantage they can't replicate
without stopping being what they are.

## What criteria the AI follows

There are two moments where an AI model makes decisions, and both follow the same
principle: **the guarantee comes from the code, not from an instruction the model
could ignore.**

### Adapting your profile to a job posting (`seleccion/`)

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

### Importing an existing CV (`perfil/importador.py`)

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
actual job applications.

- Evaluate an open source model that isn't limited by "reasoning" burning through
  Groq's free-tier token budget before finishing (see *What criteria the AI
  follows* above for why `gpt-oss-120b` needs minimal reasoning today).
- Back the CV-import translation with a dictionary, such as Oxford or Cambridge,
  instead of leaving it entirely to the model's judgement.

## Later (v2)

- Log the real feedback from each company (what stage you were rejected at, what
  they told you) so the system can suggest concrete improvements to your profile.
- Edit the CV proposal directly inside the app.

## Development

```bash
pip install -r requirements.txt
python -m pytest tests/ -q
python run.py  # serves the web app at http://127.0.0.1:5000
```

## Desktop app

Work in progress: a single executable (no installer) that opens the app in its own
window instead of a browser tab, using [pywebview](https://pywebview.flowrl.com/).
The current icon is a placeholder, pending the final design.

```bash
pip install -r requirements-escritorio.txt
python escritorio.py       # try it from source
pyinstaller --noconfirm escritorio.spec   # builds dist/CV Adaptativo.exe (or .app on macOS)
```

PyInstaller doesn't cross-compile for a different OS than the one running it: a
`.exe` is built on Windows, a `.app` on macOS. `.github/workflows/build-escritorio.yml`
builds both at once in the cloud (one per OS) when triggered manually or when a
`v*` tag is pushed.

## License

MIT
