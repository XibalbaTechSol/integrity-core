# Signer-role custody rotation (2026-08) — setup guide

Addresses `docs/MAINNET_READINESS.md` P0 #1: `funderWallet`/`governance`/`oracleSigner`/
`arbitrator`/`disputer` mostly collapsing to 1-2 EOAs the operator personally holds. Target:
`governance`/`arbitrator` behind a 2-of-3 Gnosis Safe; `oracleSigner`/`disputer`/`funderWallet`
each a distinct EOA. `resolverSigner` needs no action today — see the note at the bottom.

This doc covers the operator-side steps (creating the Safe, generating keys) that an agent
cannot do on your behalf — no private key material should ever be pasted into a chat session or
run through a tool call that logs its output.

## Step 1 — Create the 2-of-3 Safe on Base Sepolia

At [app.safe.global](https://app.safe.global):

1. Connect a wallet from your **first** device (the one you'd normally use day-to-day).
2. "Create new Safe" → select **Base Sepolia** network.
3. Add owners: your first device's address (already connected), your **second** device's
   address (connect or paste it), and a **third "recovery" address** — see Step 2 for how to
   generate this one specifically so it's not just another everyday key.
4. Set threshold to **2 of 3**.
5. Deploy (this costs a small amount of Base Sepolia gas from whichever device is paying).
6. Record the resulting Safe address — that's the new `governance`/`arbitrator`.

**What "recovery key" storage means in practice:** the third owner exists purely so that losing
*either* of your two everyday devices doesn't permanently lock you out (2-of-3 tolerates losing
one of the three). It should not live on either everyday device. Practical options, roughly in
order of security: a dedicated hardware wallet kept in a safe/lockbox; a seed phrase written on
paper and stored somewhere physically separate from both devices (not a password manager on
either of those same two devices, not cloud storage tied to the same account recovery as your
devices). Generate it with `cast wallet new` (Step 2) so no private key ever touches this chat
or any tool log.

## Step 2 — Generate new EOAs locally

Run these yourself, in your own terminal — each prompts for a keystore password interactively
and only prints the resulting **address** (never the private key) to the terminal:

```bash
cast wallet new ~/.integrity-keys oracle-signer
cast wallet new ~/.integrity-keys disputer
cast wallet new ~/.integrity-keys funder
cast wallet new ~/.integrity-keys recovery   # this is Step 1's third Safe owner
```

Each writes an encrypted JSON keystore under `~/.integrity-keys/`. Give me only the four
resulting **addresses** it prints (e.g. copy the `Address:` line) — never the keystore file
contents or the password.

## Step 3 — Fund the new `funderWallet` address

Same faucets as `contracts/FAUCET_INFO.md` (QuickNode, Alchemy, Base Discord, Coinbase). Fund it
with enough for several agent registrations — the SDK's default is 0.01 ETH per agent
(`fund_amount_wei`), so 0.05-0.1 ETH covers a handful of test registrations comfortably.

## What happens next

Once you have (a) the Safe address, (b) the three new EOA addresses (oracleSigner, disputer,
funderWallet), and (c) the funder address funded, hand the four addresses back and the rotation
script will be adapted with them — you'll then run one `forge script ... --broadcast` command
yourself (same hand-off pattern as the registration debugging), and gas for that comes from your
existing operator key, not the new ones (they're being *granted into*, not spending yet).

## `resolverSigner` — no action needed right now

Unlike the other five roles, `resolverSigner` isn't a protocol-level on-chain role that can be
rotated for existing state — it's the `RESOLVER_ROLE` granted per-market at creation time
(`IntegrityMarket.initialize()`, via `DeployMarkets.s.sol`'s `RESOLVER_ADDRESS` env var). The
prior rotation script deliberately left it untouched for the same reason (see
`RotateOperatorKeyGrant.s.sol`'s own comment: "this operator key was never that market's
creator/admin"). If you generate a distinct EOA for it anyway (optional, for bookkeeping
consistency), it only takes effect the next time `DeployMarkets.s.sol` runs for a new market —
no separate action today.
