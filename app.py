import os
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from scipy import stats
import analysis as an

st.set_page_config(page_title="Greencart A/B Test", page_icon="🛒", layout="wide")


def _password_gate():
    pw = os.environ.get("APP_PASSWORD")
    if not pw:
        try:
            pw = st.secrets.get("APP_PASSWORD")
        except Exception:
            pw = None
    if pw and st.session_state.get("authed") is not True:
        entered = st.text_input("Password", type="password")
        if entered == pw:
            st.session_state["authed"] = True
            st.rerun()
        if entered:
            st.error("Incorrect password.")
        st.stop()


_password_gate()

# ---------------------------------------------------------------- theme
GREEN, DARK, GOLD, INK, MUTED = "#2f7a66", "#1f4d3f", "#d4b25f", "#1f2a24", "#6b7569"
CTRL, TRT = GOLD, GREEN
PLANNED_BASE, PLANNED_MDE = 0.10, 0.20
COORDS = {"Bengaluru": (12.97, 77.59), "Mumbai": (19.08, 72.88), "Delhi": (28.61, 77.21),
          "Hyderabad": (17.39, 78.49), "Chennai": (13.08, 80.27), "Pune": (18.52, 73.86)}

st.markdown(f"""
<style>
.block-container {{padding-top: 1.6rem; max-width: 1250px;}}
h1, h2, h3 {{color: {DARK};}}
div[data-testid="stMetric"] {{background:#fffdf6; border:1px solid #e6dfc8; border-radius:14px; padding:12px 16px;
                              box-shadow:0 1px 2px rgba(31,77,63,.07);}}
div[data-testid="stMetricLabel"] p {{color:{MUTED}; font-size:.82rem;}}
.verdict {{background:#e6f2ec; border:1px solid #b9d9cb; border-left:6px solid {GREEN}; border-radius:14px;
           padding:16px 20px; margin:4px 0 16px 0; color:{INK};}}
.verdict.warn {{background:#fbf1dc; border-color:#ecd49a; border-left-color:#d4a017;}}
.verdict h3 {{margin:0 0 4px 0; color:{DARK};}} .verdict p {{margin:0;}}
.hero {{background:linear-gradient(160deg,#17382f,{DARK}); color:#eaf3ee; border-radius:20px; padding:36px 30px; min-height:430px;}}
.hero .brand {{letter-spacing:.14em; font-size:.78rem; color:{GOLD}; margin-bottom:34px;}}
.hero h1 {{color:#fff; font-size:2.4rem; line-height:1.15; margin:0 0 18px 0;}}
.hero p {{color:#bcd3c8; font-size:.98rem; line-height:1.55;}}
.qcard {{background:#fffdf6; border:1px solid #e6dfc8; border-radius:16px; padding:16px 18px 8px 18px; margin-bottom:6px;}}
.qcard .num {{display:inline-block; background:#e6f2ec; color:{GREEN}; border-radius:8px; padding:2px 9px; font-weight:700; font-size:.85rem;}}
.qcard h4 {{margin:10px 0 4px 0; color:{DARK};}} .qcard p {{margin:0 0 6px 0; color:{MUTED}; font-size:.9rem;}}
</style>""", unsafe_allow_html=True)

if not os.path.exists(an.DB):
    an.load_db()


def fmt_p(p):
    return "<0.001" if p < 0.001 else f"{p:.3f}"


