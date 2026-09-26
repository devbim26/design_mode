# -*- coding: utf-8 -*-
"""Чистые хелперы A/B-харнесса _e2e_3d_roundtrip.py (медианы/сводка).
Живого VLM тут нет — харнесс-скрипт импортируется через importlib
(он не .py-модуль тестов, а скрипт с main())."""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _harness():
    spec = importlib.util.spec_from_file_location(
        "_threed_ab_harness", ROOT / "tests" / "_e2e_3d_roundtrip.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_median():
    H = _harness()
    assert H._median([3, 1, 2]) == 2
    assert H._median([4, 1, 2, 3]) == 2.5
    assert H._median([5]) == 5
    assert H._median([]) is None
    print("test_median OK")


def test_summarize():
    H = _harness()
    runs = [{"score": 40, "cost_usd": 0.2, "structural_ok": True,
             "agree_rate": None, "contract_issues": 2},
            {"score": 50, "cost_usd": 0.3, "structural_ok": False,
             "agree_rate": None, "contract_issues": 4},
            {"score": 45, "cost_usd": 0.25, "structural_ok": True,
             "agree_rate": None, "contract_issues": 0}]
    s = H._summarize(runs)
    assert s["median_score"] == 45, s
    assert abs(s["median_cost_usd"] - 0.25) < 1e-9
    assert s["structural_clean_rate"] == round(2 / 3, 3), s
    assert s["median_contract_issues"] == 2
    assert s["agree_rate"] is None  # baseline без ансамбля
    runs2 = runs + [{"score": 60, "cost_usd": 0.4, "structural_ok": True,
                     "agree_rate": 0.85, "contract_issues": 0}]
    s2 = H._summarize(runs2)
    assert s2["agree_rate"] == 0.85
    print("test_summarize OK")


if __name__ == "__main__":
    test_median()
    test_summarize()
    print("ALL OK")
