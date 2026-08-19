from traceforge.interfaces.zulip.normalizer import normalize_zulip_payload
from traceforge.core.events import (
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


def test_normalize_zulip_payload_strips_html_mentions() -> None:
    event = normalize_zulip_payload(
        {
            "workspace_id": "2",
            "sender_email": "user9@traceforge.local",
            "sender_full_name": "TraceForge Admin",
            "message_id": 33,
            "message": {
                "id": 33,
                "type": "private",
                "sender_email": "user9@traceforge.local",
                "sender_full_name": "TraceForge Admin",
                "content": "<p>给 Neymar 发布一个 todo：标题为：todo 发布测试。执行人是Neyma <span class=\"user-mention\" data-user-id=\"10\">@Jarvis</span></p>",
            },
        }
    )

    assert event.payload["text"] == "给 Neymar 发布一个 todo：标题为：todo 发布测试。执行人是Neyma @Jarvis"
