-- Records OTel aggregation temporality on metric data points.
--
-- Without it, rolling up token counts is silently wrong. OTel counters default to
-- CUMULATIVE temporality: every export carries the running total since process start, not
-- the delta since the last export. Summing data points across exports therefore counts the
-- entire total once per export — an agent flushing twice reports 2x its real usage, three
-- times reports 3x, and so on. Caught empirically: a test export of 612,400 cacheRead
-- tokens read back as 1,224,800 because force_flush and shutdown each emitted the same
-- cumulative point.
--
-- Correct rollup depends on temporality, so it has to be stored, not assumed:
--   * cumulative -> take MAX per series (monotonic, so the max IS the latest total)
--   * delta      -> SUM across data points
--
-- Known limit of the MAX approach, stated rather than hidden: if a counter resets (process
-- restart within the window), MAX reports only the highest single run rather than the sum
-- across runs, understating usage. Handling resets properly needs per-series start_time
-- tracking; that is not built.

ALTER TABLE otel_metrics
    ADD COLUMN temporality TEXT NOT NULL DEFAULT 'unspecified';

-- Rollups group by series (name + attributes) before aggregating, so index the pair.
CREATE INDEX idx_otel_metrics_series ON otel_metrics (agent_id, name, temporality);
