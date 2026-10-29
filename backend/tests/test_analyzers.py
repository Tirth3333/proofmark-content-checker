from app.analyzers.brand import analyze_brand, parse_guideline_avoids, parse_preferred
from app.analyzers.factuality import analyze_factuality
from app.analyzers.intent import analyze_intent
from app.analyzers.quality import analyze_quality
from app.analyzers.text_utils import paragraphs, removal_edit, sentences, stats
from app.models import BrandBrief, IntentBrief

from .conftest import CLEAN_TEXT


def rules(findings):
    return {f.rule for f in findings}


def assert_exact(text, findings):
    for f in findings:
        if f.evidence:
            assert text[f.evidence.start : f.evidence.end] == f.evidence.text, f
        for r in f.related:
            assert text[r.start : r.end] == r.text


# ------------------------------------------------------------ text utils
def test_sentences_keep_offsets_and_abbreviations():
    t = "Dr. Smith arrived at 3.5 p.m. on time. Then we left!\nNext line"
    ss = sentences(t)
    assert [s.text for s in ss] == ["Dr. Smith arrived at 3.5 p.m. on time.", "Then we left!", "Next line"]
    for s in ss:
        assert t[s.start : s.end] == s.text


def test_paragraphs_and_stats():
    t = "One two.\n\n\nThree four five.\n\n"
    assert [p.text for p in paragraphs(t)] == ["One two.", "Three four five."]
    assert stats(t) == {"words": 5, "characters": len(t), "paragraphs": 2, "sentences": 2}


def test_removal_edit_recapitalises_sentence_start():
    t = "Hello. Basically you sign up."
    i = t.index("Basically")
    s, e, r = removal_edit(t, i, i + len("Basically"))
    assert t[:s] + r + t[e:] == "Hello. You sign up."


# ------------------------------------------------------------ quality
def test_repeated_phrase_detected():
    t = "Our onboarding checklist saves time. The onboarding checklist saves money too. Use the onboarding checklist saves effort."
    fs = analyze_quality(t)
    rp = [f for f in fs if f.rule == "repeated_phrase"]
    assert rp and "onboarding checklist saves" in rp[0].evidence.text.lower()
    assert len(rp[0].related) >= 1
    assert_exact(t, fs)


def test_repeated_idea_across_paragraphs():
    t = (
        "Regular backups protect small businesses from losing customer records after hardware failure.\n\n"
        "Pricing varies by provider and storage size.\n\n"
        "Small businesses protect customer records from hardware failure losses with regular backups."
    )
    fs = [f for f in analyze_quality(t) if f.rule == "repeated_idea"]
    assert len(fs) == 1
    assert fs[0].evidence.text.strip().startswith("Small businesses protect")
    assert fs[0].suggestion.replacement == ""


def test_vague_and_filler_with_replacements():
    t = "In order to grow, many people use various tools. Due to the fact that it works, we like it."
    fs = analyze_quality(t)
    assert {"vague_language", "filler"} <= rules(fs)
    repl = {f.evidence.text: f.suggestion.replacement for f in fs if f.rule == "filler"}
    assert repl["In order to"] == "To"
    assert repl["Due to the fact that"] == "Because"
    assert_exact(t, fs)


def test_superlative_unsupported_vs_supported():
    assert "unsupported_superlative" in rules(analyze_quality("This is the best tool for teams."))
    assert "unsupported_superlative" not in rules(
        analyze_quality("It was rated the best tool in the 2024 G2 survey of 3,000 users.")
    )


def test_guarantee_and_placeholder_and_cutoff():
    fs = analyze_quality("Results are guaranteed. TODO add pricing.\n\nTo begin you open the app and then")
    r = rules(fs)
    assert {"guaranteed_results", "placeholder", "incomplete_explanation"} <= r


def test_inconsistent_terminology_suggests_majority_form():
    t = "Check your email. We send email daily. Reply by e-mail."
    fs = [f for f in analyze_quality(t) if f.rule == "inconsistent_terminology"]
    assert len(fs) == 1 and fs[0].evidence.text == "e-mail" and fs[0].suggestion.replacement == "email"


def test_clean_text_has_few_quality_findings():
    fs = analyze_quality(CLEAN_TEXT)
    assert all(f.severity in ("low", "info") for f in fs)
    assert len(fs) <= 1


def test_long_content_is_handled():
    para = "Teams plan sprints with shared boards and review progress weekly. "
    t = "\n\n".join(para * 8 + f"Section {i} adds detail about step {i}." for i in range(120))
    assert len(t) > 60_000
    fs = analyze_quality(t)
    assert_exact(t, fs)


# ------------------------------------------------------------ factuality
def test_claim_types_detected():
    t = (
        "According to a 2023 survey, 77% of teams use it. "
        "Studies show the method works. "
        "The laptop has 16 GB of RAM. "
        "This approach always succeeds."
    )
    fs = analyze_factuality(t)
    types = [set(f.verification.claim_types) for f in fs]
    assert {"statistic", "date", "study_or_research"} <= types[0]
    assert "study_or_research" in types[1] and fs[1].severity == "high"
    assert "product_spec" in types[2]
    assert "absolute" in types[3]
    for f in fs:
        assert f.verification.status == "needs_verification"
        assert f.verification.sources == []
        assert f.verification.suggested_source_types
    assert_exact(t, fs)


