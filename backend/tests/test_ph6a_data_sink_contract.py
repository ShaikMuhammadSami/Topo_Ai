"""PH-6A customer-data sink and credential-binding inventory tests."""

from __future__ import annotations

from app.security.egress_inventory import (
    EGRESS_CALLSITES,
    EXTERNAL_DATA_SINKS,
    CustomerDataClass,
    DestinationOwnership,
    DestinationRisk,
    RuntimeComponent,
)


def test_customer_data_classification_and_sink_matrix_are_closed() -> None:
    assert {item.value for item in CustomerDataClass} == {
        "PUBLIC_SYSTEM_DATA",
        "TOPO_CONTROL_METADATA",
        "TENANT_OPERATIONAL_METADATA",
        "CUSTOMER_STRUCTURED_OPERATIONAL_DATA",
        "CUSTOMER_USER_AUTHORED_CONTENT",
        "RAW_CUSTOMER_PAYLOAD",
        "AUTHENTICATION_SECRET",
        "SECRET_MATERIAL",
    }
    sink_ids = [item.sink_id for item in EXTERNAL_DATA_SINKS]
    assert len(sink_ids) == len(set(sink_ids)) == 15
    assert all(item.data_classes for item in EXTERNAL_DATA_SINKS)
    assert all(item.credential_binding for item in EXTERNAL_DATA_SINKS)


def test_raw_and_secret_sink_reachability_is_explicit_not_claimed_safe() -> None:
    raw_sinks = {
        item.sink_id
        for item in EXTERNAL_DATA_SINKS
        if CustomerDataClass.RAW_CUSTOMER_PAYLOAD in item.data_classes
    }
    assert raw_sinks == {
        "server-database",
        "tenant-webhook",
        "openai",
        "groq",
        "agent-topo",
    }
    assert sum(
        CustomerDataClass.AUTHENTICATION_SECRET in item.data_classes
        for item in EXTERNAL_DATA_SINKS
    ) == 13
    assert sum(
        CustomerDataClass.SECRET_MATERIAL in item.data_classes
        for item in EXTERNAL_DATA_SINKS
    ) == 2
    llm_sinks = {
        item.sink_id
        for item in EXTERNAL_DATA_SINKS
        if item.sink_id in {"openai", "groq"}
    }
    assert llm_sinks == {"openai", "groq"}
    for item in EXTERNAL_DATA_SINKS:
        if item.sink_id in llm_sinks:
            assert CustomerDataClass.RAW_CUSTOMER_PAYLOAD in item.data_classes
            assert CustomerDataClass.SECRET_MATERIAL not in item.data_classes


def test_server_destination_and_credential_risks_are_exact() -> None:
    server = [
        item
        for item in EGRESS_CALLSITES
        if item.component is RuntimeComponent.SERVER_PRODUCTION_EGRESS
    ]
    assert all(item.destination_ownership is not DestinationOwnership.UNKNOWN for item in server)
    assert all(item.destination_ownership is not DestinationOwnership.NONE for item in server)

    critical = [item for item in server if item.destination_risk is DestinationRisk.CRITICAL]
    assert [item.callsite_id for item in critical] == ["server.webhook.delivery-post"]
    assert "PH-6B owns closure" in critical[0].notes
    assert critical[0].tenant_controlled
    assert critical[0].redirect_behavior.startswith("disabled")

    derived = [
        item
        for item in server
        if item.destination_ownership is DestinationOwnership.REMOTE_RESPONSE_DERIVED
    ]
    assert len(derived) == 24
    artifact = next(
        item
        for item in derived
        if item.callsite_id == "server.github.artifact-redirect-get"
    )
    assert all(item.destination_can_change_after_initial_request for item in derived)
    assert "cross-origin hop gets no Authorization" in artifact.credential_binding


def test_no_generic_inbound_header_or_mutable_shared_credential_forwarding() -> None:
    for item in EGRESS_CALLSITES:
        assert "inbound headers" not in item.headers_source.casefold()
        assert "caller host header" not in item.headers_source.casefold()
    credentialed = [item for item in EGRESS_CALLSITES if item.secret_classes]
    assert credentialed
    assert all(item.credential_binding for item in credentialed)
