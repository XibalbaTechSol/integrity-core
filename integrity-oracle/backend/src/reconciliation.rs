//! Reconciliation logic for agent anchoring coverage and independent OS witness streams (Shield).

use chrono::{DateTime, Utc};
use serde::Serialize;
use utoipa::ToSchema;

/// A Shield witness older than this is not "fresh": its stream may have stopped (the Oct 27–Nov 6
/// sensor outage is the motivating case), so coverage must not trust it as complete.
pub const WITNESS_STALENESS_SECS: i64 = 15 * 60;

/// When the self-reported reconcile set is EMPTY (no intents and no outcomes — the full-bypass
/// agent of INTERFACE_CONTRACT.md §6.10, the exact case this witness exists to catch), there is no
/// reconcile timestamp to anchor the witness window to. Fall back to this fixed lookback so the
/// witness is still queried: a bypasser with zero self-reported rows must NOT read as "no witness
/// data" when Shield did in fact witness trees. Heuristic (not derived from the reconcile rows,
/// which by definition do not exist here); documented as such.
pub const DEFAULT_WITNESS_LOOKBACK_SECS: i64 = 60 * 60;

#[derive(Debug, Clone, PartialEq, Eq, Serialize, ToSchema)]
pub struct WitnessSummary {
    /// Any Shield observation covered the window at all.
    pub present: bool,
    /// Gap-free (per-device interior contiguity AND boundary-connected to history) AND fresh —
    /// safe to use as the denominator.
    pub complete: bool,
    pub witnessed: i64,
    pub suppressed: i64,
}

#[derive(Debug, Clone, sqlx::FromRow)]
pub struct ShieldObsRecord {
    pub device_id: String,
    pub sequence: i64,
    pub executions_witnessed: i64,
    pub executions_suppressed: i64,
    pub window_end: DateTime<Utc>,
    /// True when this record is for the agent coverage is being computed for. A device's sequence
    /// is numbered PER DEVICE across every agent it witnesses (Claude, Codex, Agy on one host), so
    /// chain contiguity must be judged over the device's WHOLE in-window chain, while the counts
    /// and freshness that belong to this agent come only from its own (`is_target`) rows.
    pub is_target: bool,
}

/// The reference time from which to query Shield's witness for a coverage window.
///
/// Pure: `reconcile_min` is the earliest timestamp seen among the self-reported reconcile rows
/// (so "did the witness cover this window" means the same span the self-reported side summarized).
/// When it is `None` — the full-bypass case with zero reconcile rows — fall back to a fixed
/// lookback so the witness is still consulted rather than silently skipped.
pub fn witness_query_since(
    reconcile_min: Option<DateTime<Utc>>,
    now: DateTime<Utc>,
    lookback_secs: i64,
) -> DateTime<Utc> {
    reconcile_min.unwrap_or_else(|| now - chrono::Duration::seconds(lookback_secs))
}

/// Pure evaluation of Shield witness records over a window.
///
/// `records` are the in-window observations (`window_end >= since`). `boundary_ok` is a DB-derived
/// fact the caller supplies: for every device with in-window rows, the earliest in-window sequence
/// either IS the device's chain start or its immediate predecessor row exists — i.e. the window's
/// leading edge is connected to history, not a dropped prefix (sequences 5–6 lost, 7 first in
/// window). Interior contiguity is checked here from `records`; the leading edge cannot be, because
/// the dropped rows are, by definition, absent from the in-window slice.
///
/// `records` are the device-wide in-window rows (every agent the witnessing devices saw); the
/// counts and freshness come only from `is_target` rows, while contiguity spans the whole chain.
/// `complete` requires interior contiguity AND `boundary_ok` AND freshness AND that this agent is
/// present at all. A missing/stale/gapped witness reads `complete=false`, never as perfect
/// coverage — the §6.10 guardrail: witness-unavailable is `None`, never 1.0.
pub fn evaluate_shield_witness(
    records: &[ShieldObsRecord],
    boundary_ok: bool,
    now: DateTime<Utc>,
) -> WitnessSummary {
    let mut witnessed = 0i64;
    let mut suppressed = 0i64;
    let mut latest_target: Option<DateTime<Utc>> = None;
    let mut present = false;
    let mut per_device: std::collections::HashMap<&str, Vec<i64>> = std::collections::HashMap::new();

    for r in records {
        // Contiguity is a DEVICE property: every in-window record counts toward the chain, whichever
        // agent it names, because a dropped record could belong to any of them.
        per_device.entry(r.device_id.as_str()).or_default().push(r.sequence);
        if r.is_target {
            present = true;
            witnessed += r.executions_witnessed;
            suppressed += r.executions_suppressed;
            latest_target = Some(latest_target.map_or(r.window_end, |l| l.max(r.window_end)));
        }
    }

    if !present {
        return WitnessSummary {
            present: false,
            complete: false,
            witnessed: 0,
            suppressed: 0,
        };
    }

    // Interior contiguity: within a `window_end >= since` slice the in-window sequences must form a
    // contiguous run; `max - min + 1 == len` means no number is missing BETWEEN the ends.
    // (device_id, sequence) is the PK, so duplicates are impossible — a short run is a real gap.
    let contiguous = per_device.values().all(|seqs| {
        let (min, max) = (seqs.iter().min().copied(), seqs.iter().max().copied());
        match (min, max) {
            (Some(lo), Some(hi)) => (hi - lo + 1) == seqs.len() as i64,
            _ => true,
        }
    });

    // Freshness is this agent's own: an idle agent whose last witnessed window is old is stale even
    // if the device is still reporting for other agents.
    let fresh = latest_target.is_some_and(|l| (now - l).num_seconds() <= WITNESS_STALENESS_SECS);

    WitnessSummary {
        present: true,
        complete: contiguous && boundary_ok && fresh,
        witnessed,
        suppressed,
    }
}