def test_no_claims_in_clean_text():
    assert analyze_factuality(CLEAN_TEXT) == []


def test_attribution_lowers_severity():
    a = analyze_factuality("Revenue grew 40% last year.")[0]
    b = analyze_factuality("Revenue grew 40% last year (Statista, 2024).")[0]
    order = ["info", "low", "medium", "high"]
    assert order.index(b.severity) < order.index(a.severity)


# ------------------------------------------------------------ intent
def test_no_brief_no_intent_findings(demo_text):
    assert analyze_intent(demo_text, IntentBrief()) == []


def test_keyword_missing_and_present():
    t = "# Guide\n\nThis article explains garden tools and how to pick them."
    assert "keyword_missing" in rules(analyze_intent(t, IntentBrief(primary_keyword="crm software")))
    assert "keyword_missing" not in rules(analyze_intent(t, IntentBrief(primary_keyword="garden tool")))


def test_missing_sections_for_how_to():
    t = "# Bake bread\n\nBread is easy to bake at home with flour, water and yeast."
    fs = analyze_intent(t, IntentBrief(primary_keyword="bake bread", page_type="how_to", search_intent="informational"))
    titles = " ".join(f.title for f in fs)
    assert "Step-by-step" in titles and "Prerequisites" in titles
    assert any(f.rule == "unanswered_question" for f in fs)


def test_internal_links_only_from_supplied_urls(demo_text):
    fs = analyze_intent(demo_text, IntentBrief(internal_links=[{"url": "/pricing", "anchor": "Pricing"}]))
    links = [f for f in fs if f.rule == "internal_link"]
    assert len(links) == 1 and links[0].suggestion.replacement == "[Pricing](/pricing)"
    assert all("http" not in (f.suggestion.replacement or "") for f in fs)


def test_cta_missing_for_conversion_objective():
    t = "# Tool\n\nThe tool helps teams plan work."
    fs = analyze_intent(t, IntentBrief(objective="Drive free trial sign ups"))
    assert "missing_cta" in rules(fs)


# ------------------------------------------------------------ brand
def test_brand_requires_user_rules(demo_text):
    assert analyze_brand(demo_text, BrandBrief()) == []


def test_preferred_and_avoid_terms():
    assert parse_preferred("use customers instead of clients\nteam members -> teammates") == [
        ("clients", "customers"), ("team members", "teammates")
    ]
    assert parse_guideline_avoids('Avoid: synergy, rockstar\nNever use "awesome"') == ["synergy", "rockstar", "awesome"]
    t = "Our Clients love the synergy. It's awesome."
    fs = analyze_brand(t, BrandBrief(preferred_terms="use customers instead of clients", guidelines='Avoid: synergy\nNever use "awesome"'))
    pref = [f for f in fs if f.rule == "preferred_term"]
    assert pref[0].suggestion.replacement == "Customers"
    assert {f.evidence.text for f in fs if f.rule == "avoid_term"} == {"synergy", "awesome"}


def test_formal_tone_expands_contractions():
    fs = analyze_brand("We don't ship on Sundays!", BrandBrief(tone="formal"))
    repl = {f.evidence.text: f.suggestion.replacement for f in fs}
    assert repl["don't"] == "do not" and repl["!"] == "."


def test_unsupported_claims_rule_only_when_enabled():
    t = "We are the best agency in town."
    assert analyze_brand(t, BrandBrief(tone="plain")) == []
    fs = analyze_brand(t, BrandBrief(forbid_unsupported_claims=True))
    assert fs and fs[0].rule == "unsupported_promise"


def test_style_drift_against_example(demo_text, demo_brief):
    fs = analyze_brand(demo_text, BrandBrief(**demo_brief["brand"]))
    assert "style_drift" in rules(fs)


def test_removal_edit_consumes_trailing_comma():
    t = "Intro.\n\nIn today's fast-paced world, choosing a tool is hard."
    f = [x for x in analyze_quality(t) if x.rule == "filler"][0]
    ev = f.evidence
    assert t[: ev.start] + f.suggestion.replacement + t[ev.end :] == "Intro.\n\nChoosing a tool is hard."


def test_every_replacement_keeps_unrelated_text(demo_text):
    """Applying any single suggestion changes only its own evidence span."""
    for f in analyze_quality(demo_text):
        if f.evidence and f.suggestion.replacement is not None:
            new = demo_text[: f.evidence.start] + f.suggestion.replacement + demo_text[f.evidence.end :]
            assert new.startswith(demo_text[: f.evidence.start]) and new.endswith(demo_text[f.evidence.end :])
            assert ", ," not in new and "  " not in new.replace("\n", "")
