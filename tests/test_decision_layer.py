"""Learned decision layer: tree walk, live features, plain-language reason, and its place in decide()."""

from __future__ import annotations

import pytest

from contracts import DecisionAuthority, RiskLevel
from contracts.vocabulary import FailureSeverity
from domain import PerceptionInputs, PhysicalSignals, ReasoningInputs, decide
from domain.decision import FailureMode
from realtime_native import daily_features as dfe
from realtime_native import decision_layer

def _posts(statuses):
    return [{"nama_pintu_air": f"P.A. {p.title()} 1", "status_siaga": f"Status : {s}"} for p, s in statuses.items()]


def test_water_now_reads_the_river_posts_only():
    river = sorted(dfe.RIVER_POSTS)
    statuses = {p: "Normal" for p in river}
    statuses["MANGGARAI"] = "Siaga 2"
    posts = _posts(statuses) + [{"nama_pintu_air": "Pompa Pasar Ikan", "status_siaga": "Status : Siaga 1"}]
    now = decision_layer.water_now(posts)
    assert now["w_max"] == 2 and now["w_manggarai"] == 2 and now["w_frac2"] == pytest.approx(1 / len(river))
    assert decision_layer.water_now(_posts({p: "Normal" for p in river[:5]})) is None  # fewer than 8 posts


def _daily(lag=1, p=0.05):
    return {"lag_days": lag, "city_probability": p, "water_d1": {c: 0.0 for c in dfe.WATER_DAY}}


def test_served_layer_decides_and_is_monotone():
    river = sorted(dfe.RIVER_POSTS)
    calm = {p: "Normal" for p in river}
    low = decision_layer.decide(_daily(), _posts(calm))
    assert low["risk_level"] == "SAFE" and 0.0 <= low["score"] < low["thresholds"]["PRE_ALERT"]
    wet = decision_layer.decide(_daily(p=0.3), _posts(calm))
    assert wet["score"] >= low["score"]  # a higher daily chance never lowers the risk
    high = dict(calm)
    for post in river[:5]:
        high[post] = "Siaga 2"
    raised = decision_layer.decide(_daily(p=0.3), _posts(high))
    assert raised["score"] >= wet["score"]  # more posts at Siaga 2 never lower it
    thr = raised["thresholds"]
    assert thr["PRE_ALERT"] <= thr["WARNING"] <= thr["DANGER"]
    assert set(raised["push"]) == set(decision_layer.load()["features"])


def test_decide_needs_the_posts_and_a_layer_for_the_lag():
    river = sorted(dfe.RIVER_POSTS)
    assert decision_layer.decide(_daily(lag=9), _posts({p: "Normal" for p in river})) is None
    assert decision_layer.decide(_daily(), []) is None
    assert decision_layer.decide(None, _posts({p: "Normal" for p in river})) is None


def test_switch_off(monkeypatch):
    monkeypatch.setenv("LEARNED_DECISION_ENABLED", "false")
    assert decision_layer.decide(_daily(), _posts({p: "Normal" for p in sorted(dfe.RIVER_POSTS)})) is None


def test_describe_names_the_chance_and_what_raised_it():
    learned = {"score": 0.34, "thresholds": {"PRE_ALERT": 0.22, "WARNING": 0.61, "DANGER": 0.75},
               "features": {"p": 0.17, "w_max_now": 1.0, "w_frac2_d1": 0.25},
               "push": {"p": 0.6, "w_max_now": 0.3, "w_frac2_d1": 0.01}}
    text = decision_layer.describe(learned)
    assert "peluang banjir hari ini 34%" in text and "Waspada mulai 22%, Siaga 61%, Bahaya 75%" in text
    assert "peluang model harian 17%; pos sungai tertinggi sekarang Siaga 3" in text and "kemarin" not in text
    assert "flood chance today 34%" in decision_layer.describe(learned, en=True)


def _perception(**kw):
    base = dict(physically_plausible=True, completeness=0.95, freshness_min=2.0, max_water_level_ratio=0.0,
                rainfall_1h_mm=0.0, bmkg_max_severity=0.0)
    base.update(kw)
    return PerceptionInputs(**base)


def _reasoning(level, **kw):
    base = dict(probability=0.1, confidence=0.9, model_variant="daily_kecamatan", ood_score=0.1,
                learned_level=level, learned_score=0.42, learned_path=({"feature": "p", "value": 0.1},))
    base.update(kw)
    return ReasoningInputs(**base)


def test_learned_level_is_final_after_the_safety_rules():
    d = decide(_perception(), _reasoning(RiskLevel.WARNING))
    assert d.risk_level == RiskLevel.WARNING and d.authority == DecisionAuthority.L3_LEARNED
    # The tree may say SAFE although a post sits at Siaga 2: the hand-written floor (L1.8) is replaced.
    physical = PhysicalSignals(hydrology_max_severity=0.8, hydrology_bands=True)
    d = decide(_perception(), _reasoning(RiskLevel.SAFE), physical=physical)
    assert d.risk_level == RiskLevel.SAFE and d.authority == DecisionAuthority.L3_LEARNED


def test_siaga_1_and_bmkg_severe_still_win():
    physical = PhysicalSignals(hydrology_max_severity=1.0, hydrology_bands=True)
    d = decide(_perception(), _reasoning(RiskLevel.SAFE), physical=physical)
    assert d.risk_level == RiskLevel.DANGER and d.authority == DecisionAuthority.L1_SIAGA
    d = decide(_perception(bmkg_max_severity=0.95, rainfall_1h_mm=25.0), _reasoning(RiskLevel.SAFE))
    assert d.risk_level == RiskLevel.WARNING and d.authority == DecisionAuthority.L1_7_BMKG_SAFETY_FLOOR


def test_compound_rule_and_signal_conflicts_are_replaced():
    # L1.5 (two extreme signals -> DANGER) is one of the replaced layers.
    d = decide(_perception(rainfall_1h_mm=70.0, max_water_level_ratio=0.86), _reasoning(RiskLevel.PRE_ALERT))
    assert d.authority == DecisionAuthority.L3_LEARNED and d.risk_level == RiskLevel.PRE_ALERT
    failure = FailureMode("signal_conflict", FailureSeverity.HIGH, risk_escalation=True)
    d = decide(_perception(), _reasoning(RiskLevel.SAFE), failures=[failure])
    assert d.authority == DecisionAuthority.L3_LEARNED and d.risk_level == RiskLevel.SAFE
    d = decide(_perception(), _reasoning(None), failures=[failure])
    assert d.authority == DecisionAuthority.L2_INTEGRITY  # without the layer, L2 still escalates


def test_no_learned_level_keeps_the_rule_hierarchy():
    d = decide(_perception(rainfall_1h_mm=70.0, max_water_level_ratio=0.86), _reasoning(None))
    assert d.risk_level == RiskLevel.DANGER and d.authority == DecisionAuthority.L1_5_MULTI


def test_interpretation_says_what_the_layer_saw():
    from realtime_native.inference import _risk_interpretation

    learned = {"score": 0.64, "thresholds": {"PRE_ALERT": 0.21, "WARNING": 0.61, "DANGER": 0.76},
               "features": {"p": 0.2, "w_frac2_now": 0.21}, "push": {"p": 0.4, "w_frac2_now": 0.9}}
    text = _risk_interpretation("WARNING", {}, learned=learned)
    assert text.startswith("Siaga.") and "peluang banjir hari ini 64%" in text and "21% pos sungai di Siaga 2" in text
    assert _risk_interpretation("WARNING", {}, lang="en", learned=learned).startswith("Alert.")
    assert "model keputusan" not in _risk_interpretation("WARNING", {})
