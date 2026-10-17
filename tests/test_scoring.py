import pytest

import scoring
from config import FIT_DIMENSIONS

DEFAULT_W = {k: w for k, (_, w) in FIT_DIMENSIONS.items()}


def test_default_weights_sum_to_100():
    assert sum(DEFAULT_W.values()) == 100


def test_fit_total_is_weighted_sum():
    scores = {k: 10 for k in DEFAULT_W}
    assert scoring.fit_total(scores, DEFAULT_W) == 100
    scores = {k: 5 for k in DEFAULT_W}
    assert scoring.fit_total(scores, DEFAULT_W) == 50
    scores = dict.fromkeys(DEFAULT_W, 0) | {"experience": 10}
    assert scoring.fit_total(scores, DEFAULT_W) == 20


def test_fit_total_renormalises_weights():
    scores = {"experience": 10, "skills": 0}
    assert scoring.fit_total(scores, {"experience": 1, "skills": 1}) == 50
    assert scoring.fit_total(scores, {"experience": 30, "skills": 10}) == 75
    assert scoring.fit_total(scores, {"experience": 0, "skills": 0}) == 0


def test_fit_total_clamps_out_of_range_scores():
    assert scoring.fit_total({"experience": 14}, {"experience": 1}) == 100


def test_keyword_coverage_synonyms_stemming_and_weights():
    kws = [
        {"term": "demand planning", "synonyms": [], "importance": "must_have"},
        {"term": "supply chain management", "synonyms": ["SCM"], "importance": "important"},
        {"term": "Python", "synonyms": [], "importance": "important"},
    ]
    cv = "Led demand-planning reviews. Strong SCM background."
    pct, res = scoring.keyword_coverage(kws, cv)
    assert [r.found for r in res] == [True, True, False]
    assert res[1].matched_as == "SCM"
    assert pct == pytest.approx(3 / 4 * 100)


def test_keyword_no_partial_word_match():
    _, res = scoring.keyword_coverage([{"term": "R", "synonyms": [], "importance": "important"}], "Reporting role")
    assert not res[0].found


def test_structure_ignores_year_ranges_as_phone():
    cv = "EXPERIENCE\nAcme 2019 - 2021\nEDUCATION\nMBA 2023\nSKILLS\nExcel"
    _, checks = scoring.structure_score(cv)
    assert checks["phone present"] is False
    assert checks["'experience' heading"] and checks["'education' heading"] and checks["'skills' heading"]
    _, checks = scoring.structure_score(cv + "\nCall +91 98765 43210")
    assert checks["phone present"] is True


def test_quantified_score():
    pct, n, d = scoring.quantified_score(["Cut cost 12%", "Managed team", "Saved ₹2 Cr", ""])
    assert (n, d) == (2, 3)
    assert pct == pytest.approx(66.7)
    assert scoring.quantified_score([]) == (0.0, 0, 0)


def test_ats_total_matches_component_weights():
    kws = [{"term": "excel", "synonyms": [], "importance": "important"}]
    r = scoring.ats_score(kws, "SKILLS\nExcel", ["Grew sales 10%"], ["one flag"])
    expected = 0.5 * r.keywords + 0.2 * r.structure + 0.2 * r.quantified + 0.1 * r.formatting
    assert r.total == pytest.approx(round(expected, 1))
    assert r.formatting == 75


def test_story_coverage_counts_backed_unique_themes():
    stories = [{"theme": "leadership", "backed_by_cv": True}, {"theme": "leadership", "backed_by_cv": True},
               {"theme": "failure", "backed_by_cv": False}, {"theme": "teamwork", "backed_by_cv": True}]
    assert scoring.story_coverage(stories) == pytest.approx(2 / 7 * 100, abs=0.1)


def test_readiness_formula():
    assert scoring.gap_score(0) == 100 and scoring.gap_score(2) == 50 and scoring.gap_score(9) == 0
    assert scoring.readiness_score(80, 60, 100, 1) == pytest.approx(0.4 * 80 + 0.2 * 60 + 0.2 * 100 + 0.2 * 75)
