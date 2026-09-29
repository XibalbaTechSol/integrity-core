package integrity.pack

decision := {"decision": "deny", "reason_code": "NO_ACTIVE_BAA"} if {
    input.event_class == "agent.tool_call"
    not input.baa_active
}
