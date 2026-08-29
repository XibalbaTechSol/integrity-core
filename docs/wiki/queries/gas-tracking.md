---
title: Gas Tracking & Optimization Data
type: query
updated: 2026-07-30
confidence: high
---
# Gas Tracking Data
> Last updated: 2026-07-30 01:00:12

This document automatically tracks gas usage from the agent SDK transactions.
**Total Agent Spend:** 66994636603782559 wei

## Table of contents

- [Averages by Action](#averages-by-action)
- [Optimization Plan](#optimization-plan)

## Averages by Action
| Action | Count | Avg Gas Used | Avg Cost (wei) |
|---|---|---|---|
| deploy_sovereign_agent | 24 | 796,079.50 | 812,105,401,434,018.00 |
| deploy_state_anchor | 23 | 537,434.48 | 547,961,931,578,354.06 |
| mint_testnet_itk | 25 | 59,216.56 | 60,968,510,595,728.88 |
| grant_anchor_role | 23 | 83,175.96 | 84,590,817,112,630.09 |
| register_primitives | 23 | 1,085,420.74 | 1,102,074,176,713,000.88 |
| fund_agent_wallet | 29 | 21,000.00 | 21,477,574,151,068.96 |
| register_covered_entity | 3 | 94,467.00 | 94,467,000,755,736.00 |
| create_baa | 3 | 583,532.00 | 583,532,004,668,256.00 |
| execute_via_agent(0x5FbDB2315678afecb367f032d93F642f64180aa3) | 5 | 61,066.00 | 61,067,910,437,596.80 |
| execute_via_agent(0x440C0fCDC317D69606eabc35C0F676D1a8251Ee1) | 2 | 94,812.00 | 94,812,000,758,496.00 |
| grant_ehr_access | 3 | 69,478.00 | 69,478,000,555,824.00 |
| execute_via_agent(0x4A679253410272dd5232B3Ff7cF5dbB88f295319) | 2 | 343,260.00 | 344,271,904,455,030.00 |
| execute_via_agent(0x532B02BD614Fd18aEE45603d02866cFb77575CB3) | 3 | 178,820.67 | 178,832,356,300,860.34 |
| resolve_market | 1 | 52,344.00 | 52,346,729,425,536.00 |
| approve_erc20 | 2 | 45,991.00 | 45,991,143,123,992.00 |
| allocate_capital_onchain | 2 | 229,799.00 | 229,799,645,294,950.50 |
| release_allocation | 1 | 110,424.00 | 110,424,481,448,640.00 |
| clawback_allocation | 1 | 63,614.00 | 63,614,026,717,880.00 |
| anchor_genesis_root | 3 | 151,458.00 | 151,458,001,262,150.00 |
| execute_via_agent(0x9bd03768a7DCc129555dE410FF8E85528A4F88b5) | 1 | 94,812.00 | 94,812,000,758,496.00 |
| execute_via_agent(0x0F764078757ef38E8a8A867e5A3b994Ed8F51301) | 1 | 73,210.00 | 73,210,000,585,680.00 |
| execute_via_agent(0x8A791620dd6260079BF849Dc5567aDC3F2FdC318) | 1 | 97,827.00 | 97,827,000,782,616.00 |

## Optimization Plan
- **`deploy_sovereign_agent`**: Averaging ~796k gas. This is abnormally high for a typical EIP-1167 proxy deployment. Investigate the agent factory or deployment logic to ensure proxies are used correctly and initialization is optimized.
- **`deploy_state_anchor`**: Averaging ~537k gas, also potentially high. Needs review.
