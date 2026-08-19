from traceforge.context.models import ZulipConversationType
from traceforge.context.zulip import ZulipContextBuilder
from traceforge.core.events import ActorRef, EventKind, EventSource, WorkspaceEvent, WorkspaceLocation
from traceforge.session.keys import SessionKeyResolver


def _stream_event(topic: str = "SQL 注入排查") -> WorkspaceEvent:
    return WorkspaceEvent(
        source=EventSource.ZULIP,
        kind=EventKind.MESSAGE_CREATED,
        actor=ActorRef(
            external_id="9",
            display_name="TraceForge Admin",
            email="user9@traceforge.local",
        ),
        location=WorkspaceLocation(
            workspace_id="2",
            channel_id="42",
            channel_name="security",
            topic=topic,
        ),
        payload={
            "text": "@Jarvis 总结这个 Topic",
            "raw": {
                "message": {
                    "id": 33,
                    "type": "stream",
                    "sender_id": 9,
                    "sender_email": "user9@traceforge.local",
                    "sender_full_name": "TraceForge Admin",
                    "stream_id": 42,
                    "display_recipient": "security",
                    "subject": topic,
                    "content": "<p>@**Jarvis** 总结这个 Topic</p>",
                }
            },
        },
        external_event_id="33",
    )


def test_context_builder_preserves_zulip_conversation_metadata() -> None:
    context = ZulipContextBuilder().build(_stream_event())

    assert context.message_type == ZulipConversationType.STREAM
    assert context.sender.email == "user9@traceforge.local"
    assert context.stream_id == "42"
    assert context.stream_name == "security"
    assert context.topic == "SQL 注入排查"
    assert context.mentions == ("Jarvis",)


def test_session_key_is_stable_for_same_stream_topic() -> None:
    resolver = SessionKeyResolver()

    first = resolver.resolve(ZulipContextBuilder().build(_stream_event("Security Review")))
    second = resolver.resolve(ZulipContextBuilder().build(_stream_event("security review")))

    assert first == second
    assert ":stream:42:topic:security%20review" in first


def test_private_session_uses_participant_set() -> None:
    event = _stream_event()
    private_event = WorkspaceEvent(
        source=event.source,
        kind=event.kind,
        actor=event.actor,
        location=event.location,
        payload={
            "text": "你好",
            "raw": {
                "message": {
                    "id": 34,
                    "type": "private",
                    "sender_email": "user9@traceforge.local",
                    "sender_full_name": "TraceForge Admin",
                    "display_recipient": [
                        {
                            "id": 9,
                            "email": "user9@traceforge.local",
                            "full_name": "TraceForge Admin",
                        },
                        {
                            "id": 10,
                            "email": "Jarvis-bot@traceforge.local",
                            "full_name": "Jarvis",
                        },
                    ],
                    "content": "<p>你好</p>",
                }
            },
        },
        external_event_id="34",
    )

    key = SessionKeyResolver().resolve(ZulipContextBuilder().build(private_event))

    assert key.startswith("zulip:2:dm:")