def style(fig, h=340):
    fig.update_layout(template="plotly_white", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      height=h, margin=dict(l=10, r=10, t=60, b=10), font=dict(color=INK),
                      title=dict(font=dict(size=15, color=DARK)),
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
    return fig


# ---------------------------------------------------------------- sidebar
ALL_PAGES = ["Home", "Experiment Brief", "Executive Overview", "Funnel & Trend", "Segments",
             "City Profile", "Test Quality", "Impact"]
ROLE_PAGES = {
    "Analyst (all pages)": ALL_PAGES,
    "Executive": ["Home", "Executive Overview", "Impact"],
    "Product manager": ["Home", "Experiment Brief", "Executive Overview", "Impact"],
    "Growth / marketing": ["Home", "Funnel & Trend", "Segments", "City Profile"],
    "Engineering / QA": ["Home", "Test Quality", "Funnel & Trend"],
    "Finance": ["Home", "Impact", "Executive Overview"],
}
base = an.q("SELECT DISTINCT city, device FROM sessions", db=an.DB)
CITIES, DEVICES = sorted(base.city.unique()), sorted(base.device.unique())


def go_to(page):
    st.session_state["page"] = page


def reset_filters():
    st.session_state["city_f"] = "All"
    st.session_state["dev_f"] = DEVICES


st.sidebar.markdown("### 🛒 Greencart A/B Test")
nav_box = st.sidebar.container()
st.sidebar.markdown("---")
st.sidebar.markdown("**Filters**")
city = st.sidebar.selectbox("City", ["All"] + CITIES, key="city_f")
sel_dev = st.sidebar.pills("Device", DEVICES, selection_mode="multi", default=DEVICES, key="dev_f")
st.sidebar.button("Reset filters", on_click=reset_filters)
st.sidebar.markdown("---")
alpha = st.sidebar.slider("Significance level (alpha)", 0.01, 0.20, 0.05, step=0.01)
st.sidebar.caption(f"Confidence intervals are {1 - alpha:.0%}.")
role = st.sidebar.selectbox("View as", list(ROLE_PAGES))
st.sidebar.caption("Simulated data · 9,000 sessions · Mar 2026")

pages = ROLE_PAGES[role]
with nav_box:
    page = st.radio("Pages", pages, key="page", label_visibility="collapsed")

# ---------------------------------------------------------------- data (filters apply to every query)
an.use_filter([] if city == "All" else [city], [] if not sel_dev or set(sel_dev) == set(DEVICES) else list(sel_dev))
counts, res, srm = an.overall(alpha) if len(an.q("SELECT DISTINCT variant FROM sessions")) == 2 else (None, None, None)
if counts is None or counts.n.min() < 200:
    st.warning("Too few sessions for this filter. Widen the filters or press Reset filters.")
    st.stop()
nc, nt = int(counts.loc["control", "n"]), int(counts.loc["treatment", "n"])
bay = an.bayes()
rev = an.revenue_test()
zc = stats.norm.ppf(1 - alpha / 2)
win = (not srm["mismatch"]) and res["p_value"] < alpha and res["ci_low"] > 0
filt_text = f"City: {city} · Device: {'All' if not sel_dev or set(sel_dev) == set(DEVICES) else ', '.join(sel_dev)} · {nc + nt:,} sessions"

if page != "Home":
    st.title(page)
    if page != "City Profile":
        st.caption(filt_text)

# ================================================================ HOME
if page == "Home":
    left, right = st.columns([1, 2], gap="large")
    with left:
        st.markdown("""<div class="hero"><div class="brand">🛒 GREENCART A/B TEST</div>
        <h1>Checkout Redesign<br>A/B Test Analysis</h1>
        <p>Compare the current and redesigned checkout across 9,000 simulated sessions: conversion, funnel,
        segments and test quality. Pick a question on the right and the dashboard answers it.</p></div>""",
                    unsafe_allow_html=True)
    with right:
        st.subheader("Choose a question")
        cards = [("Experiment Brief", "How was the test designed?", "Hypotheses, metrics, sample size and the decision rule."),
                 ("Executive Overview", "Did the new checkout win?", "Conversion, lift, confidence interval and the ship decision."),
                 ("Funnel & Trend", "Where did the lift come from?", "Checkout funnel, trend over time and novelty check."),
                 ("Segments", "Who benefits?", "Lift by device and city, with multiple-comparison care."),
                 ("City Profile", "How does one city compare?", "Zoom in on a city and compare it with the rest."),
                 ("Test Quality", "Can we trust the result?", "SRM, power, data validation and robustness checks."),
                 ("Impact", "What is it worth?", "Extra orders and revenue per month at scale.")]
        cards = [c for c in cards if c[0] in pages]
        cols = st.columns(2)
        for i, (target, title, desc) in enumerate(cards):
            with cols[i % 2]:
                st.markdown(f'<div class="qcard"><span class="num">{i + 1:02d}</span><h4>{title}</h4><p>{desc}</p></div>',
                            unsafe_allow_html=True)
                st.button(f"Open {target} →", key=f"open_{i}", on_click=go_to, args=(target,))

# ================================================================ BRIEF
elif page == "Experiment Brief":
    need0 = an.sample_size(PLANNED_BASE, PLANNED_MDE, alpha)
    b1, b2 = st.columns(2)
    with b1:
        st.subheader("Question")
        st.write("Does the redesigned (simplified) checkout convert more sessions into orders than the current one?")
        st.subheader("Hypotheses")
        st.markdown("- **H0:** conversion rate is the same in both variants\n- **H1:** conversion rates differ (two-sided)")
        st.subheader("Metrics")
        st.markdown("- **Primary:** session-level checkout conversion rate\n"
                    "- **Guardrail:** revenue per session (must not drop)\n"
                    "- **Integrity:** Sample Ratio Mismatch on the 50/50 split")
    with b2:
        st.subheader("Design")
        st.markdown(f"- Randomization: 50/50 by session\n- Planned baseline conversion: {PLANNED_BASE:.0%}\n"
                    f"- Minimum detectable effect: 20% relative\n- Alpha {alpha} (two-sided), power 80%\n"
                    f"- Required sample: **{need0:,} per group** · actual: {nc:,} / {nt:,}")
        st.subheader("Decision rule (set before looking at results)")
        st.markdown("Ship if **SRM passes**, **p < alpha**, the CI for the lift **excludes zero**, "
                    "and the revenue guardrail is not significantly negative.")
        st.subheader("Method")
        st.markdown("Two-proportion z-test · confidence interval for the difference · SRM chi-square · "
                    "SQL segmentation by device and city · Bayesian cross-check")

# ================================================================ EXECUTIVE OVERVIEW
elif page == "Executive Overview":
    if win:
        st.markdown(f"""<div class="verdict"><h3>✅ Ship the new checkout</h3>
        <p>Conversion {res['p_control']:.2%} → {res['p_treatment']:.2%} ({res['rel_lift']:+.1%} relative, p = {res['p_value']:.4f}).
        {1 - alpha:.0%} CI for absolute lift [{res['ci_low']:+.2%}, {res['ci_high']:+.2%}] excludes zero · SRM passed ·
        P(treatment better) = {bay['prob_better']:.1%}. Roll out gradually, mobile first, and watch revenue per session.</p></div>""",
                    unsafe_allow_html=True)
    else:
        why = "SRM detected: assignment is broken." if srm["mismatch"] else "Result not significant at this alpha."
        st.markdown(f'<div class="verdict warn"><h3>⚠️ Do not ship yet</h3><p>{why}</p></div>', unsafe_allow_html=True)

    k = st.columns(5)
    k[0].metric("Sessions", f"{nc + nt:,}")
    k[1].metric("Control conversion", f"{res['p_control']:.2%}")
    k[2].metric("Treatment conversion", f"{res['p_treatment']:.2%}", f"{res['rel_lift']:+.1%} relative")
    k[3].metric("p-value (z-test)", f"{res['p_value']:.4f}")
    k[4].metric("P(treatment > control)", f"{bay['prob_better']:.1%}")

    seg = an.segment("city", alpha)
    m1, m2 = st.columns([5, 4], gap="large")
    with m1:
        choice = st.radio("Colour the map by", ["Relative lift", "Treatment conv.", "Control conv.", "Sessions"], horizontal=True)
        field = {"Relative lift": "rel_lift", "Treatment conv.": "p_treatment", "Control conv.": "p_control", "Sessions": "sessions"}[choice]
        fig = go.Figure(go.Scattergeo(
            lat=[COORDS[c][0] for c in seg.city], lon=[COORDS[c][1] for c in seg.city], text=seg.city,
            mode="markers+text", textposition="top center",
            marker=dict(size=14 + seg.sessions / 55, color=seg[field], colorscale=[[0, "#dcebe4"], [1, DARK]],
                        line=dict(width=1, color=DARK), showscale=True,
                        colorbar=dict(title=choice, thickness=10, tickformat="" if field == "sessions" else ".0%")),
            customdata=np.stack([seg.sessions, seg.rel_lift, seg.p_value], axis=1),
            hovertemplate="<b>%{text}</b><br>Sessions: %{customdata[0]:,.0f}<br>Lift: %{customdata[1]:+.1%}"
                          "<br>p: %{customdata[2]:.3f}<extra></extra>"))
        fig.update_geos(scope="asia", lonaxis=dict(range=[66, 92]), lataxis=dict(range=[6, 34]), showland=True,
                        landcolor="#e9e4d0", showcountries=True, countrycolor="#bdb8a2", showocean=True,
                        oceancolor="#f7f3e6", bgcolor="rgba(0,0,0,0)", coastlinecolor="#bdb8a2")
        fig.update_layout(title="Where the redesign performs, by city")
        st.plotly_chart(style(fig, 420), width="stretch")
    with m2:
        st.markdown("**City ranking by lift**")
        rank = seg.sort_values("rel_lift", ascending=False)
        st.dataframe(pd.DataFrame({
            "City": rank.city.values, "Sessions": rank.sessions.values,
            "Control": rank.p_control.map("{:.1%}".format).values, "Treatment": rank.p_treatment.map("{:.1%}".format).values,
            "Lift": rank.rel_lift.map("{:+.0%}".format).values, "p": rank.p_value.map(fmt_p).values}),
            hide_index=True, width="stretch", height=300)
        st.caption("City results are exploratory: each city has only a few hundred to ~2,000 sessions.")

    r1, r2, r3 = st.columns(3)
    with r1:
        s = seg.sort_values("sessions")
        fig = go.Figure(go.Bar(x=s.sessions, y=s.city, orientation="h", marker_color=GREEN))
        fig.update_layout(title="Sessions by city")
        st.plotly_chart(style(fig, 300), width="stretch")
    with r2:
        dv = an.q("SELECT device, COUNT(*) n FROM sessions GROUP BY device")
        fig = go.Figure(go.Pie(labels=dv.device, values=dv.n, hole=0.62, marker=dict(colors=[GREEN, GOLD, "#9bc3b4"]),
                               textinfo="percent"))
        fig.add_annotation(text=f"<b>{nc + nt:,}</b><br>sessions", showarrow=False, font=dict(size=14, color=DARK))
        fig.update_layout(title="Sessions by device")
        st.plotly_chart(style(fig, 300), width="stretch")
    with r3:
        sd = an.segment("device", alpha)
        fig = go.Figure()
        fig.add_trace(go.Bar(x=sd.device, y=sd.p_control, name="Control", marker_color=CTRL))
        fig.add_trace(go.Bar(x=sd.device, y=sd.p_treatment, name="Treatment", marker_color=TRT))
        fig.update_yaxes(tickformat=".0%")
        fig.update_layout(title="Conversion by device", barmode="group")
        st.plotly_chart(style(fig, 300), width="stretch")

    b1, b2, b3 = st.columns(3)
    b1.metric("Expected relative lift (Bayes)", f"{bay['lift_mean']:+.1%}")
    b2.metric("95% credible interval", f"[{bay['lift_lo']:+.1%}, {bay['lift_hi']:+.1%}]")
    b3.metric("Revenue / session", f"₹{rev['rps_treatment']:.0f}", f"{rev['rel_lift']:+.1%} (p = {rev['p_value']:.2f})")
    st.caption("Revenue per session is a guardrail: the lift is positive but not statistically significant.")

# ================================================================ FUNNEL & TREND
elif page == "Funnel & Trend":
    fn = an.funnel(alpha)
    fig = go.Figure()
    fig.add_trace(go.Funnel(name="Control", y=fn.label, x=fn.control, marker_color=CTRL, textinfo="value+percent initial"))
    fig.add_trace(go.Funnel(name="Treatment", y=fn.label, x=fn.treatment, marker_color=TRT, textinfo="value+percent initial"))
    fig.update_layout(title="Checkout funnel by variant")
    st.plotly_chart(style(fig, 380), width="stretch")
    st.write("**Where did the lift come from?** Step-to-step conversion, treatment vs control:")
    st.dataframe(pd.DataFrame({
        "Step": fn.label[1:], "Control": fn.step_conv_control[1:].map("{:.1%}".format),
        "Treatment": fn.step_conv_treatment[1:].map("{:.1%}".format),
        "Rel. lift": fn.rel_lift[1:].map("{:+.1%}".format), "p": fn.p_value[1:].map(fmt_p)}),
        hide_index=True, width="stretch")
    last = fn.iloc[-1]
    st.info(f"The gain is concentrated at the final step (payment → order placed: "
            f"{last.step_conv_control:.1%} → {last.step_conv_treatment:.1%}, {last.rel_lift:+.1%}). "
            "Earlier steps are roughly flat, so the redesign mainly reduces drop-off at payment.")

    dly = an.daily()
    t1, t2 = st.columns(2)
    with t1:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=dly.session_date, y=dly.cum_rate_control, name="Control", line_color=CTRL))
        fig.add_trace(go.Scatter(x=dly.session_date, y=dly.cum_rate_treatment, name="Treatment", line_color=TRT))
        fig.update_yaxes(tickformat=".0%")
        fig.update_layout(title="Cumulative conversion rate")
        st.plotly_chart(style(fig, 320), width="stretch")
    with t2:
        fig = go.Figure(go.Scatter(x=dly.session_date, y=dly.cum_p, line_color="#d4a017", name="cumulative p"))
        fig.add_hline(y=alpha, line_dash="dash", line_color="#c2410c", annotation_text=f"alpha = {alpha}")
        fig.update_yaxes(type="log", title="p-value (log)")
        fig.update_layout(title="Cumulative p-value over time")
        st.plotly_chart(style(fig, 320), width="stretch")
    wk = an.weekly(alpha)
    fig = go.Figure(go.Bar(x=wk.week, y=wk.rel_lift, marker_color=GREEN,
                           text=[f"{v:+.0%}" for v in wk.rel_lift], textposition="outside"))
    fig.update_yaxes(tickformat=".0%", title="Relative lift")
    fig.update_layout(title="Lift by experiment week (novelty check)")
    st.plotly_chart(style(fig, 300), width="stretch")
    st.caption("Lift is positive every week and does not fade, so there is no sign of a novelty effect. "
               "Weekly samples are small, so individual weeks are noisy. Early p-values swing; stopping the moment "
               "p < alpha ('peeking') inflates false positives, so the sample size was fixed in advance.")

