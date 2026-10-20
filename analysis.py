"""Core stats: SQL load/segmentation, SRM check, two-proportion z-test, 95% CI."""
import contextvars, hashlib, os, sqlite3, tempfile
import numpy as np, pandas as pd
from scipy import stats

DB = "data/greencart.db"
_DB = contextvars.ContextVar("db", default=None)   # per-session filtered database (set by use_filter)

def load_db(csv="data/sessions.csv", db=DB, schema="sql/schema.sql"):
    df = pd.read_csv(csv)
    with sqlite3.connect(db) as con:
        con.executescript(open(schema).read())
        df.to_sql("sessions", con, if_exists="append", index=False)

def q(sql, db=None):
    with sqlite3.connect(db or _DB.get() or DB) as con:
        return pd.read_sql(sql, con)

def use_filter(cities=None, devices=None):
    """Point every query at a filtered copy of the sessions table (per Streamlit session). No filter -> full data."""
    cities, devices = sorted(cities or []), sorted(devices or [])
    if not cities and not devices:
        _DB.set(None)
        return DB
    stamp = int(os.path.getmtime(DB))
    key = hashlib.md5(f"{cities}|{devices}|{stamp}".encode()).hexdigest()[:10]
    path = os.path.join(tempfile.gettempdir(), f"greencart_{key}.db")
    if not os.path.exists(path):
        df = q("SELECT * FROM sessions", db=DB)
        if cities:
            df = df[df.city.isin(cities)]
        if devices:
            df = df[df.device.isin(devices)]
        with sqlite3.connect(path) as con:
            con.executescript(open("sql/schema.sql").read())
            df.to_sql("sessions", con, if_exists="append", index=False)
    _DB.set(path)
    return path

def z_test(x1, n1, x2, n2, alpha=0.05):
    """Two-proportion z-test (pooled). Group 1 = control, group 2 = treatment."""
    p1, p2 = x1 / n1, x2 / n2
    pp = (x1 + x2) / (n1 + n2)
    se_pool = np.sqrt(pp * (1 - pp) * (1 / n1 + 1 / n2))
    z = (p2 - p1) / se_pool
    p_val = 2 * (1 - stats.norm.cdf(abs(z)))
    se = np.sqrt(p1 * (1 - p1) / n1 + p2 * (1 - p2) / n2)   # unpooled for CI
    zc = stats.norm.ppf(1 - alpha / 2)
    diff = p2 - p1
    return dict(p_control=p1, p_treatment=p2, abs_lift=diff, rel_lift=diff / p1,
                z=z, p_value=p_val, ci_low=diff - zc * se, ci_high=diff + zc * se)

def sample_size(p_base, rel_mde, alpha=0.05, power=0.80):
    """Required sessions PER GROUP for a two-sided two-proportion test."""
    p2 = p_base * (1 + rel_mde)
    pbar = (p_base + p2) / 2
    za, zb = stats.norm.ppf(1 - alpha / 2), stats.norm.ppf(power)
    num = (za * np.sqrt(2 * pbar * (1 - pbar)) + zb * np.sqrt(p_base * (1 - p_base) + p2 * (1 - p2))) ** 2
    return int(np.ceil(num / (p2 - p_base) ** 2))

def revenue_test():
    """Guardrail: revenue per session, Welch t-test (control vs treatment)."""
    d = q("SELECT variant, order_value FROM sessions")
    a = d[d.variant == "control"].order_value
    b = d[d.variant == "treatment"].order_value
    t, p = stats.ttest_ind(b, a, equal_var=False)
    return dict(rps_control=a.mean(), rps_treatment=b.mean(), rel_lift=b.mean() / a.mean() - 1, p_value=p)

def srm_check(n_control, n_treatment, expected=(0.5, 0.5), alpha=0.001):
    """Chi-square goodness-of-fit on assignment counts. Flag if p < alpha."""
    total = n_control + n_treatment
    chi2, p = stats.chisquare([n_control, n_treatment], [total * expected[0], total * expected[1]])
    return dict(chi2=chi2, p_value=p, mismatch=p < alpha)

def overall(alpha=0.05):
    t = q("SELECT variant, COUNT(*) n, SUM(converted) x FROM sessions GROUP BY variant").set_index("variant")
    c, tr = t.loc["control"], t.loc["treatment"]
    return t, z_test(c.x, c.n, tr.x, tr.n, alpha), srm_check(c.n, tr.n)

def segment(col, alpha=0.05):
    """Per-segment conversion + z-test, computed from SQL aggregates."""
    d = q(f"SELECT {col} seg, variant, COUNT(*) n, SUM(converted) x FROM sessions GROUP BY {col}, variant")
    rows = []
    for seg, g in d.groupby("seg"):
        g = g.set_index("variant")
        if {"control", "treatment"} <= set(g.index):
            r = z_test(g.loc["control", "x"], g.loc["control", "n"], g.loc["treatment", "x"], g.loc["treatment", "n"], alpha)
            rows.append({col: seg, "sessions": int(g.n.sum()), **r})
    out = pd.DataFrame(rows).sort_values("rel_lift", ascending=False)
    out["p_adj"] = (out["p_value"] * len(out)).clip(upper=1)   # Bonferroni
    return out

