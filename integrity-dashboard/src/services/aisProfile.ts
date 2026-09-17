/**
 * Hypothetical AIS explorer profile.
 *
 * This is intentionally not an authoritative scoring engine. Live AIS values
 * come only from the Oracle API. The simulator imports this profile so its
 * constants and transfer functions have one dashboard definition and are
 * visibly tied to the versioned Rust profile it explains.
 */
export const AIS_PROFILE = 'ais/v1-geometric-1' as const;
export const MAX_COMPONENT_SCORE = 1000;
export const AIS_WEIGHTS = { entropy: 0.30, grounding: 0.30, sacrifice: 0.20, compliance: 0.20 } as const;
export const ZK_BOOST_FACTOR = 1.15;
export const TIER_CEILINGS = [300, 600, 850, 1000] as const;
export const SHADOW_FLOORS = { entropy: 100, grounding: 200, compliance: 400 } as const;

export function entropyScore(variance: number): number {
  const v = Math.max(variance, 0);
  return Math.min(Math.max(Math.exp(-1.5 * v * v) * MAX_COMPONENT_SCORE, 0), MAX_COMPONENT_SCORE);
}

export function groundingScore(hgi: number): number {
  return Math.min(Math.max(hgi, 0), 1) * MAX_COMPONENT_SCORE;
}

export function sacrificeProxyScore(hours: number): number {
  const h = Math.max(hours, 0);
  return Math.min(Math.log10(h + 1) / 3, 1) * MAX_COMPONENT_SCORE;
}

export function complianceScore(penaltyRatio: number): number {
  return (1 - Math.min(Math.max(penaltyRatio, 0), 1)) * MAX_COMPONENT_SCORE;
}
