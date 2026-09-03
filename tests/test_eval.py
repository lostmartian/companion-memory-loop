import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.eval.judge import _parse_verdict
from scripts.eval.scenarios import ALL_SCENARIOS, CATEGORIES, FACT_SCENARIOS, PERSONA_SCENARIOS


def test_scenario_ids_unique():
    ids = [s.id for s in ALL_SCENARIOS]
    assert len(ids) == len(set(ids))


def test_categories_valid():
    for s in ALL_SCENARIOS:
        assert s.category in CATEGORIES, s.id


def test_fact_scenarios_have_distractors():
    for s in FACT_SCENARIOS:
        assert len(s.distractors) >= 1, f"{s.id} needs distractors for FPR probe"
        assert s.expected, s.id


def test_persona_scenarios_have_probe_and_expected():
    for s in PERSONA_SCENARIOS:
        assert s.probe and s.expected and len(s.turns) >= 2, s.id


def test_scenario_counts():
    assert len(FACT_SCENARIOS) >= 20
    assert len(PERSONA_SCENARIOS) >= 6


def test_parse_verdict_clean():
    assert _parse_verdict('{"verdict": "PASS", "reason": "ok"}') == {
        "verdict": "PASS",
        "reason": "ok",
    }


def test_parse_verdict_fenced_json():
    raw = '```json\n{"verdict": "FAIL", "reason": "wrong city"}\n```'
    assert _parse_verdict(raw)["verdict"] == "FAIL"


def test_parse_verdict_garbage_is_error():
    assert _parse_verdict("no json here")["verdict"] == "ERROR"


def test_parse_verdict_unknown_verdict_is_error():
    assert _parse_verdict('{"verdict": "MAYBE", "reason": "x"}')["verdict"] == "ERROR"
