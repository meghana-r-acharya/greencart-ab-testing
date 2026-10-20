"""Simulate GreenCart checkout A/B test sessions -> data/sessions.csv"""
import numpy as np, pandas as pd

SEED = 89
N = 9000                       # total sessions
rng = np.random.default_rng(SEED)

cities = ["Bengaluru", "Mumbai", "Delhi", "Hyderabad", "Chennai", "Pune"]
city_p = [0.24, 0.22, 0.20, 0.14, 0.11, 0.09]
devices = ["Mobile", "Desktop", "Tablet"]
device_p = [0.62, 0.31, 0.07]

# baseline conversion by device; treatment multiplies it (~20% relative lift)
base = {"Mobile": 0.085, "Desktop": 0.135, "Tablet": 0.10}
LIFT = 1.20

variant = rng.choice(["control", "treatment"], size=N, p=[0.5, 0.5])
device = rng.choice(devices, size=N, p=device_p)
u = rng.random(N)
df = pd.DataFrame({
    "session_id": np.arange(1, N + 1),
    "variant": variant,
    "device": device,
    "city": rng.choice(cities, size=N, p=city_p),
})
df["session_date"] = pd.to_datetime("2026-03-01") + pd.to_timedelta(rng.integers(0, 28, N), unit="D")
p = df["device"].map(base) * np.where(df["variant"] == "treatment", LIFT, 1.0)
df["converted"] = (u < p).astype(int)
df["order_value"] = np.where(df["converted"] == 1, rng.gamma(4, 180, N).round(2), 0.0)
# Checkout funnel depth: 1 cart viewed, 2 shipping details, 3 payment details, 4 order placed.
# Step-to-step rates (a: cart->shipping, b: shipping->payment) are close in both arms; the
# payment->order rate c is implied by each arm's realized conversion, so the gain sits at the last step.
rng2 = np.random.default_rng(SEED + 1)
ab = {"control": (0.74, 0.62), "treatment": (0.75, 0.64)}
u2 = rng2.random(N)
step = np.full(N, 4)
for v in ("control", "treatment"):
    m = (df["variant"] == v).values
    a, b = ab[v]
    conv = df.loc[m, "converted"].mean()
    c = conv / (a * b)
    d1, d2 = (1 - a) / (1 - conv), a * (1 - b) / (1 - conv)       # P(drop at step 1 / 2 | not converted)
    for i in np.where(m & (df["converted"].values == 0))[0]:
        step[i] = 1 if u2[i] < d1 else (2 if u2[i] < d1 + d2 else 3)
df["furthest_step"] = step
df.to_csv("data/sessions.csv", index=False)
print(df.groupby("variant").converted.agg(["count", "sum", "mean"]))