# ---------- extended analysis ----------
def power_at(p_base, rel_mde, n, alpha=0.05):
    """Power of a two-sided two-proportion test with n sessions per group."""
    p2 = p_base * (1 + rel_mde)
    se = np.sqrt(p_base * (1 - p_base) / n + p2 * (1 - p2) / n)
    za = stats.norm.ppf(1 - alpha / 2)
    return float(stats.norm.cdf((p2 - p_base) / se - za))

def bayes(draws=200_000, seed=1):
    """Beta(1,1) posteriors for each arm. Returns P(treatment > control) and lift summary."""
    t = q("SELECT variant, COUNT(*) n, SUM(converted) x FROM sessions GROUP BY variant").set_index("variant")
    rng = np.random.default_rng(seed)
    pc = rng.beta(1 + t.loc["control", "x"], 1 + t.loc["control", "n"] - t.loc["control", "x"], draws)
    pt = rng.beta(1 + t.loc["treatment", "x"], 1 + t.loc["treatment", "n"] - t.loc["treatment", "x"], draws)
    lift = pt / pc - 1
    return dict(prob_better=float((pt > pc).mean()), lift_mean=float(lift.mean()),
                lift_lo=float(np.percentile(lift, 2.5)), lift_hi=float(np.percentile(lift, 97.5)),
                post_c=pc, post_t=pt)

def daily():
    """Daily and cumulative conversion by variant (cumulative sums via SQL window functions)."""
    d = q("""SELECT session_date, variant, COUNT(*) n, SUM(converted) x,
                    SUM(COUNT(*))       OVER (PARTITION BY variant ORDER BY session_date) cum_n,
                    SUM(SUM(converted)) OVER (PARTITION BY variant ORDER BY session_date) cum_x
             FROM sessions GROUP BY session_date, variant ORDER BY session_date""")
    out = pd.DataFrame({"session_date": sorted(d.session_date.unique())}).set_index("session_date")
    for v in ("control", "treatment"):
        s = d[d.variant == v].set_index("session_date")
        out[f"cum_n_{v}"], out[f"cum_x_{v}"] = s.cum_n, s.cum_x
        out[f"cum_rate_{v}"] = s.cum_x / s.cum_n
    out = out.ffill()
    out["cum_p"] = [z_test(r.cum_x_control, r.cum_n_control, r.cum_x_treatment, r.cum_n_treatment)["p_value"]
                    for _, r in out.iterrows()]
    return out.reset_index()

def weekly(alpha=0.05):
    """Lift by experiment week (novelty-effect check)."""
    d = q("""SELECT CAST((julianday(session_date) - julianday('2026-03-01')) / 7 AS INTEGER) + 1 AS week,
                    variant, COUNT(*) n, SUM(converted) x
             FROM sessions GROUP BY week, variant""")
    rows = []
    for wk, g in d.groupby("week"):
        g = g.set_index("variant")
        if {"control", "treatment"} <= set(g.index):
            r = z_test(g.loc["control", "x"], g.loc["control", "n"], g.loc["treatment", "x"], g.loc["treatment", "n"], alpha)
            rows.append({"week": f"Week {int(wk)}", "sessions": int(g.n.sum()), **r})
    return pd.DataFrame(rows)

def funnel(alpha=0.05):
    """Funnel by variant from SQL (CTE + LAG), plus a z-test on each step-to-step conversion."""
    d = q("""
        WITH steps(step, label) AS (
            VALUES (1,'Cart viewed'), (2,'Shipping details'), (3,'Payment details'), (4,'Order placed')),
        reached AS (
            SELECT st.step, st.label, s.variant, COUNT(*) AS sessions
            FROM sessions s JOIN steps st ON s.furthest_step >= st.step
            GROUP BY st.step, st.label, s.variant)
        SELECT step, label, variant, sessions,
               LAG(sessions) OVER (PARTITION BY variant ORDER BY step) AS prev_sessions
        FROM reached ORDER BY step, variant""")
    rows = []
    for step, g in d.groupby("step"):
        g = g.set_index("variant")
        row = {"step": int(step), "label": g.label.iloc[0],
               "control": int(g.loc["control", "sessions"]), "treatment": int(g.loc["treatment", "sessions"])}
        if step > 1:
            r = z_test(g.loc["control", "sessions"], g.loc["control", "prev_sessions"],
                       g.loc["treatment", "sessions"], g.loc["treatment", "prev_sessions"], alpha)
            row.update(step_conv_control=r["p_control"], step_conv_treatment=r["p_treatment"],
                       rel_lift=r["rel_lift"], p_value=r["p_value"])
        rows.append(row)
    return pd.DataFrame(rows)

