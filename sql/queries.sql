-- 1. Overall conversion by variant
SELECT variant,
       COUNT(*)                         AS sessions,
       SUM(converted)                   AS conversions,
       ROUND(AVG(converted) * 100, 2)   AS conv_rate_pct
FROM sessions
GROUP BY variant;

-- 2. Segment by device
SELECT device, variant,
       COUNT(*)                         AS sessions,
       SUM(converted)                   AS conversions,
       ROUND(AVG(converted) * 100, 2)   AS conv_rate_pct
FROM sessions
GROUP BY device, variant
ORDER BY device, variant;

-- 3. Segment by city
SELECT city, variant,
       COUNT(*)                         AS sessions,
       SUM(converted)                   AS conversions,
       ROUND(AVG(converted) * 100, 2)   AS conv_rate_pct
FROM sessions
GROUP BY city, variant
ORDER BY city, variant;

-- 4. Revenue per session by variant
SELECT variant,
       ROUND(SUM(order_value), 2)       AS revenue,
       ROUND(SUM(order_value) * 1.0 / COUNT(*), 2) AS revenue_per_session
FROM sessions
GROUP BY variant;

-- 5. Checkout funnel with step-to-step conversion (CTE + window function)
WITH steps(step, label) AS (
    VALUES (1, 'Cart viewed'), (2, 'Shipping details'), (3, 'Payment details'), (4, 'Order placed')
),
reached AS (
    SELECT st.step, st.label, s.variant, COUNT(*) AS sessions
    FROM sessions s JOIN steps st ON s.furthest_step >= st.step
    GROUP BY st.step, st.label, s.variant
)
SELECT step, label, variant, sessions,
       ROUND(sessions * 1.0 / LAG(sessions) OVER (PARTITION BY variant ORDER BY step), 4) AS step_conversion
FROM reached
ORDER BY variant, step;

-- 6. Running (cumulative) totals by day with window functions
SELECT session_date, variant,
       COUNT(*) AS n, SUM(converted) AS x,
       SUM(COUNT(*))       OVER (PARTITION BY variant ORDER BY session_date) AS cum_n,
       SUM(SUM(converted)) OVER (PARTITION BY variant ORDER BY session_date) AS cum_x
FROM sessions
GROUP BY session_date, variant;

-- 7. Week-by-week conversion (novelty-effect check)
SELECT CAST((julianday(session_date) - julianday('2026-03-01')) / 7 AS INTEGER) + 1 AS week,
       variant, COUNT(*) AS n, SUM(converted) AS x
FROM sessions
GROUP BY week, variant;
