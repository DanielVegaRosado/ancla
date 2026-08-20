"""Profile and CV proposal data model.

This module is the contract every other module depends on: storage, selection
engine, archive, formatting, and web. It is defined first and in isolation,
on purpose.

All user content is bilingual (ES/EN) because a single base of facts serves
applications in both languages. The app's interface is Spanish-only in V1,
but the data is not.

Core product rule: only facts the user has written or verified live here. The
system selects and orders; it never invents new content.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, time
from enum import Enum
from typing import Generic, Literal, TypeVar

Language = Literal["es", "en"]
LANGUAGES: tuple[Language, ...] = ("es", "en")

# How many items fit in each CV section. These are defaults (the ones for a
# one-page CV), not a law: the user can change them in settings because every
# template has different space.
N_EXPERIENCES = 4
N_SKILLS = 9
N_ABOUT_ME_GROUP = 3

T = TypeVar("T")


@dataclass(frozen=True)
class Bilingual(Generic[T]):
    """The same piece of data in Spanish and English (a text, a bullet list...)."""

    es: T
    en: T

    def __getitem__(self, language: Language) -> T:
        if language not in LANGUAGES:
            raise ValueError(f"Unsupported language: {language!r}")
        return self.es if language == "es" else self.en

    @staticmethod
    def from_sidecar(valor: object, fallback: T) -> "Bilingual[T]":
        """Parses a YAML field that's either a plain scalar (applies to
        both languages) or an `{es: ..., en: ...}` mapping — the shape a
        template sidecar (`docx-templates/*.yaml`, `canva-templates/*.yaml`)
        uses for a bilingual name. Missing pieces fall back to `fallback`,
        never raise: a sidecar with a name problem should still show
        *something* rather than disappear from the list."""
        if isinstance(valor, dict):
            es = valor.get("es") or fallback
            return Bilingual(es=es, en=valor.get("en") or es)
        if valor:
            return Bilingual(es=valor, en=valor)
        return Bilingual(es=fallback, en=fallback)


# --------------------------------------------------------------------------
# Profile: the user's base of verified facts
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Experience:
    """A project or role from the personal base.

    `id` is the YAML file name without its extension, and it is used as a
    stable reference from saved proposals: if it changes, archived CVs stop
    resolving that experience.
    """

    id: str
    title: Bilingual[str]
    period: Bilingual[str]
    bullets: Bilingual[list[str]]
    stack: Bilingual[str]
    keywords: list[str] = field(default_factory=list)
    status: str = ""


@dataclass(frozen=True)
class Skill:
    """A technical skill from the personal base."""

    id: str
    name: Bilingual[str]
    category: str = ""
    keywords: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SpokenLanguage:
    """A language the user speaks, with their level.

    Distinct from the `Language` type (the CV's *output* language, "es"/"en"):
    this represents a language as a piece of profile data — English,
    French... — hence the deliberately different name.
    """

    id: str
    name: Bilingual[str]
    level: Bilingual[str]
    keywords: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Education:
    """A degree or course from the personal base.

    Same shape and same rules as `SpokenLanguage`: never sent to
    `selection/engine.py`, always shown in full on the Proposal and in a
    `.docx` export — a real CV does not trim education per job posting.
    """

    id: str
    title: Bilingual[str]
    institution: Bilingual[str]
    period: Bilingual[str]


@dataclass(frozen=True)
class AboutMe:
    """Template for the "About me" block.

    The text is fixed and written by the user; the system only fills the
    `{GROUP_A_1..3}` (concepts/domains) and `{GROUP_B_1..3}` (languages and
    specific technologies) gaps. It is the only part of the CV where the
    system composes text, and even then it is limited to inserting existing
    skill names.
    """

    template: Bilingual[str]

    def gaps(self) -> tuple[str, ...]:
        return tuple(
            f"{{GROUP_{group}_{n}}}"
            for group in ("A", "B")
            for n in range(1, N_ABOUT_ME_GROUP + 1)
        )

    def render(self, group_a: list[str], group_b: list[str], language: Language) -> str:
        """Replaces the gaps with the chosen items."""
        for name, group in (("GROUP_A", group_a), ("GROUP_B", group_b)):
            if len(group) != N_ABOUT_ME_GROUP:
                raise ValueError(
                    f"{name} needs {N_ABOUT_ME_GROUP} items, got {len(group)}"
                )
        text = self.template[language]
        for n, value in enumerate(group_a, start=1):
            text = text.replace(f"{{GROUP_A_{n}}}", value)
        for n, value in enumerate(group_b, start=1):
            text = text.replace(f"{{GROUP_B_{n}}}", value)
        return text


@dataclass(frozen=True)
class Profile:
    """The user's whole base of facts, already loaded in memory.

    `personal_skills` and `languages` are separate catalogs, deliberately
    kept outside the scope of `selection/engine.py`: they are never sent to
    the model, so they can never end up in "About me" nor among the
    technical skills — it is not a filter applied afterwards, the selection
    simply has no access to them. In the Proposal they are always shown in
    full, with no subset selected: unlike experience or technical skills, a
    real CV does not trim these down per job posting.
    """

    experiences: list[Experience] = field(default_factory=list)
    skills: list[Skill] = field(default_factory=list)
    personal_skills: list[Skill] = field(default_factory=list)
    languages: list[SpokenLanguage] = field(default_factory=list)
    education: list[Education] = field(default_factory=list)
    about_me: AboutMe | None = None
    # Not bilingual: a person's own name reads the same in any language.
    # Lives here, not in `web/settings.py`, because it is a fact about the
    # user like the rest of the profile, not local installation
    # configuration — it also fills a `.docx` template's `{{ nombre }}` tag.
    name: str = ""
    # Contact details (phone, email, city, LinkedIn...) are free-form lines,
    # not bilingual: a phone number or a URL reads the same in any language.
    contact: list[str] = field(default_factory=list)
    # The line under the name on a CV ("Data Engineer", "Ingeniero
    # Informático"...). Bilingual, unlike `contact`: a role title is part of
    # the CV's own language, not a language-neutral fact like a phone number
    # or a URL — a CV generated in English has to show the English role.
    headline: Bilingual[str] = field(default_factory=lambda: Bilingual(es="", en=""))
    # Filename of the profile photo inside the profile folder (e.g.
    # "photo.jpg"), resolved against `root` by `profile/store.py`. Empty
    # means no photo — never a path, so the profile stays a plain dataclass
    # with no notion of where it was loaded from.
    photo: str = ""

    def experience(self, id: str) -> Experience | None:
        return next((e for e in self.experiences if e.id == id), None)

    def skill(self, id: str) -> Skill | None:
        return next((s for s in self.skills if s.id == id), None)

    def personal_skill(self, id: str) -> Skill | None:
        return next((s for s in self.personal_skills if s.id == id), None)

    def language(self, id: str) -> SpokenLanguage | None:
        return next((i for i in self.languages if i.id == id), None)

    def education_entry(self, id: str) -> Education | None:
        return next((e for e in self.education if e.id == id), None)

    def is_empty(self) -> bool:
        return not self.experiences and not self.skills


# --------------------------------------------------------------------------
# Proposal: the result of adapting the profile to a job posting
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class SelectedAboutMe:
    group_a: list[str]
    group_b: list[str]
    text: str
    reason: str = ""


@dataclass(frozen=True)
class SelectedExperience:
    """Reference to a profile experience, plus why it was chosen."""

    id: str
    reason: str = ""


@dataclass(frozen=True)
class Proposal:
    """What to show on the CV for a specific job posting.

    Only stores *references* (ids) to the profile, never copies of the
    content: that way a correction to the base is reflected across the whole
    archive. The "About me" text is stored already composed, because that is
    what the user pasted in.

    `gaps` are the job posting's requirements that do not exist in the
    profile. They are kept apart from the proposal on purpose: they are
    information for the user, not material for the CV, and they are exactly
    what must never be invented.
    """

    language: Language
    about_me: SelectedAboutMe
    skills: list[str]
    experiences: list[SelectedExperience]
    skills_reason: str = ""
    gaps: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------
# Archive: proposals saved over time
# --------------------------------------------------------------------------


class CVStatus(str, Enum):
    """Where that application stands. Will feed the improvements section (v2)."""

    DRAFT = "draft"
    SENT = "sent"
    INTERVIEW = "interview"
    REJECTED = "rejected"
    ACCEPTED = "accepted"


@dataclass(frozen=True)
class SavedCV:
    """An archived adaptation, to look up, duplicate, or reuse.

    `attachments` are the final CVs the user put together on their own, in
    whatever format (PDF, docx, image): the app copies each one and links
    to it, it does not validate or convert them. More than one is normal —
    the same posting can end up with the CV exported in different
    templates, or a PDF alongside the .docx it came from.

    `time` is optional (`None` if unknown) so a CV saved before this field
    existed still reads fine: not having the time is not a broken file, just
    a piece of data that was not captured back then.
    """

    id: str
    date: date
    company: str
    position: str
    posting: str
    proposal: Proposal
    status: CVStatus = CVStatus.DRAFT
    attachments: list[str] = field(default_factory=list)
    notes: str = ""
    time: time | None = None
