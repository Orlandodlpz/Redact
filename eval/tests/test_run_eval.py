import asyncio
import time

import numpy as np

import metrics
import run_eval
from app.schemas import AnalyzeResponse, Finding
from schemas import Label, ManifestRow


def finding(box, category="credential", masked=True, source="judge"):
    return Finding(id="f", marks=[1], category=category, reason="r", source=source,
                   masked=masked, locked=False, box=box)


def truth(box, category="credential"):
    return finding(box, category)


def resp(findings, w=100, h=100, status="ok", total=1000, cost=0.06):
    return AnalyzeResponse(image_id="x", width=w, height=h, destination="public", findings=findings,
                           judge_status=status, prompt_version="judge_v1", model_ids={},
                           timings_ms={"total": total}, est_cost_usd=cost)


def row(image_id="s01", source="staged", dests=("public",)):
    return ManifestRow(image_id=image_id, source=source, license="team staged, fake data", split="dev",
                       provenance="photo", categories=[], destinations_labeled=list(dests))


def label(image_id="s01", items=(), dests=("public",), w=100, h=100):
    return Label(image_id=image_id, width=w, height=h, destinations={d: list(items) for d in dests})


def test_score_recall_and_over_redaction_use_pixels():
    lab = label(items=[truth([0, 0, 10, 10])])
    rec = run_eval.score(row(), lab, "public", resp([finding([0, 0, 10, 20])]), 0)
    assert (rec.caught, rec.total) == (1, 1)
    assert rec.over_redaction == 100 / 10000  # the extra 10x10 below the item


def test_dilation_can_rescue_a_tight_mask():
    lab = label(items=[truth([10, 10, 30, 30])])
    tight = resp([finding([12, 12, 28, 28])])
    assert run_eval.score(row(), lab, "public", tight, 0).caught == 0
    assert run_eval.score(row(), lab, "public", tight, 4).caught == 1


def test_size_mismatch_is_an_error_not_a_score():
    rec = run_eval.score(row(), label(), "public", resp([], w=50, h=50), 0)
    assert rec.error.startswith("size_mismatch") and rec.total == 0


def test_hard_negative_false_positive_flag():
    lab = label("hn1", items=[])
    hn = row("hn1", "hard_negative")
    assert run_eval.score(hn, lab, "public", resp([finding([0, 0, 5, 5])]), 0).hard_negative_fp is True
    assert run_eval.score(hn, lab, "public", resp([]), 0).hard_negative_fp is False
    assert run_eval.score(row(), label(), "public", resp([]), 0).hard_negative_fp is None


def write_case(tmp_path, image_id="s01", dests=("public",), items=()):
    (tmp_path / "data" / "images").mkdir(parents=True, exist_ok=True)
    (tmp_path / "labels").mkdir(exist_ok=True)
    (tmp_path / "data" / "images" / f"{image_id}.jpg").write_bytes(b"fake")
    (tmp_path / "labels" / f"{image_id}.json").write_text(label(image_id, items, dests).model_dump_json())


def evaluate(tmp_path, rows, system):
    return asyncio.run(run_eval.evaluate(
        rows, system, client=None, data=tmp_path / "data", labels=tmp_path / "labels",
        dilation_px=0, pacer=run_eval.Pacer(60000)))


def test_evaluate_runs_each_labeled_destination_and_records_crashes(tmp_path):
    write_case(tmp_path, "s01", dests=("public", "team"), items=[truth([0, 0, 10, 10])])
    write_case(tmp_path, "s02", items=[truth([0, 0, 10, 10])])
    calls = []

    async def system(client, image_bytes, dest):
        calls.append(dest)
        if len(calls) == 3:
            raise RuntimeError("boom with a secret in the message")
        return resp([finding([0, 0, 10, 10])])

    rows = [row("s01", dests=("public", "team")), row("s02")]
    records, skipped = evaluate(tmp_path, rows, system)
    assert sorted(calls) == ["public", "public", "team"] and skipped == []
    crashed = [r for r in records if r.error]
    assert len(crashed) == 1 and crashed[0].error == "crash:RuntimeError"  # type only, never the message
    assert "secret" not in str(crashed[0].__dict__)
    assert sum(r.caught for r in records) == 2


