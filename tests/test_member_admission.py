"""M10-03 member admission (common.admit_members): the one rule stage 2 and
stage 3 both apply. Until 2026-09-27 stage 3 skipped it and averaged every
member — the ones stage 2 had rejected included — into the book the gates judge.
"""
import numpy as np
import pandas as pd

from src.pipeline.common import MEMBER_ADMISSION_FLOOR, admit_members


def _frames(rng, n=40, k=25):
    idx = pd.bdate_range("2024-01-01", periods=n)
    cols = [f"T{i}" for i in range(k)]
    realized = pd.DataFrame(rng.normal(size=(n, k)), index=idx, columns=cols)
    mask = pd.DataFrame(True, index=idx, columns=cols)
    return idx, realized, mask


def _good(rng, fwd):
    # informative but not perfect: a perfect score has a zero-spread daily IC
    return fwd + 0.5 * rng.normal(size=fwd.shape)


def test_admits_the_informative_member_only(rng):
    idx, fwd, mask = _frames(rng)
    scores = {"good": _good(rng, fwd),
              "constant": pd.DataFrame(1.0, index=idx, columns=fwd.columns),
              "contrary": -_good(rng, fwd)}
    admitted, ics = admit_members(scores, idx, fwd, mask)
    assert list(admitted) == ["good"]
    assert set(ics) == set(scores)                        # every member is reported
    assert np.isnan(ics["constant"]["RankIC"])           # like lgbm_h5 on 2026-09-26
    assert ics["contrary"]["RankIC"] < MEMBER_ADMISSION_FLOOR


def test_gate_off_admits_everyone(rng):
    idx, fwd, mask = _frames(rng)
    scores = {"good": _good(rng, fwd), "contrary": -_good(rng, fwd)}
    admitted, _ = admit_members(scores, idx, fwd, mask, gate=False)
    assert list(admitted) == ["good", "contrary"]


def test_nothing_admitted_keeps_everyone_for_the_gates_to_judge(rng):
    idx, fwd, mask = _frames(rng)
    scores = {"contrary": -_good(rng, fwd), "constant": pd.DataFrame(1.0, index=idx, columns=fwd.columns)}
    admitted, _ = admit_members(scores, idx, fwd, mask)
    assert list(admitted) == ["contrary", "constant"]


def test_scores_that_miss_some_test_dates_do_not_raise(rng):
    # stage 3 reads its scores from parquet; they need not cover every test date
    idx, fwd, mask = _frames(rng)
    admitted, ics = admit_members({"good": _good(rng, fwd).iloc[5:]}, idx, fwd, mask)
    assert list(admitted) == ["good"] and ics["good"]["RankIC"] > 0.5
