BOOK_REGISTRY: dict[str, dict] = {
    "105312772": {
        "title":   "Ongoing Crisis Communication",
        "author":  "Coombs, W.T.",
        "year":    2019,
        "edition": "5th ed.",
        "publisher": "SAGE Publications",
    },
    "bohdanov": {
        "title":   "Кризові комунікації",
        "author":  "Богданов, С.",
        "year":    2021,
        "publisher": "Академія",
    },
    "benoit": {
        "title":   "Accounts, Excuses, and Apologies",
        "author":  "Benoit, W.L.",
        "year":    2015,
        "edition": "2nd ed.",
        "publisher": "SUNY Press",
    },
    "fearn_banks": {
        "title":   "Crisis Communications: A Casebook Approach",
        "author":  "Fearn-Banks, K.",
        "year":    2017,
        "edition": "5th ed.",
        "publisher": "Routledge",
    },
    "coombs_holladay": {
        "title":   "The Handbook of Crisis Communication",
        "author":  "Coombs, W.T. & Holladay, S.J.",
        "year":    2010,
        "publisher": "Wiley-Blackwell",
    },
}


def resolve_citation(source_title: str, chapter: str) -> str:
    #Converts a raw chunk source_title like into a readable citation like

    for key, meta in BOOK_REGISTRY.items():
        if key.lower() in source_title.lower():
            year    = meta.get("year", "")
            author  = meta.get("author", source_title)
            title   = meta.get("title", source_title)
            edition = meta.get("edition", "")
            edition_str = f", {edition}" if edition else ""
            chapter_str = f" — {chapter}" if chapter else ""
            return f"{author} ({year}){edition_str}, *{title}*{chapter_str}"

    # Fallback - clean up the raw name
    clean = source_title.replace("__", " ").replace("_", " ").strip()
    return f"{clean} — {chapter}" if chapter else clean