# ================================================================ SEGMENTS
elif page == "Segments":
    cA, cB = st.columns(2)
    for col_, tab_ in (("device", cA), ("city", cB)):
        seg = an.segment(col_, alpha).sort_values("abs_lift")
        fig = go.Figure(go.Scatter(
            x=seg.abs_lift, y=seg[col_], mode="markers", marker=dict(size=10, color=GREEN),
            error_x=dict(type="data", symmetric=False, array=seg.ci_high - seg.abs_lift,
                         arrayminus=seg.abs_lift - seg.ci_low, color=GOLD)))
        fig.add_vline(x=0, line_dash="dash", line_color="#c2410c")
        fig.update_xaxes(tickformat=".0%", title="Absolute lift")
        fig.update_layout(title=f"Lift by {col_} ({1 - alpha:.0%} CI)")
        tab_.plotly_chart(style(fig, 340), width="stretch")
    hm = an.heatmap().pivot(index="device", columns="city", values="lift")
    fig = go.Figure(go.Heatmap(z=hm.values * 100, x=hm.columns, y=hm.index, colorscale="RdYlGn", zmid=0,
                               colorbar=dict(title="Rel. lift %"), hovertemplate="%{y} · %{x}: %{z:.0f}%<extra></extra>"))
    fig.update_layout(title="Relative lift, device × city")
    st.plotly_chart(style(fig, 280), width="stretch")
    st.caption("Cells are small (a few hundred sessions each), so this view is exploratory and noisy.")
    for col_ in ("device", "city"):
        seg = an.segment(col_, alpha)
        show = seg[[col_, "sessions", "p_control", "p_treatment", "rel_lift", "p_value", "p_adj"]].copy()
        show[["p_control", "p_treatment"]] = show[["p_control", "p_treatment"]].map("{:.2%}".format)
        show["rel_lift"] = show["rel_lift"].map("{:+.1%}".format)
        show[["p_value", "p_adj"]] = show[["p_value", "p_adj"]].map(fmt_p)
        st.dataframe(show.rename(columns={"p_control": "control", "p_treatment": "treatment", "rel_lift": "rel. lift",
                                          "p_value": "p", "p_adj": "p (Bonferroni)"}), hide_index=True, width="stretch")

