/**
 * Client-side, trustless verification of the oracle-issued W3C Verifiable Credential
 * (`AgentIntegrityCredential`). This is the point of the exercise: rather than trusting
 * that the oracle "signed" the credential, the browser re-derives the exact signed bytes
 * and checks the Ed25519 signature against the issuer's OWN public key (extracted from the
 * credential's `did:key` issuer) — no oracle round-trip, no server trust.
 *
 * The signed bytes MUST byte-match `integrity-oracle/backend/src/crypto.rs::canonical_json_bytes`
 * over the proof-less credential body (the oracle signs the credential, THEN attaches `proof`).
 * That scheme is: recursively lexicographically-sorted object keys, compact separators
 * (`,`/`:`, no whitespace), and non-ASCII escaped as `\uXXXX` (Python `ensure_ascii=True`
 * parity). See `vc.rs::issue_vc`.
 */
import * as ed from '@noble/ed25519';

/**
 * Canonical JSON bytes matching the oracle's `canonical_json_bytes`: sorted keys, compact,
 * non-ASCII escaped as lowercase `\uXXXX` (UTF-16 code units, surrogate pairs for astral
 * code points). ASCII passes through unchanged — which covers the entire credential body
 * in practice (DIDs, integers, ISO-8601 dates, trust levels are all ASCII).
 */
export function canonicalJsonBytes(value: unknown): Uint8Array {
    return new TextEncoder().encode(canonicalize(value));
}

function canonicalize(value: unknown): string {
    if (value === null) return 'null';
    if (typeof value === 'boolean') return value ? 'true' : 'false';
    if (typeof value === 'number') {
        if (!Number.isFinite(value)) throw new Error('non-finite number in credential');
        // Integers (the only numbers in an AgentIntegrityCredential) serialize identically
        // to serde_json / Python json.dumps.
        return String(value);
    }
    if (typeof value === 'string') return encodeString(value);
    if (Array.isArray(value)) return `[${value.map(canonicalize).join(',')}]`;
    if (typeof value === 'object') {
        const obj = value as Record<string, unknown>;
        const keys = Object.keys(obj).sort();
        return `{${keys.map((k) => `${encodeString(k)}:${canonicalize(obj[k])}`).join(',')}}`;
    }
    throw new Error(`unserializable value of type ${typeof value}`);
}

/** JSON string encoding with `ensure_ascii=True` parity (matches serde_json + Python). */
function encodeString(s: string): string {
    let out = '"';
    for (const ch of s) {
        const code = ch.codePointAt(0)!;
        if (ch === '"') out += '\\"';
        else if (ch === '\\') out += '\\\\';
        else if (ch === '\b') out += '\\b';
        else if (ch === '\f') out += '\\f';
        else if (ch === '\n') out += '\\n';
        else if (ch === '\r') out += '\\r';
        else if (ch === '\t') out += '\\t';
        else if (code < 0x20) out += `\\u${code.toString(16).padStart(4, '0')}`;
        else if (code < 0x80) out += ch;
        else {
            // Non-ASCII: emit UTF-16 code units, exactly like ensure_ascii=True.
            for (let i = 0; i < ch.length; i++) {
                out += `\\u${ch.charCodeAt(i).toString(16).padStart(4, '0')}`;
            }
        }
    }
    return out + '"';
}

const B58_ALPHABET = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz';

/** Decode a base58btc string to bytes (no external dep). */
function base58Decode(str: string): Uint8Array {
    const bytes: number[] = [0];
    for (const c of str) {
        const val = B58_ALPHABET.indexOf(c);
        if (val < 0) throw new Error(`invalid base58 char: ${c}`);
        let carry = val;
        for (let j = 0; j < bytes.length; j++) {
            carry += bytes[j] * 58;
            bytes[j] = carry & 0xff;
            carry >>= 8;
        }
        while (carry > 0) {
            bytes.push(carry & 0xff);
            carry >>= 8;
        }
    }
    // Preserve leading zeros (each leading '1' in base58 is a zero byte).
    for (let k = 0; k < str.length && str[k] === '1'; k++) bytes.push(0);
    return new Uint8Array(bytes.reverse());
}

/** base64url (no padding) → bytes. */
function base64UrlDecode(s: string): Uint8Array {
    const b64 = s.replace(/-/g, '+').replace(/_/g, '/');
    const bin = atob(b64);
    const out = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
    return out;
}

/**
 * Extract the raw 32-byte Ed25519 public key from a `did:key:z...` identifier. The base58btc
 * payload is `0xed 0x01` (Ed25519 multicodec) followed by the 32-byte key.
 */
export function ed25519PubkeyFromDidKey(didKey: string): Uint8Array {
    const m = didKey.match(/^did:key:z([1-9A-HJ-NP-Za-km-z]+)$/);
    if (!m) throw new Error('issuer is not a did:key identifier');
    const decoded = base58Decode(m[1]);
    if (decoded.length !== 34 || decoded[0] !== 0xed || decoded[1] !== 0x01) {
        throw new Error('did:key is not an Ed25519 multicodec key');
    }
    return decoded.slice(2);
}

export interface VcVerification {
    valid: boolean;
    issuer: string;
    /** Hex of the issuer Ed25519 public key the signature was checked against. */
    issuerPublicKeyHex: string;
    /** The exact canonical string the signature covers — shown so a user can inspect it. */
    signedPayload: string;
    error?: string;
}

/**
 * Verify an oracle-issued AgentIntegrityCredential entirely in the browser. Returns a
 * structured result (never throws for an invalid signature — only for a malformed input we
 * genuinely cannot check).
 */
export async function verifyCredential(vc: Record<string, unknown>): Promise<VcVerification> {
    const proof = vc.proof as Record<string, unknown> | undefined;
    const issuer = String(vc.issuer ?? '');
    if (!proof || typeof proof.jws !== 'string') {
        return { valid: false, issuer, issuerPublicKeyHex: '', signedPayload: '', error: 'credential has no Ed25519 proof' };
    }
    try {
        // The oracle signs the credential body WITHOUT the proof, then attaches proof.
        const { proof: _omit, ...body } = vc;
        const signedBytes = canonicalJsonBytes(body);
        const pubkey = ed25519PubkeyFromDidKey(issuer);
        const sig = base64UrlDecode(proof.jws as string);
        const valid = await ed.verifyAsync(sig, signedBytes, pubkey);
        return {
            valid,
            issuer,
            issuerPublicKeyHex: bytesToHex(pubkey),
            signedPayload: new TextDecoder().decode(signedBytes),
        };
    } catch (e: unknown) {
        return {
            valid: false,
            issuer,
            issuerPublicKeyHex: '',
            signedPayload: '',
            error: e instanceof Error ? e.message : 'verification failed',
        };
    }
}

function bytesToHex(b: Uint8Array): string {
    return '0x' + Array.from(b).map((x) => x.toString(16).padStart(2, '0')).join('');
}
