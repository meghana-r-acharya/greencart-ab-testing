import numpy as np
from scipy import stats
import analysis as an

def test_z_test_matches_chi_square():
    r = an.z_test(453, 4464, 553, 4536)
    table = [[453, 4464 - 453], [553, 4536 - 553]]
    chi2, p, *_ = stats.chi2_contingency(table, correction=False)
    assert np.isclose(r["z"] ** 2, chi2)
    assert np.isclose(r["p_value"], p)

def test_ci_contains_estimate_and_orders():
    r = an.z_test(100, 1000, 130, 1000)
    assert r["ci_low"] < r["abs_lift"] < r["ci_high"]

def test_srm_flags_bad_split_only():
    assert an.srm_check(5000, 4000)["mismatch"]
    assert not an.srm_check(4464, 4536)["mismatch"]

def test_sample_size_known_value():
    assert an.sample_size(0.10, 0.20) == 3841

def test_power_matches_sample_size():
    n = an.sample_size(0.10, 0.20)
    assert an.power_at(0.10, 0.20, n) >= 0.79
    assert an.power_at(0.10, 0.20, n // 2) < 0.6


def test_funnel_consistent_with_conversion():
    an.load_db()
    fn = an.funnel()
    last = fn.iloc[-1]
    t, res, _ = an.overall()
    assert last.control == t.loc["control", "x"] and last.treatment == t.loc["treatment", "x"]
    assert fn.control.is_monotonic_decreasing and fn.treatment.is_monotonic_decreasing

def test_sql_cumulative_matches_total():
    an.load_db()
    d = an.daily().iloc[-1]
    t, _, _ = an.overall()
    assert d.cum_x_control == t.loc["control", "x"] and d.cum_n_treatment == t.loc["treatment", "n"]


def test_validation_passes_on_generated_data():
    an.load_db()
    assert an.validate_data().passed.all()

def test_robustness_methods_agree():
    an.load_db()
    r = an.robustness().set_index("method")
    z = r.loc["Two-proportion z-test", "p_value"]
    assert abs(r.loc["Chi-square (2x2)", "p_value"] - z) < 1e-9
    assert abs(r.loc["Permutation test", "p_value"] - z) < 0.003
    assert r.loc["Fisher exact", "p_value"] < 0.01


def test_filter_restricts_rows_and_resets():
    an.load_db()
    total = int(an.q("SELECT COUNT(*) c FROM sessions").c[0])
    an.use_filter(cities=["Mumbai"], devices=["Mobile"])
    sub = an.q("SELECT city, device FROM sessions")
    assert 0 < len(sub) < total and set(sub.city) == {"Mumbai"} and set(sub.device) == {"Mobile"}
    an.use_filter()
    assert int(an.q("SELECT COUNT(*) c FROM sessions").c[0]) == total