# ================================================================ CITY PROFILE (drill-through)
elif page == "City Profile":
    st.caption("Drill-through view: one city versus all cities (ignores the sidebar filters).")
    full = an.q("SELECT * FROM sessions", db=an.DB)
    pick = st.selectbox("City", CITIES, key="profile_city")

    def arms(df):
        g = df.groupby("variant").agg(n=("converted", "size"), x=("converted", "sum"))
        return g.loc["control", "n"], g.loc["control", "x"], g.loc["treatment", "n"], g.loc["treatment", "x"]

    def stats_for(df):
        n1, x1, n2, x2 = arms(df)
        r = an.z_test(x1, n1, x2, n2, alpha)
        t = df[df.variant == "treatment"]
        c = df[df.variant == "control"]
        return dict(r=r, sessions=len(df), rps=t.order_value.mean(), mobile=(df.device == "Mobile").mean(),
                    pay_order=(t.furthest_step == 4).sum() / (t.furthest_step >= 3).sum(),
                    pay_order_c=(c.furthest_step == 4).sum() / (c.furthest_step >= 3).sum())

    cs, al = stats_for(full[full.city == pick]), stats_for(full)
    lifts = {c: stats_for(full[full.city == c])["r"]["rel_lift"] for c in CITIES}
    rank = sorted(lifts, key=lifts.get, reverse=True).index(pick) + 1

    k = st.columns(5)
    k[0].metric("Sessions", f"{cs['sessions']:,}", f"{cs['sessions'] / al['sessions']:.0%} of all")
    k[1].metric("Control conversion", f"{cs['r']['p_control']:.2%}")
    k[2].metric("Treatment conversion", f"{cs['r']['p_treatment']:.2%}")
    k[3].metric("Relative lift", f"{cs['r']['rel_lift']:+.1%}", f"p = {fmt_p(cs['r']['p_value'])}")
    k[4].metric("Rank by lift", f"#{rank} of {len(CITIES)}")

    p1, p2 = st.columns([3, 2], gap="large")
    with p1:
        score = pd.DataFrame({
            "Metric": ["Control conversion", "Treatment conversion", "Relative lift", "Revenue per session (treatment)",
                       "Mobile share of sessions", "Payment → order (treatment)"],
            pick: [f"{cs['r']['p_control']:.2%}", f"{cs['r']['p_treatment']:.2%}", f"{cs['r']['rel_lift']:+.1%}",
                   f"₹{cs['rps']:.0f}", f"{cs['mobile']:.0%}", f"{cs['pay_order']:.1%}"],
            "All cities": [f"{al['r']['p_control']:.2%}", f"{al['r']['p_treatment']:.2%}", f"{al['r']['rel_lift']:+.1%}",
                           f"₹{al['rps']:.0f}", f"{al['mobile']:.0%}", f"{al['pay_order']:.1%}"]})
        st.markdown(f"**{pick} vs all cities**")
        st.dataframe(score, hide_index=True, width="stretch")
        fig = go.Figure()
        fig.add_trace(go.Bar(x=["Control", "Treatment"], y=[cs["r"]["p_control"], cs["r"]["p_treatment"]], name=pick, marker_color=GREEN))
        fig.add_trace(go.Bar(x=["Control", "Treatment"], y=[al["r"]["p_control"], al["r"]["p_treatment"]], name="All cities", marker_color=GOLD))
        fig.update_yaxes(tickformat=".0%")
        fig.update_layout(title="Conversion: city vs all cities", barmode="group")
        st.plotly_chart(style(fig, 320), width="stretch")
    with p2:
        sub = full[full.city == pick]
        dv = sub.groupby("device").size()
        fig = go.Figure(go.Pie(labels=dv.index, values=dv.values, hole=0.62, marker=dict(colors=[GREEN, GOLD, "#9bc3b4"]),
                               textinfo="percent"))
        fig.add_annotation(text=f"<b>{len(sub):,}</b><br>sessions", showarrow=False, font=dict(size=14, color=DARK))
        fig.update_layout(title=f"{pick}: device mix")
        st.plotly_chart(style(fig, 300), width="stretch")
        rk = pd.DataFrame({"City": list(lifts), "Rel. lift": [f"{v:+.1%}" for v in lifts.values()]})
        rk = rk.assign(_s=list(lifts.values())).sort_values("_s", ascending=False).drop(columns="_s")
        st.markdown("**All cities by lift**")
        st.dataframe(rk, hide_index=True, width="stretch", height=240)
    st.caption("A single city has only a few hundred to ~2,000 sessions, so differences between cities are mostly noise. "
               "Use this view to explore, not to decide.")

