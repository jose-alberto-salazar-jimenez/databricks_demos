"""Unit tests for lib/severity.py. Run from src/app: `python -m pytest tests`."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib import severity as s  # noqa: E402

T = 0.70


def test_low_confidence_is_unconfirmed_and_covers_top2():
    a = s.assess("patches", 0.55, T, "Medium", runner_up="pitted_surface")
    assert a.severity == s.LOW_UNCONFIRMED
    assert a.human_review is True
    assert a.report_classes == ("patches", "pitted_surface")
    assert a.call_llm is True


def test_confident_uses_base_severity():
    for base in ("Low", "Medium", "High"):
        a = s.assess("x", 0.80, T, base, runner_up="y")
        assert a.severity == base
        assert a.human_review is False
        assert a.report_classes == ("x",)


def test_high_base_and_very_confident_is_critical():
    assert s.assess("pitted_surface", 0.95, T, "High").severity == s.CRITICAL
    assert s.assess("pitted_surface", 0.949, T, "High").severity == "High"
    assert s.assess("patches", 0.99, T, "Medium").severity == "Medium"


def test_threshold_boundary_is_inclusive():
    assert s.assess("x", 0.70, T, "Low").severity == "Low"
    assert s.assess("x", 0.6999, T, "Low").severity == s.LOW_UNCONFIRMED


def test_missing_playbook_routes_to_review_without_llm():
    a = s.assess("crazing", 0.99, T, None)
    assert a.severity == s.UNASSESSED
    assert a.human_review is True
    assert a.call_llm is False
    a_low = s.assess("crazing", 0.40, T, None, runner_up="scratches")
    assert a_low.severity == s.LOW_UNCONFIRMED and a_low.call_llm is False


def test_invalid_base_severity_treated_as_missing():
    a = s.assess("x", 0.9, T, "Severe")
    assert a.severity == s.UNASSESSED and a.call_llm is False and a.human_review is True
    assert s.assess("x", 0.9, T, " high ").severity == "High"


def test_runner_up_same_as_top_is_ignored():
    assert s.assess("x", 0.5, T, "Low", runner_up="x").report_classes == ("x",)


def test_top_k_sorted_desc_with_name_tiebreak():
    probs = {"b": 0.2, "a": 0.2, "c": 0.6}
    assert s.top_k(probs, 3) == [("c", 0.6), ("a", 0.2), ("b", 0.2)]
    assert s.top_k(probs, 1) == [("c", 0.6)]


@pytest.mark.parametrize("conf,thr", [(1.2, T), (-0.1, T), (0.5, 1.5)])
def test_out_of_range_inputs_raise(conf, thr):
    with pytest.raises(ValueError):
        s.assess("x", conf, thr, "Low")
