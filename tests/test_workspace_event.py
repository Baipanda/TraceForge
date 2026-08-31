from traceforge.interfaces.zulip.normalizer import normalize_zulip_payload
from traceforge.core.events import (
    ActorRef,
    EventKind,
    EventSource,
    WorkspaceEvent,
    WorkspaceLocation,
)
from traceforge.infrastructure.identity.person_store import PersonStore


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


def test_normalize_zulip_payload_strips_html_mentions(tmp_path) -> None:
    store = PersonStore(tmp_path / "persons.sqlite3")
    event = normalize_zulip_payload(
        {
            "workspace_id": "2",
            "sender_email": "user9@traceforge.local",
            "sender_full_name": "TraceForge Admin",
            "sender_id": 8,
            "message_id": 33,
            "message": {
                "id": 33,
                "type": "private",
                "sender_id": 8,
                "sender_email": "user9@traceforge.local",
                "sender_full_name": "TraceForge Admin",
                "content": "<p>给 Neymar 发布一个 todo：标题为：todo 发布测试。执行人是Neyma <span class=\"user-mention\" data-user-id=\"10\">@Jarvis</span></p>",
            },
        },
        person_store=store,
    )

    assert event.payload["text"] == "给 Neymar 发布一个 todo：标题为：todo 发布测试。执行人是Neyma @Jarvis"
    assert event.actor.person_id
    assert event.actor.external_id == "8"
    # Seeded Admin binding for Zulip user_id 8
    admin = store.resolve("8")
    assert admin is not None
    assert event.actor.person_id == admin.person_id