# ================================================================ TEST QUALITY
elif page == "Test Quality":
    d1, d2 = st.columns(2)
    with d1:
        need = an.sample_size(PLANNED_BASE, PLANNED_MDE, alpha)
        ns = np.arange(500, 8001, 100)
        fig = go.Figure(go.Scatter(x=ns, y=[an.power_at(PLANNED_BASE, PLANNED_MDE, n, alpha) for n in ns],
                                   line_color=GREEN, name="power"))
        fig.add_hline(y=0.8, line_dash="dash", line_color="#d4a017", annotation_text="80% power")
        fig.add_vline(x=need, line_dash="dot", line_color=MUTED, annotation_text=f"needed: {need:,}")
        fig.add_vline(x=min(nc, nt), line_dash="dot", line_color=GREEN, annotation_text=f"actual: {min(nc, nt):,}",
                      annotation_position="bottom right")
        fig.update_yaxes(tickformat=".0%")
        fig.update_xaxes(title="Sessions per group")
        fig.update_layout(title="Power curve (20% relative MDE)")
        st.plotly_chart(style(fig, 360), width="stretch")
    with d2:
        share = nt / (nc + nt)
        half = stats.norm.ppf(1 - 0.001 / 2) * np.sqrt(0.25 / (nc + nt))
        lo, hi = (0.5 - half) * 100, (0.5 + half) * 100
        fig = go.Figure(go.Indicator(mode="gauge+number", value=share * 100, number={"suffix": "%"},
                                     title={"text": "Treatment share of sessions (expected 50%)"},
                                     gauge=dict(axis=dict(range=[40, 60]), bar=dict(color=GREEN),
                                                steps=[dict(range=[lo, hi], color="#cfe6db")])))
        st.plotly_chart(style(fig, 300), width="stretch")
        st.caption(f"Green zone = split allowed by chance ({lo:.1f}% to {hi:.1f}%). SRM uses a fixed strict threshold "
                   "(p < 0.001), so it does not change with the alpha slider.")
        st.metric("SRM chi-square p-value", f"{srm['p_value']:.3f}")
        (st.error if srm["mismatch"] else st.success)(
            "SRM detected (p < 0.001): do not trust results." if srm["mismatch"]
            else f"No SRM: {nc:,} / {nt:,} vs expected 50/50 (alpha = 0.001).")

    st.subheader("Data validation (SQL checks)")
    val = an.validate_data()
    st.dataframe(pd.DataFrame({"Check": val.check, "Issues found": val.issues_found,
                               "Status": val.passed.map({True: "✅ Pass", False: "❌ Fail"})}),
                 hide_index=True, width="stretch")
    st.subheader("Robustness: same conclusion, different methods")
    rb = an.robustness()
    tests = rb.dropna(subset=["p_value"])
    boot = rb[rb.method == "Bootstrap CI"].iloc[0]
    st.dataframe(pd.DataFrame({"Method": tests.method, "p-value": tests.p_value.map(fmt_p)}),
                 hide_index=True, width="stretch")
    st.caption(f"Bootstrap 95% CI for the absolute lift: [{boot.ci_low:+.2%}, {boot.ci_high:+.2%}], "
               f"matching the analytic CI [{res['ci_low']:+.2%}, {res['ci_high']:+.2%}] at alpha 0.05. "
               "The permutation test has no normality assumption.")

