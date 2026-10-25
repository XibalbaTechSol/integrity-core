//! Receiver-side stripping of prohibited identity and content attributes
//! (`docs/EXECUTION_PLAN.md` B5).
//!
//! `crate::phi` is a **value** backstop: it regex-scans JSON string leaves and rejects the
//! export when one looks like raw PHI/PII/secret material. That leaves a real hole, because
//! the thing B5 names is a **key**. An attribute literally called `user.email` whose value is
//! `jdoe` matches no pattern in `phi.rs` and is persisted verbatim today; so are a stack
//! trace, a repository name, a file path and an environment variable, none of which any regex
//! can recognise. This module closes that by name: the key is removed whatever its value is.
//!
//! Ordering matters and is deliberate — the strip runs **before** the PHI backstop in every
//! handler. The other order would make a `user.email` holding a real address reject the whole
//! export (`phi_backstop_mode = reject` is the default) instead of dropping the one field it
//! was never allowed to keep, so a single prohibited attribute would cost every sibling span
//! in the batch.
//!
//! **This is a deny-list, and a deny-list cannot be complete.** It names the keys OTel's
//! semantic conventions define for identity and content, plus the categories B5 enumerates;
//! an emitter that invents `my_company.customer_email` is not covered, and no negative test
//! here can discover that. Closing that properly means an allow-list for the regulated
//! profile, which is a product decision about what the oracle accepts at all rather than a
//! change to this module — see `docs/INTERFACE_CONTRACT.md`.

use serde_json::{Map, Value};

/// The attribute carrying the agent's own identity. It is the receiver's routing key
/// (`otlp.rs::extract_agent_id`), so it is never a candidate for stripping even though it
/// starts with a prefix a future rule might otherwise match.
const NEVER_STRIP: &[&str] = ["integrity.agent.id"].as_slice();

/// Keys removed on exact match, compared case-insensitively against both the attribute's own
/// name and its full dotted path (OTel permits either `{"user.email": …}` or a nested
/// `KvlistValue` that arrives here as `{"user": {"email": …}}` — both are the same attribute).
///
/// Grouped by the category B5 lists, so a reader can check coverage against the plan.
const PROHIBITED_EXACT: &[&str] = &[
    // Identity. `enduser.*` is the older semconv spelling of `user.*`; both are live.
    "user.email", "user.full_name", "user.name", "user.id", "user.hash", "user.roles",
    "enduser.id", "enduser.role", "enduser.scope",
    "client.address", "host.ip",
    // Prompts and completions.
    "gen_ai.prompt", "gen_ai.completion", "gen_ai.input.messages", "gen_ai.output.messages",
    "gen_ai.system_instructions", "prompt", "completion", "content", "message", "text",
    // Tool arguments and results.
    "gen_ai.tool.arguments", "tool.arguments", "tool.result", "tool_result", "tool_output",
    "arguments", "function.arguments",
    // File contents and filenames.
    "file.content", "file.path", "file.name", "file.directory", "code.filepath",
    // stdout / stderr.
    "process.stdout", "process.stderr", "code.stdout", "code.stderr", "stdout", "stderr",
    // Command lines carry both filenames and arguments.
    "process.command", "process.command_line", "process.command_args",
    // URLs and query strings.
    "url.full", "url.query", "url.path", "http.url", "http.target",
    // Repository names.
    "vcs.repository.url.full", "vcs.repository.name", "vcs.repository.ref.name",
    "repository.name", "repository.url",
    // Exception messages and stack traces.
    "exception.message", "exception.stacktrace", "error.message", "error.stack",
];

/// Keys removed when the name or dotted path *starts with* one of these, for the conventions
/// that are open-ended by design: every environment variable is its own attribute
/// (`process.environment_variable.PATH`), and a `KvlistValue` lands as a nested object whose
/// leaves must go with it.
const PROHIBITED_PREFIX: &[&str] = &["process.environment_variable.", "user.", "enduser."];

/// The attribute this module writes back when it removed anything, so a consumer reading the
/// row can tell "nothing prohibited was sent" from "something was sent and dropped here".
/// Silent removal would be indistinguishable from the emitter never having set the field.
pub const STRIPPED_KEYS_ATTRIBUTE: &str = "integrity.telemetry.stripped";

fn is_prohibited(name: &str, path: &str) -> bool {
    let name_lower = name.to_ascii_lowercase();
    let path_lower = path.to_ascii_lowercase();
    if NEVER_STRIP.iter().any(|k| *k == path_lower || *k == name_lower) {
        return false;
    }
    PROHIBITED_EXACT.iter().any(|k| *k == name_lower || *k == path_lower)
        || PROHIBITED_PREFIX.iter().any(|p| name_lower.starts_with(p) || path_lower.starts_with(p))
}

fn strip_map(map: &mut Map<String, Value>, parent: &str, removed: &mut Vec<String>) {
    let names: Vec<String> = map.keys().cloned().collect();
    for name in names {
        let path = if parent.is_empty() { name.clone() } else { format!("{parent}.{name}") };
        if is_prohibited(&name, &path) {
            map.remove(&name);
            removed.push(path);
            continue;
        }
        match map.get_mut(&name) {
            Some(Value::Object(child)) => {
                let was_empty = child.is_empty();
                strip_map(child, &path, removed);
                // A branch whose every leaf was prohibited -- `{"user": {"email": …,
                // "tier": …}}` under the `user.` prefix -- would otherwise be left behind as
                // an empty object, which tells a reader nothing the stripped-key list does
                // not already say. A branch that arrived empty is the emitter's own doing
                // and is left exactly as sent.
                if child.is_empty() && !was_empty {
                    map.remove(&name);
                }
            }
            Some(Value::Array(items)) => {
                for item in items.iter_mut() {
                    if let Value::Object(child) = item {
                        strip_map(child, &path, removed);
                    }
                }
            }
            _ => {}
        }
    }
}

/// Removes every prohibited attribute from `value` in place and returns the dotted paths of
/// what went, sorted and deduplicated so the result is stable to assert on and to store.
///
/// A non-object `value` is returned untouched with an empty list: there is no key to judge.
pub fn strip_prohibited(value: &mut Value) -> Vec<String> {
    let mut removed = Vec::new();
    if let Value::Object(map) = value {
        strip_map(map, "", &mut removed);
    }
    removed.sort();
    removed.dedup();
    removed
}

/// `strip_prohibited`, plus the audit trail: when anything was removed, records the names
/// under [`STRIPPED_KEYS_ATTRIBUTE`] on the same map. This is what the OTLP handlers call to
/// build the row they persist.
pub fn sanitize_attributes(value: &mut Value) -> Vec<String> {
    let removed = strip_prohibited(value);
    if !removed.is_empty() {
        if let Value::Object(map) = value {
            map.insert(
                STRIPPED_KEYS_ATTRIBUTE.to_string(),
                Value::Array(removed.iter().map(|k| Value::String(k.clone())).collect()),
            );
        }
    }
    removed
}
