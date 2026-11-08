//! Reconciliation logic for agent anchoring coverage and independent OS witness streams (Shield).

use chrono::{DateTime, Utc};
use serde::Serialize;
use utoipa::ToSchema;

/// A Shield witness older than this is not "fresh": its stream may have stopped (the Oct 27–Nov 6
/// sensor outage is the motivating case), so coverage must not trust it as complete.
pub const WITNESS_STALENESS_SECS: i64 = 15 * 60;

#[derive(Debug, Clone, PartialEq, Eq, Serialize, ToSchema)]
pub struct WitnessSummary {
    /// Any Shield observation covered the window at all.
    pub present: bool,
    /// Gap-free (per-device contiguous sequences) AND fresh — safe to use as the denominator.
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
}

/// Pure evaluation of Shield witness records over a window.
/// Verifies per-device sequence continuity (missing sequence = suppressed/lost = incomplete)
/// and freshness against the given reference time.
pub fn evaluate_shield_witness(records: &[ShieldObsRecord], now: DateTime<Utc>) -> WitnessSummary {
    if records.is_empty() {
        return WitnessSummary {
            present: false,
            complete: false,
            witnessed: 0,
            suppressed: 0,
        };
    }

    let mut witnessed = 0i64;
    let mut suppressed = 0i64;
    let mut latest: Option<DateTime<Utc>> = None;
    let mut per_device: std::collections::HashMap<String, Vec<i64>> = std::collections::HashMap::new();

    for r in records {
        witnessed += r.executions_witnessed;
        suppressed += r.executions_suppressed;
        latest = Some(latest.map_or(r.window_end, |l| l.max(r.window_end)));
        per_device.entry(r.device_id.clone()).or_default().push(r.sequence);
    }

    // Sequences are monotonic with time, so within a `window_end >= since` slice the in-window
    // sequences must form a contiguous tail; `max - min + 1 == len` means no number is missing.
    // (device_id, sequence) is the PK, so duplicates are impossible — a short run is a real gap.
    let contiguous = per_device.values().all(|seqs| {
        let (min, max) = (seqs.iter().min().copied(), seqs.iter().max().copied());
        match (min, max) {
            (Some(lo), Some(hi)) => (hi - lo + 1) == seqs.len() as i64,
            _ => true,
        }
    });

    let fresh = latest.is_some_and(|l| (now - l).num_seconds() <= WITNESS_STALENESS_SECS);

    WitnessSummary {
        present: true,
        complete: contiguous && fresh,
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

    #[test]
    fn test_shield_witness_empty() {
        let summary = evaluate_shield_witness(&[], Utc::now());
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
            ShieldObsRecord {
                device_id: "dev-1".into(),
                sequence: 1,
                executions_witnessed: 5,
                executions_suppressed: 0,
                window_end: now - Duration::seconds(120),
            },
            ShieldObsRecord {
                device_id: "dev-1".into(),
                sequence: 2,
                executions_witnessed: 3,
                executions_suppressed: 1,
                window_end: now - Duration::seconds(60),
            },
        ];

        let summary = evaluate_shield_witness(&records, now);
        assert!(summary.present);
        assert!(summary.complete);
        assert_eq!(summary.witnessed, 8);
        assert_eq!(summary.suppressed, 1);
    }

    #[test]
    fn test_shield_witness_sequence_gap_is_incomplete() {
        let now = Utc::now();
        let records = vec![
            ShieldObsRecord {
                device_id: "dev-1".into(),
                sequence: 1,
                executions_witnessed: 5,
                executions_suppressed: 0,
                window_end: now - Duration::seconds(120),
            },
            ShieldObsRecord {
                device_id: "dev-1".into(),
                sequence: 3, // Missing sequence 2!
                executions_witnessed: 3,
                executions_suppressed: 0,
                window_end: now - Duration::seconds(60),
            },
        ];

        let summary = evaluate_shield_witness(&records, now);
        assert!(summary.present);
        assert!(!summary.complete, "A missing sequence number must mark the witness incomplete");
        assert_eq!(summary.witnessed, 8);
    }

    #[test]
    fn test_shield_witness_stale_is_incomplete() {
        let now = Utc::now();
        let records = vec![ShieldObsRecord {
            device_id: "dev-1".into(),
            sequence: 1,
            executions_witnessed: 4,
            executions_suppressed: 0,
            window_end: now - Duration::seconds(WITNESS_STALENESS_SECS + 10),
        }];

        let summary = evaluate_shield_witness(&records, now);
        assert!(summary.present);
        assert!(!summary.complete, "Observation older than staleness threshold must be incomplete");
    }

    #[test]
    fn test_shield_witness_multi_device_tail() {
        let now = Utc::now();
        let records = vec![
            ShieldObsRecord {
                device_id: "dev-1".into(),
                sequence: 10,
                executions_witnessed: 2,
                executions_suppressed: 0,
                window_end: now - Duration::seconds(50),
            },
            ShieldObsRecord {
                device_id: "dev-1".into(),
                sequence: 11,
                executions_witnessed: 2,
                executions_suppressed: 0,
                window_end: now - Duration::seconds(40),
            },
            ShieldObsRecord {
                device_id: "dev-2".into(),
                sequence: 5,
                executions_witnessed: 4,
                executions_suppressed: 0,
                window_end: now - Duration::seconds(30),
            },
            ShieldObsRecord {
                device_id: "dev-2".into(),
                sequence: 6,
                executions_witnessed: 3,
                executions_suppressed: 0,
                window_end: now - Duration::seconds(10),
            },
        ];

        let summary = evaluate_shield_witness(&records, now);
        assert!(summary.present);
        assert!(summary.complete);
        assert_eq!(summary.witnessed, 11);
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