def heatmap():
    """Relative lift by device x city plus sessions per cell."""
    d = q("""SELECT device, city, variant, COUNT(*) n, SUM(converted) x
             FROM sessions GROUP BY device, city, variant""")
    w = d.pivot_table(index=["device", "city"], columns="variant", values=["n", "x"]).fillna(0)
    rate_c = w["x"]["control"] / w["n"]["control"]
    rate_t = w["x"]["treatment"] / w["n"]["treatment"]
    res = pd.DataFrame({"lift": rate_t / rate_c - 1, "sessions": w["n"].sum(axis=1)}).reset_index()
    return res.replace([np.inf, -np.inf], np.nan)


# ---------- data validation & robustness ----------
def validate_data():
    """Data-quality checks on the experiment table (SQL). Returns a DataFrame: check, detail, passed."""
    one = lambda sql: int(q(sql).iloc[0, 0])
    checks = [
        ("No duplicate session_id", one("SELECT COUNT(*) - COUNT(DISTINCT session_id) FROM sessions"), 0),
        ("No missing values", one("""SELECT COUNT(*) FROM sessions WHERE session_id IS NULL OR variant IS NULL OR device IS NULL
                                       OR city IS NULL OR session_date IS NULL OR converted IS NULL OR order_value IS NULL"""), 0),
        ("Variant only control/treatment", one("SELECT COUNT(*) FROM sessions WHERE variant NOT IN ('control','treatment')"), 0),
        ("Converted is 0/1", one("SELECT COUNT(*) FROM sessions WHERE converted NOT IN (0,1)"), 0),
        ("Order value only on converted sessions", one("""SELECT COUNT(*) FROM sessions
                                                         WHERE (converted = 1 AND order_value <= 0) OR (converted = 0 AND order_value <> 0)"""), 0),
        ("Funnel step 4 equals converted", one("SELECT COUNT(*) FROM sessions WHERE (furthest_step = 4) <> (converted = 1)"), 0),
        ("Dates inside experiment window", one("""SELECT COUNT(*) FROM sessions
                                                 WHERE session_date < '2026-03-01' OR session_date > '2026-03-28'"""), 0),
    ]
    return pd.DataFrame([{"check": c, "issues_found": n, "passed": n == e} for c, n, e in checks])

def robustness(draws=20_000, seed=3):
    """Cross-check the z-test with other methods on the same data."""
    t = q("SELECT variant, COUNT(*) n, SUM(converted) x FROM sessions GROUP BY variant").set_index("variant")
    nc, xc, nt, xt = (int(t.loc["control", "n"]), int(t.loc["control", "x"]),
                      int(t.loc["treatment", "n"]), int(t.loc["treatment", "x"]))
    rng = np.random.default_rng(seed)
    obs = xt / nt - xc / nc
    # exact permutation distribution of treatment conversions (hypergeometric), two-sided
    perm_xt = rng.hypergeometric(xc + xt, nc + nt - xc - xt, nt, draws)
    perm_diff = perm_xt / nt - (xc + xt - perm_xt) / nc
    p_perm = float((np.abs(perm_diff) >= abs(obs)).mean())
    # bootstrap CI for the absolute difference
    bd = rng.binomial(nt, xt / nt, draws) / nt - rng.binomial(nc, xc / nc, draws) / nc
    boot = (float(np.percentile(bd, 2.5)), float(np.percentile(bd, 97.5)))
    chi2, p_chi, *_ = stats.chi2_contingency([[xc, nc - xc], [xt, nt - xt]], correction=False)
    _, p_fisher = stats.fisher_exact([[xc, nc - xc], [xt, nt - xt]])
    z = z_test(xc, nc, xt, nt)
    return pd.DataFrame([
        {"method": "Two-proportion z-test", "p_value": z["p_value"], "ci_low": z["ci_low"], "ci_high": z["ci_high"]},
        {"method": "Chi-square (2x2)", "p_value": float(p_chi), "ci_low": np.nan, "ci_high": np.nan},
        {"method": "Fisher exact", "p_value": float(p_fisher), "ci_low": np.nan, "ci_high": np.nan},
        {"method": "Permutation test", "p_value": p_perm, "ci_low": np.nan, "ci_high": np.nan},
        {"method": "Bootstrap CI", "p_value": np.nan, "ci_low": boot[0], "ci_high": boot[1]},
    ])


if __name__ == "__main__":
    load_db()
    print("Required n/group (10% base, 20% rel. MDE, 80% power):", sample_size(0.10, 0.20))
    t, res, srm = overall()
    print(t, "\n", {k: round(float(v), 4) for k, v in res.items()}, "\n", srm)
    print(validate_data())
    print(robustness())
    print(funnel())
    print(weekly()[["week", "sessions", "rel_lift", "p_value"]])
    print(segment("device")[["device", "sessions", "rel_lift", "p_value"]])
    print(segment("city")[["city", "sessions", "rel_lift", "p_value"]])
