"""The designer's library for one run: industry priors for the brief, plus a sample of the preset catalogs.

The planner anchors on whatever menu it is shown, so it never sees the whole catalog or the same fixed
menu twice. Each sample mixes entries that fit this kind of product with random ones from the rest."""

from __future__ import annotations

import math
import random
import re
from collections import Counter

from . import settings

SAMPLE = {"styles": (5, 5), "pairings": (5, 7), "structures": (3, 3)}  # (relevant, random) per catalog
PRIORS = 3
PRIOR_MIN_SHARE = 0.6  # keep industries scoring at least this share of the best match
CATEGORY_WEIGHT = 3  # the intake's product_category outweighs the brief's other words

STOPWORDS = set("""a an and are as at be but by can do does for from get has have how i in into is it its
just more most no not of on or our so than that the their them they this to up use we what when who will
with without you your page site website people users user visitors""".split())
SUFFIXES = ("ations", "ation", "ings", "ing", "ers", "er", "es", "s", "e", "y")


def tokens(text: str) -> list[str]:
    """Lowercase words with a crude suffix strip, so 'freelancers' meets 'freelance' and 'receipts' meets 'receipt'."""
    out = []
    for w in re.findall(r"[a-z0-9]+", text.lower()):
        if w in STOPWORDS or len(w) < 2:
            continue
        for suf in SUFFIXES:
            if w.endswith(suf) and len(w) - len(suf) >= 4:
                w = w[: -len(suf)]
                break
        out.append(w)
    return out


def bm25(query: list[str], docs: list[list[str]], k1: float = 1.2, b: float = 0.75) -> list[float]:
    n = len(docs)
    avg = sum(map(len, docs)) / n if n else 0
    df = Counter(t for d in docs for t in set(d))
    scores = []
    for d in docs:
        tf = Counter(d)
        s = 0.0
        for t in set(query):
            if t in tf:
                idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
                s += idf * tf[t] * (k1 + 1) / (tf[t] + k1 * (1 - b + b * len(d) / avg))
        scores.append(s)
    return scores


def ranked(query: list[str], items: list[dict], doc) -> list[dict]:
    """Items with a positive score, best first."""
    scores = bm25(query, [tokens(doc(i)) for i in items])
    return [i for s, i in sorted(zip(scores, items), key=lambda p: -p[0]) if s > 0]


def brief_query(brief: dict, intake: dict) -> list[str]:
    fields = [brief.get(k) or "" for k in ("product_name", "problem", "audience", "goal", "context")]
    fields += [intake.get(k) or "" for k in ("problem", "audience", "primary_action")]
    return tokens(" ".join(fields))


def industry_priors(brief: dict, intake: dict) -> list[dict]:
    """The product types this brief most resembles: what such products usually look like and what to avoid.

    Brief words alone mislead ("food bank" reads as a restaurant), so the intake's product_category leads."""
    industries = settings.presets()["industries"]["industries"]
    # The name counts twice: it is the strongest signal, and keywords alone are often one word.
    docs = [tokens(f"{i['name']} {i['name']} {' '.join(i['keywords'])} {i['considerations']}") for i in industries]
    by_category = bm25(tokens(intake.get("product_category") or ""), docs)
    by_brief = bm25(brief_query(brief, intake), docs)
    scored = sorted(((CATEGORY_WEIGHT * c + b, i) for c, b, i in zip(by_category, by_brief, industries)), key=lambda p: -p[0])
    if not scored or scored[0][0] <= 0:
        return []
    floor = PRIOR_MIN_SHARE * scored[0][0]
    return [{k: v for k, v in i.items() if k != "keywords"} for s, i in scored[:PRIORS] if s >= floor]


def _sample(rng: random.Random, relevant: list[dict], pool: list[dict], key: str) -> list[dict]:
    """`relevant` first (tagged typical), then random others from `pool` (tagged less obvious)."""
    n_rel, n_rand = SAMPLE[key]
    picked = {i["id"]: {**i, "fit": "typical for products like this"} for i in relevant[:n_rel]}
    rest = [i for i in pool if i["id"] not in picked]
    for i in rng.sample(rest, min(n_rand, len(rest))):
        picked[i["id"]] = {**i, "fit": "a less obvious option"}
    return list(picked.values())


def design_library(brief: dict, intake: dict, priors: list[dict], seed: str) -> dict:
    """Vocabulary and starting points for the planner, never constraints."""
    p = settings.presets()
    rng = random.Random(seed)
    query = brief_query(brief, intake)

    styles = p["styles"]["styles"]
    by_id = {s["id"]: s for s in styles}
    typical = [by_id[sid] for pr in priors for sid in pr["style_ids"] if sid in by_id]
    typical += ranked(query, styles, lambda s: f"{s['name']} {' '.join(s['keywords'])} {s['best_for']}")
    # A style whose own "do not use for" names this kind of product is never offered as typical.
    product = set(tokens(" ".join([intake.get("product_category") or ""] + [pr["name"] for pr in priors])))
    typical = [s for s in typical if not product & set(tokens(s["avoid_for"]))]
    style_sample = _sample(rng, list({s["id"]: s for s in typical}.values()), styles, "styles")

    pairings = p["typography"]["pairings"]
    moods = " ".join(pr["typography_mood"] for pr in priors)
    pairing_sample = _sample(rng, ranked(query + tokens(moods), pairings,
                                         lambda t: f"{t['name']} {t['hint']} {t.get('best_for', '')}"), pairings, "pairings")

    structures = [s for s in p["structures"]["structures"] if intake["page_type"] in s["page_types"]]
    st_by_id = {s["id"]: s for s in structures}
    typical_st = [st_by_id[pr["structure_id"]] for pr in priors if pr.get("structure_id") in st_by_id]
    typical_st += ranked(query, structures, lambda s: f"{s['name']} {' '.join(s['sections'])}")
    structure_sample = _sample(rng, list({s["id"]: s for s in typical_st}.values()), structures, "structures")

    return {
        "layouts_for_page_type": [{"id": l["id"], "name": l["name"], "brief": l["brief"]}
                                  for l in p["layouts"]["layouts"] if l["page_type"] == intake["page_type"]],
        "page_structures": [{k: s[k] for k in ("id", "name", "sections", "cta_placement", "color_strategy", "fit")}
                            for s in structure_sample],
        "reference_styles": [{k: s[k] for k in ("id", "name", "guidance", "best_for", "avoid_for", "modes", "fit")}
                             for s in style_sample],
        "color_directions": [{"id": d["id"], "name": d["name"], "hint": d["hint"]} for d in p["colors"]["directions"]],
        "type_pairings": [{"name": t["name"], "heading": t["heading"]["family"], "body": t["body"]["family"],
                           "mood": t["hint"], "fit": t["fit"]} for t in pairing_sample],
    }


def style_recipe(style_id: str | None) -> dict | None:
    """What the designer needs to build a reference style for real: its techniques, not just its name."""
    s = settings.style(style_id) if style_id else None
    if not s:
        return None
    return {k: s[k] for k in ("name", "guidance", "keywords", "recipe") if k in s}
