//! Anchor-coverage signal: did an agent that was actually active in the AIS reporting
//! period also get its evidence anchored on-chain during that same window?
//!
//! **Informational only — not an AIS input.** `docs/INTERFACE_CONTRACT.md` §4.3 pins the
//! AIS formula's four components (entropy/grounding/sacrifice/compliance); this module
//! deliberately does not touch `scoring-core` or add a fifth component. It exists to make
//! visible, automatically, the exact failure mode `PRODUCTION_GAPS.md` §21 and §24 record
//! a human catching by hand — telemetry kept flowing while on-chain anchoring silently
//! stopped for days. Turning this into an AIS penalty or a `Slasher` dispute trigger is a
//! separate, later decision (staking collateral is real money — see the discussion this
//! module implements the read-only first step of), not something this module does itself.
//!
//! **What this can and can't tell you.** `StateAnchor.latestTimestamp` only records the
//! *most recent* anchor across the contract's entire history, not a per-period leaf
//! count — so this cannot yet say "70% of this period's actions were anchored," only
//! "at least one anchor landed since the period started." That coarser signal is still
//! exactly what would have caught §21/§24 early: both were "activity, zero anchors for
//! days," which this flags as `Stale` on the very first computation after the anchoring
//! stopped, not after a human happens to diff `anchors.jsonl` by hand.
//!
//! **Deliberate vs. incidental is NOT decided here.** A single `Stale` reading is exactly
//! as consistent with a transient RPC outage (§24's actual root cause) as with an agent
//! that has stopped anchoring on purpose. Telling those apart needs the *history* of this
//! signal across consecutive reporting periods, which is a caller/consumer concern (e.g.
//! a future `Slasher` dispute trigger requiring N consecutive `Stale` periods, mirroring
//! `Slasher.sol`'s own "don't let one bad automated signal move funds" dispute-window
//! design) — this module only ever reports one period at a time.

use chrono::{DateTime, TimeZone, Utc};
use serde::Serialize;
use utoipa::ToSchema;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum AnchorCoverageStatus {
    /// No telemetry events in the reporting period — nothing to have anchored, so this
    /// is not evidence of anything, favorable or not. Matches the same "no activity is
    /// not evidence of misbehavior" posture `scoring-core`'s empty-batch defaults use.
    NoActivity,
    /// The agent's `StateAnchor` recorded at least one `anchorRoot` call at or after the
    /// reporting period started.
    Current,
    /// The agent had telemetry activity in the period, but its `StateAnchor`'s most
    /// recent anchor predates the period start (or the anchor is unreadable/never
    /// initialized). This is the signal that would have caught §21/§24 automatically.
    Stale,
}

#[derive(Debug, Clone, Serialize, ToSchema)]
pub struct AnchorCoverage {
    pub status: AnchorCoverageStatus,
    pub events_in_period: i64,
    /// `None` if the on-chain read failed (RPC unreachable, bad address) or the
    /// `StateAnchor` has never anchored anything (`latestEpoch == 0`) — indistinguishable
    /// from each other at this layer, both surfaced as "we don't know," never coerced
    /// into a false `Stale` or `Current`.
    pub last_anchored_at: Option<DateTime<Utc>>,
    pub last_anchored_epoch: Option<u64>,
}

/// Pure evaluation — no chain/DB access, so it's cheaply unit-testable and the caller
/// (`handlers::compute_ais_for_agent`) owns all I/O and its own error handling, matching
/// the `onchain_zk_boost_consistent` cross-check's existing pattern in that function
/// (best-effort `Option`, never fails the whole AIS response).
pub fn evaluate(
    events_in_period: i64,
    period_start: DateTime<Utc>,
    onchain_anchor_activity: Option<(u64, i64)>,
) -> AnchorCoverage {
    let last_anchored_at = onchain_anchor_activity
        .filter(|(epoch, _)| *epoch > 0)
        .and_then(|(_, ts)| Utc.timestamp_opt(ts, 0).single());
    let last_anchored_epoch = onchain_anchor_activity
        .map(|(epoch, _)| epoch)
        .filter(|e| *e > 0);

    // `StateAnchor.latestTimestamp` is a whole-second `block.timestamp`; `period_start` may
    // carry sub-second precision. Compare at second resolution so an anchor landing in the
    // same second the period started isn't spuriously read as predating it.
    let period_start_secs = period_start.timestamp();
    let status = if events_in_period <= 0 {
        AnchorCoverageStatus::NoActivity
    } else {
        match last_anchored_at {
            Some(ts) if ts.timestamp() >= period_start_secs => AnchorCoverageStatus::Current,
            _ => AnchorCoverageStatus::Stale,
        }
    };

    AnchorCoverage {
        status,
        events_in_period,
        last_anchored_at,
        last_anchored_epoch,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use chrono::Duration;

    fn t(hours_ago: i64) -> DateTime<Utc> {
        Utc::now() - Duration::hours(hours_ago)
    }

    #[test]
    fn no_events_is_no_activity_regardless_of_anchor_state() {
        let period_start = t(720); // 30 days ago
        assert_eq!(
            evaluate(0, period_start, None).status,
            AnchorCoverageStatus::NoActivity
        );
        assert_eq!(
            evaluate(0, period_start, Some((5, Utc::now().timestamp()))).status,
            AnchorCoverageStatus::NoActivity
        );
    }

    #[test]
    fn active_agent_with_recent_anchor_is_current() {
        let period_start = t(720);
        let recent = Utc::now().timestamp();
        let result = evaluate(42, period_start, Some((3, recent)));
        assert_eq!(result.status, AnchorCoverageStatus::Current);
        assert_eq!(result.last_anchored_epoch, Some(3));
    }

    #[test]
    fn active_agent_with_stale_anchor_before_period_start_is_stale() {
        let period_start = t(720); // period started 30 days ago
        let stale_anchor = (Utc::now() - Duration::days(45)).timestamp(); // anchored 45 days ago
        let result = evaluate(42, period_start, Some((1, stale_anchor)));
        assert_eq!(result.status, AnchorCoverageStatus::Stale);
    }

    #[test]
    fn active_agent_with_never_anchored_state_anchor_is_stale() {
        // latestEpoch == 0 means the StateAnchor has never had anchorRoot called on it —
        // must not be misread as "anchored at unix epoch 0".
        let period_start = t(720);
        let result = evaluate(10, period_start, Some((0, 0)));
        assert_eq!(result.status, AnchorCoverageStatus::Stale);
        assert_eq!(result.last_anchored_at, None);
        assert_eq!(result.last_anchored_epoch, None);
    }

    #[test]
    fn active_agent_with_unreadable_chain_state_is_stale_not_a_false_current() {
        // An RPC failure the caller couldn't read past is passed through as None —
        // must default to the honest "we don't know" reading (Stale), never Current.
        let period_start = t(720);
        let result = evaluate(10, period_start, None);
        assert_eq!(result.status, AnchorCoverageStatus::Stale);
        assert_eq!(result.last_anchored_at, None);
    }

    #[test]
    fn anchor_exactly_at_period_start_counts_as_current() {
        let period_start = t(720);
        let result = evaluate(5, period_start, Some((1, period_start.timestamp())));
        assert_eq!(result.status, AnchorCoverageStatus::Current);
    }
}
