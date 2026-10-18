"""Small text helpers shared by entity resolution and grounding (T08)."""
import re
import unicodedata

TITLE_TOKENS = frozenset({"prof", "dr", "phd", "md", "msc", "med", "pd", "mag", "dipl", "ing"})


def norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).casefold()
    return re.sub(r"\s+", " ", text).strip()


def name_aliases(name: str) -> set[str]:
    """Full name, name without a trailing parenthetical, and the parenthetical
    abbreviation: "Department X (DBMR)" -> {"department x (dbmr)", "department x", "dbmr"}."""
    n = norm(name)
    out = {n}
    m = re.match(r"^(.*?)\s*\(([^()]+)\)\s*$", n)
    if m:
        out |= {m.group(1).strip(), m.group(2).strip()}
    return {a for a in out if a}


def person_key(name: str) -> str:
    """Person name without academic titles: "Prof. Dr. Lena Muster" -> "lena muster"."""
    tokens = [t for t in re.split(r"[\s,.]+", norm(name)) if t and t not in TITLE_TOKENS]
    return " ".join(tokens)


def mentions_person(name: str, text: str, other_names: list[str] = ()) -> bool:
    """Full name (without titles), or surname as a whole word outside other entities'
    names ("Example" inside "Example Lab" does not name Anna Example)."""
    key = person_key(name)
    t = norm(text)
    if not key:
        return False
    if key in t:
        return True
    for other in sorted((norm(o) for o in other_names), key=len, reverse=True):
        if other and other != norm(name):
            t = t.replace(other, " ")
    surname = key.split(" ")[-1]
    return len(surname) > 2 and re.search(rf"\b{re.escape(surname)}\b", t) is not None


ABSENCE_TEXT = "Not found in the indexed sources."