/// Evaluates the coverage ratio and basis label.
/// When a trusted, complete Shield witness covers the window, it is `executions_anchored / executions_witnessed`.
/// Otherwise, falls back to `executions_anchored / executions_observed` and marks `coverage_basis = "self_reported"`.
pub fn compute_coverage_ratio_and_basis(
    anchored: i64,
    observed: i64,
    witness: &WitnessSummary,
) -> (Option<f64>, &'static str) {
    if witness.complete && witness.witnessed > 0 {
        (Some(anchored as f64 / witness.witnessed as f64), "shield_witness")
    } else if observed > 0 {
        (Some(anchored as f64 / observed as f64), "self_reported")
    } else {
        (None, "self_reported")
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use chrono::Duration;

    fn rec(device: &str, seq: i64, w: i64, s: i64, end: DateTime<Utc>) -> ShieldObsRecord {
        rec_tgt(device, seq, w, s, end, true)
    }

    fn rec_tgt(device: &str, seq: i64, w: i64, s: i64, end: DateTime<Utc>, is_target: bool) -> ShieldObsRecord {
        ShieldObsRecord {
            device_id: device.into(),
            sequence: seq,
            executions_witnessed: w,
            executions_suppressed: s,
            window_end: end,
            is_target,
        }
    }

    #[test]
    fn test_shield_witness_interleaved_agents_on_one_device_stays_complete() {
        // One device numbers sequences across THREE agents it witnesses. For the target agent the
        // in-window rows are {0, 3} — which, filtered to the target, would look like a gap — but the
        // device's full chain {0,1,2,3} is contiguous, so the target agent must still read complete.
        let now = Utc::now();
        let records = vec![
            rec_tgt("dev-1", 0, 4, 1, now - Duration::seconds(80), true),  // target
            rec_tgt("dev-1", 1, 9, 0, now - Duration::seconds(70), false), // other agent
            rec_tgt("dev-1", 2, 9, 0, now - Duration::seconds(60), false), // other agent
            rec_tgt("dev-1", 3, 2, 0, now - Duration::seconds(50), true),  // target
        ];

        let summary = evaluate_shield_witness(&records, true, now);
        assert!(summary.present);
        assert!(summary.complete, "a contiguous DEVICE chain must not read as a gap for one of its agents");
        assert_eq!(summary.witnessed, 6, "counts come only from the target agent's rows (4 + 2)");
        assert_eq!(summary.suppressed, 1);
    }

    #[test]
    fn test_shield_witness_empty() {
        let summary = evaluate_shield_witness(&[], true, Utc::now());
        assert_eq!(
            summary,
            WitnessSummary {
                present: false,
                complete: false,
                witnessed: 0,
                suppressed: 0,
            }
        );
    }

    #[test]
    fn test_shield_witness_contiguous_and_fresh() {
        let now = Utc::now();
        let records = vec![
            rec("dev-1", 1, 5, 0, now - Duration::seconds(120)),
            rec("dev-1", 2, 3, 1, now - Duration::seconds(60)),
        ];

        let summary = evaluate_shield_witness(&records, true, now);
        assert!(summary.present);
        assert!(summary.complete);
        assert_eq!(summary.witnessed, 8);
        assert_eq!(summary.suppressed, 1);
    }

    #[test]
    fn test_shield_witness_sequence_gap_is_incomplete() {
        let now = Utc::now();
        let records = vec![
            rec("dev-1", 1, 5, 0, now - Duration::seconds(120)),
            rec("dev-1", 3, 3, 0, now - Duration::seconds(60)), // Missing interior sequence 2!
        ];

        let summary = evaluate_shield_witness(&records, true, now);
        assert!(summary.present);
        assert!(!summary.complete, "A missing interior sequence must mark the witness incomplete");
        assert_eq!(summary.witnessed, 8);
    }

    #[test]
    fn test_shield_witness_leading_edge_gap_is_incomplete() {
        // The in-window rows are themselves contiguous (7,8) and fresh, but the caller determined
        // the window's first sequence does NOT connect to history (sequences before 7 were dropped
        // — boundary_ok=false). This must read incomplete; an interior-only check would miss it.
        let now = Utc::now();
        let records = vec![
            rec("dev-1", 7, 5, 0, now - Duration::seconds(120)),
            rec("dev-1", 8, 3, 0, now - Duration::seconds(60)),
        ];

        let summary = evaluate_shield_witness(&records, false, now);
        assert!(summary.present);
        assert!(
            !summary.complete,
            "A dropped prefix (leading-edge gap) must mark the witness incomplete"
        );
        assert_eq!(summary.witnessed, 8);
    }

    #[test]
    fn test_shield_witness_stale_is_incomplete() {
        let now = Utc::now();
        let records = vec![rec(
            "dev-1",
            1,
            4,
            0,
            now - Duration::seconds(WITNESS_STALENESS_SECS + 10),
        )];

        let summary = evaluate_shield_witness(&records, true, now);
        assert!(summary.present);
        assert!(!summary.complete, "Observation older than staleness threshold must be incomplete");
    }

    #[test]
    fn test_shield_witness_multi_device_tail() {
        let now = Utc::now();
        let records = vec![
            rec("dev-1", 10, 2, 0, now - Duration::seconds(50)),
            rec("dev-1", 11, 2, 0, now - Duration::seconds(40)),
            rec("dev-2", 5, 4, 0, now - Duration::seconds(30)),
            rec("dev-2", 6, 3, 0, now - Duration::seconds(10)),
        ];

        let summary = evaluate_shield_witness(&records, true, now);
        assert!(summary.present);
        assert!(summary.complete);
        assert_eq!(summary.witnessed, 11);
    }

    #[test]
    fn test_witness_query_since_uses_reconcile_min_when_present() {
        let now = Utc::now();
        let reconcile_min = now - Duration::seconds(300);
        let since = witness_query_since(Some(reconcile_min), now, DEFAULT_WITNESS_LOOKBACK_SECS);
        assert_eq!(since, reconcile_min, "a real reconcile min must anchor the witness window");
    }

    #[test]
    fn test_witness_query_since_falls_back_to_lookback_on_empty_reconcile() {
        // The full-bypass case: zero reconcile rows -> None -> a bypasser must still be witnessed,
        // not skipped. The fallback window is `now - lookback`, strictly before `now`.
        let now = Utc::now();
        let since = witness_query_since(None, now, DEFAULT_WITNESS_LOOKBACK_SECS);
        assert_eq!(since, now - Duration::seconds(DEFAULT_WITNESS_LOOKBACK_SECS));
        assert!(since < now);
    }

    #[test]
    fn test_coverage_ratio_and_basis_selection() {
        // 1. Complete witness takes precedence
        let complete_witness = WitnessSummary {
            present: true,
            complete: true,
            witnessed: 10,
            suppressed: 0,
        };
        let (ratio, basis) = compute_coverage_ratio_and_basis(8, 6, &complete_witness);
        assert_eq!(basis, "shield_witness");
        assert_eq!(ratio, Some(0.8));

        // 2. Incomplete witness falls back to self_reported
        let incomplete_witness = WitnessSummary {
            present: true,
            complete: false,
            witnessed: 10,
            suppressed: 0,
        };
        let (ratio, basis) = compute_coverage_ratio_and_basis(5, 5, &incomplete_witness);
        assert_eq!(basis, "self_reported");
        assert_eq!(ratio, Some(1.0));

        // 3. Absent witness with observed outcomes
        let absent_witness = WitnessSummary {
            present: false,
            complete: false,
            witnessed: 0,
            suppressed: 0,
        };
        let (ratio, basis) = compute_coverage_ratio_and_basis(3, 4, &absent_witness);
        assert_eq!(basis, "self_reported");
        assert_eq!(ratio, Some(0.75));

        // 4. Nothing observed or witnessed -> None
        let (ratio, basis) = compute_coverage_ratio_and_basis(0, 0, &absent_witness);
        assert_eq!(basis, "self_reported");
        assert_eq!(ratio, None);
    }
}
