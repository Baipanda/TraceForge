from traceforge.domain.events import (
    ActorRef,
    EventKind,
    EventSource,
    WorkspaceEvent,
    WorkspaceLocation,
)


def test_workspace_event_route_key_includes_workspace_context() -> None:
    event = WorkspaceEvent(
        source=EventSource.ZULIP,
        kind=EventKind.MESSAGE_CREATED,
        actor=ActorRef(external_id="alice@example.com", display_name="Alice"),
        location=WorkspaceLocation(
            workspace_id="default",
            project_id="security-lab",
            channel_id="42",
            channel_name="security",
            topic="auth review",
        ),
        payload={"text": "这个安全问题修了吗？"},
        external_event_id="zulip-message-1001",
    )

    assert event.route_key() == "zulip:default:security-lab:42:auth review"
