import bakeoff
from app.pipeline.judge import JudgeResult
from app.providers.meta_api import CallStats
from app.schemas import Candidate, Finding, JudgeOutput
from schemas import Label


def cands():
    return [
        Candidate(mark=1, source="sam", sam_label="sticky note", box=[0, 0, 10, 10]),
        Candidate(mark=2, source="sam", sam_label="street sign", box=[20, 0, 30, 10]),
        Candidate(mark=3, source="sam", sam_label="house number", box=[40, 0, 50, 10]),
    ]


def truth(box, category="credential"):
    return Finding(id="t", marks=[], category=category, reason="r", source="judge",
                   masked=True, locked=False, box=box)


def result(**kw):
    base = dict(verdicts=[], extra_findings=[], combined_leaks=[], instruction_text=[])
    base.update(kw)
    return JudgeResult(output=JudgeOutput(**base), attempts=[CallStats("m", "chat", True, 100, est_cost_usd=0.01)])


def v(mark, sensitive, category="credential"):
    return dict(mark=mark, sensitive=sensitive, category=category, reason="r", confidence="high")


def test_judge_findings_go_through_the_real_merge():
    r = result(
        verdicts=[v(1, True), v(2, False, "benign"), v(3, True, "benign")],
        combined_leaks=[dict(marks=[2, 3], category="home_location", reason="r")],
        extra_findings=[dict(category="contact_info", reason="r", box=[60, 0, 70, 10])],
    )
    fs = bakeoff.judge_findings(r, cands(), "public")
    masked = [(f.source, f.box) for f in fs if f.masked]
    assert masked == [("judge", [0, 0, 10, 10]), ("judge", [40, 0, 50, 10]), ("combined", [20, 0, 30, 10]),
                      ("extra", [60, 0, 70, 10])]


def test_failed_judge_scores_through_fail_closed():
    cs = [Candidate(mark=1, source="sam", sam_label="sticky note", box=[0, 0, 10, 10])]
    label = Label(image_id="s01", width=100, height=100, destinations={"public": [truth([0, 0, 10, 10])]})
    run = bakeoff.score("s01", "public", 0, JudgeResult(output=None), cs, label)
    assert (run.ok, run.caught, run.total) == (False, 1, 1)  # fail closed masks the sticky note


def test_score_and_summary():
    label = Label(image_id="s01", width=100, height=100, destinations={"public": [truth([0, 0, 10, 10])]})
    run = bakeoff.score("s01", "public", 0, result(verdicts=[v(1, True)]), cands(), label)
    s = bakeoff.summarize([run])
    assert (run.caught, run.total, run.cost_usd, run.latency_ms) == (1, 1, 0.01, 100)
    assert s["recall"] == 1.0 and s["recall_by_category"] == {"credential": "1/1"}


def test_pick_uses_recall_then_latency_within_tie_window():
    s = lambda caught, p50: {"caught": caught, "p50_ms": p50}  # noqa: E731
    assert bakeoff.pick({"a": s(30, 9000), "b": s(29, 3000), "c": s(26, 1000)}) == "b"  # b ties a, faster
    assert bakeoff.pick({"a": s(30, 9000), "b": s(20, 3000)}) == "a"  # b is outside the window