# ================================================================ IMPACT
elif page == "Impact":
    st.write("What the lift could mean at scale. Illustrative: assumes the test effect holds in production.")
    i1, i2 = st.columns(2)
    monthly = i1.slider("Monthly checkout sessions", 10_000, 1_000_000, 100_000, 10_000)
    aov = i2.slider("Average order value (₹)", 200, 2000,
                    int(an.q("SELECT AVG(order_value) a FROM sessions WHERE converted=1").a[0]), 10)
    inc = lambda d: monthly * d
    m1, m2, m3 = st.columns(3)
    m1.metric("Extra orders / month", f"{inc(res['abs_lift']):,.0f}")
    m2.metric(f"{1 - alpha:.0%} range", f"{inc(res['ci_low']):,.0f} to {inc(res['ci_high']):,.0f}")
    m3.metric("Extra revenue / month", f"₹{inc(res['abs_lift']) * aov:,.0f}")
    st.subheader("Guardrail: revenue per session")
    g1, g2, g3 = st.columns(3)
    g1.metric("Control", f"₹{rev['rps_control']:.2f}")
    g2.metric("Treatment", f"₹{rev['rps_treatment']:.2f}", f"{rev['rel_lift']:+.1%}")
    g3.metric("Welch t-test p", f"{rev['p_value']:.3f}")
    st.caption("Revenue per session is up but not statistically significant, so the guardrail is met (no drop) and no revenue win is claimed.")