def test_missing_image_or_label_is_skipped_not_scored(tmp_path):
    write_case(tmp_path, "s01", items=[truth([0, 0, 10, 10])])

    async def system(client, image_bytes, dest):
        return resp([])

    records, skipped = evaluate(tmp_path, [row("s01"), row("s02"), row("s01", dests=("public", "team"))], system)
    assert "s02" in skipped and "s01:team" in skipped and len(records) == 2


def test_summarize():
    lab = label(items=[truth([0, 0, 10, 10]), truth([20, 0, 30, 10], "face")])
    ok = run_eval.score(row(), lab, "public", resp([finding([0, 0, 10, 10])], total=1000, cost=0.06), 0)
    bad = run_eval.score(row(), label(), "public", resp([], w=1, h=1), 0)
    s = run_eval.summarize([ok, bad])
    assert s["errors"] == {"size_mismatch": 1} and s["scored_runs"] == 1
    assert s["overall"] == {"caught": 1, "total": 2, "recall": 0.5}
    assert s["recall_by_category"]["face"]["caught"] == 0
    assert s["latency_ms"] == {"p50": 1000, "p90": 1000}
    assert s["cost_usd"]["per_image_run"] == 0.06


def test_pacer_spaces_starts():
    async def go():
        p = run_eval.Pacer(600)  # 0.1 s apart
        t0 = time.monotonic()
        await asyncio.gather(*[p.wait() for _ in range(4)])
        return time.monotonic() - t0

    assert 0.25 <= asyncio.run(go()) < 0.6


def test_pixel_metrics_match_box_metrics_on_clean_masks():
    mask = np.zeros((100, 100), dtype=bool)
    mask[0:10, 0:10] = True
    t = [truth([0, 0, 10, 10])]
    assert metrics.recall_by_category_px(t, mask) == {"credential": (1, 1)}
    assert metrics.over_redaction_px(t, mask) == 0.0
    assert metrics.mask_coverage([0, 0, 10, 20], mask) == 0.5


def test_destination_accuracy_separates_keep_cells_from_mask_cells():
    face, card = truth([0, 0, 10, 10], "face"), truth([20, 20, 30, 30], "payment")
    lab = Label(image_id="s01", width=100, height=100,
                destinations={"public": [face, card], "team": [card], "ai_assistant": [card]})
    # A system that masks both items everywhere is right on every mask cell, wrong on the two keep cells.
    everywhere = resp([finding([0, 0, 10, 10]), finding([20, 20, 30, 30])])
    recs = [run_eval.score(row(dests=("public", "team", "ai_assistant")), lab, d, everywhere, 0)
            for d in ("public", "team", "ai_assistant")]
    acc = run_eval.destination_accuracy(recs)
    assert acc["keep_cells"] == {"right": 0, "total": 2, "accuracy": 0.0}
    assert acc["mask_cells"] == {"right": 4, "total": 4, "accuracy": 1.0}
    assert acc["by_destination"]["public"]["accuracy"] == 1.0
    assert acc["by_destination"]["team"]["accuracy"] == 0.5
    assert acc["images"] == 1


def test_destination_accuracy_is_none_for_single_destination_labels():
    rec = run_eval.score(row(), label(items=[truth([0, 0, 10, 10])]), "public", resp([]), 0)
    assert run_eval.destination_accuracy([rec]) is None


def test_box_union_counts_a_card_whose_mask_fills_only_part_of_its_box():
    from app.pipeline.sweep import encode_rle

    m = np.zeros((100, 100), dtype=np.uint8)
    m[10:90, 10:90] = 1
    m[10:30, 10:30] = 0  # a rounded corner: the mask fills 95 percent of its own box
    m[10:30, 70:90] = 0
    m[70:90, 10:30] = 0
    m[70:90, 70:90] = 0  # now about 75 percent
    f = finding([10, 10, 90, 90]).model_copy(update={"mask_rle": encode_rle(m)})
    lab = label(items=[truth([10, 10, 90, 90])])
    rec = run_eval.score(row(), lab, "public", resp([f]), 0)
    assert (rec.caught, rec.total) == (0, 1)  # pixel rule, primary
    assert rec.by_category_box == {"credential": (1, 1)}  # box union, secondary
    assert run_eval.summarize([rec])["overall_box_union"]["recall"] == 1.0
