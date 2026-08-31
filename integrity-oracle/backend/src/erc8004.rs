//! ERC-8004 registration-file validation at the Integrity directory boundary.
//!
//! A valid ERC-8004 file provides discovery only. Binding it to an Integrity DID
//! requires the two-way DID backlink checked here; it never changes AIS directly.

use serde::{Deserialize, Serialize};

pub const REGISTRATION_TYPE: &str = "https://eips.ethereum.org/EIPS/eip-8004#registration-v1";

/// CAIP-10-shaped identifier for an ERC-8004 Identity Registry deployment, e.g.
/// `eip155:84532:0x8004a818bfb912233c491871b3d84c89a494bd9e`. This is the value a
/// registration file's `registrations[].agentRegistry` entry must match — never a bare
/// address — so the same registration file can unambiguously name which chain's registry
/// it's registered against.
pub fn caip10(chain_id: u64, registry: &str) -> String {
    format!("eip155:{chain_id}:{}", registry.to_ascii_lowercase())
}

#[derive(Debug, Clone, Deserialize)]
pub struct RegistrationFile {
    #[serde(rename = "type")]
    pub registration_type: String,
    pub name: String,
    pub description: String,
    pub image: String,
    pub services: Vec<Service>,
    #[serde(rename = "x402Support")]
    pub x402_support: bool,
    pub active: bool,
    pub registrations: Vec<RegistrationRef>,
    #[serde(rename = "supportedTrust", default)]
    pub supported_trust: Vec<String>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct Service {
    pub name: String,
    pub endpoint: String,
    #[serde(default)]
    pub version: Option<String>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct RegistrationRef {
    #[serde(rename = "agentId")]
    pub agent_id: serde_json::Value,
    #[serde(rename = "agentRegistry")]
    pub agent_registry: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct VerifiedRegistration {
    pub name: String,
    pub description: String,
    pub image: String,
    pub active: bool,
    pub x402_support: bool,
    pub supported_trust: Vec<String>,
    pub did_backlink: String,
    pub mcp_endpoint: Option<String>,
    pub a2a_endpoint: Option<String>,
    pub a2a_version: Option<String>,
}

pub fn validate_registration(
    bytes: &[u8],
    integrity_did: &str,
    expected_registry: &str,
    expected_token_id: &str,
) -> Result<VerifiedRegistration, String> {
    let file: RegistrationFile =
        serde_json::from_slice(bytes).map_err(|_| "registration file is not valid JSON".to_string())?;
    if file.registration_type != REGISTRATION_TYPE {
        return Err("registration file has an unsupported ERC-8004 type".to_string());
    }
    if [file.name.as_str(), file.description.as_str(), file.image.as_str()]
        .iter()
        .any(|field| field.trim().is_empty())
    {
        return Err("registration file requires non-empty name, description, and image".to_string());
    }
    if !file.registrations.iter().any(|entry| {
        entry.agent_registry.eq_ignore_ascii_case(expected_registry)
            && token_id_matches(&entry.agent_id, expected_token_id)
    }) {
        return Err("registration file does not backlink to the supplied ERC-8004 identity".to_string());
    }
    let did = file
        .services
        .iter()
        .find(|service| service.name.eq_ignore_ascii_case("DID") && service.endpoint == integrity_did)
        .ok_or_else(|| "registration file has no matching Integrity DID service".to_string())?;
    let service = |name: &str| file.services.iter().find(|item| item.name.eq_ignore_ascii_case(name));
    let a2a = service("A2A");
    Ok(VerifiedRegistration {
        name: file.name,
        description: file.description,
        image: file.image,
        active: file.active,
        x402_support: file.x402_support,
        supported_trust: file.supported_trust,
        did_backlink: did.endpoint.clone(),
        mcp_endpoint: service("MCP").map(|item| item.endpoint.clone()),
        a2a_endpoint: a2a.map(|item| item.endpoint.clone()),
        a2a_version: a2a.and_then(|item| item.version.clone()),
    })
}

fn token_id_matches(value: &serde_json::Value, expected: &str) -> bool {
    matches!(value, serde_json::Value::String(value) if value == expected)
        || matches!(value, serde_json::Value::Number(value) if value.to_string() == expected)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn accepts_two_way_integrity_binding_with_a2a_and_x402() {
        let json = br#"{"type":"https://eips.ethereum.org/EIPS/eip-8004#registration-v1","name":"Xibalba","description":"Agent","image":"ipfs://image","services":[{"name":"DID","endpoint":"did:integrity:xibalba"},{"name":"A2A","endpoint":"https://agent.example/.well-known/agent-card.json","version":"0.3.0"}],"x402Support":true,"active":true,"registrations":[{"agentId":7,"agentRegistry":"eip155:84532:0x8004"}]}"#;
        let verified = validate_registration(json, "did:integrity:xibalba", "eip155:84532:0x8004", "7").unwrap();
        assert!(verified.x402_support);
        assert_eq!(verified.a2a_version.as_deref(), Some("0.3.0"));
    }

    #[test]
    fn caip10_lowercases_the_registry_address() {
        assert_eq!(
            caip10(84532, "0x8004A818BFB912233c491871b3d84c89A494BD9e"),
            "eip155:84532:0x8004a818bfb912233c491871b3d84c89a494bd9e"
        );
    }

    #[test]
    fn rejects_one_way_claim_without_did_backlink() {
        let json = br#"{"type":"https://eips.ethereum.org/EIPS/eip-8004#registration-v1","name":"Xibalba","description":"Agent","image":"ipfs://image","services":[],"x402Support":false,"active":true,"registrations":[{"agentId":"7","agentRegistry":"eip155:84532:0x8004"}]}"#;
        assert!(validate_registration(json, "did:integrity:xibalba", "eip155:84532:0x8004", "7").is_err());
    }
}
