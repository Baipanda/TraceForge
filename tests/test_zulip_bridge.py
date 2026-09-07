from traceforge.config import TraceForgeSettings
from traceforge.interfaces.zulip.bridge import (
    ZulipTraceForgeBridge,
    _direct_message_recipients,
    _stream_name,
    _typing_payload,
)


def _settings() -> TraceForgeSettings:
    return TraceForgeSettings(
        deepseek_api_key=None,
        deepseek_base_url="https://api.deepseek.com",
        deepseek_model="deepseek-v4-flash",
        traceforge_api_url="http://127.0.0.1:19090",
        traceforge_db_path="/tmp/traceforge-test.sqlite3",
        zulip_url="https://127.0.0.1:18443",
        zulip_email="Jarvis-bot@traceforge.local",
        zulip_api_key="test-key",
        zulip_bot_name="Jarvis",
        zulip_verify_ssl=False,
        zulip_poll_interval_seconds=1.0,
    )


def test_bridge_handles_stream_message_when_jarvis_is_mentioned() -> None:
    bridge = ZulipTraceForgeBridge(settings=_settings())

    assert bridge._should_handle_message(
        {"type": "stream", "content": "<p>@**Jarvis** 帮我总结这个 topic</p>"}
    )


def test_bridge_ignores_stream_message_without_mention() -> None:
    bridge = ZulipTraceForgeBridge(settings=_settings())

    assert not bridge._should_handle_message(
        {"type": "stream", "content": "<p>今天先看认证模块</p>"}
    )


def test_bridge_ignores_bare_bot_name_without_at_mention() -> None:
    """Substring 'Jarvis' must NOT trigger — that caused Jarvis↔RepoAudit loops."""
    bridge = ZulipTraceForgeBridge(settings=_settings())

    assert not bridge._should_handle_message(
        {
            "type": "stream",
            "content": "<p>这条消息来自 RepoAudit，Jarvis 无需处理。</p>",
        }
    )
    assert not bridge._should_handle_message(
        {
            "type": "stream",
            "content": "<p>This is Jarvis again confirming there's no audit request.</p>",
        }
    )


def test_bridge_replies_to_same_stream_name() -> None:
    assert _stream_name({"display_recipient": "security", "stream_id": 42}) == "security"


def test_direct_message_recipients_excludes_bot() -> None:
    recipients = _direct_message_recipients(
        {
            "display_recipient": [
                {"email": "alice@example.local"},
                {"email": "Jarvis-bot@traceforge.local"},
            ]
        },
        "Jarvis-bot@traceforge.local",
    )

    assert recipients == ["alice@example.local"]


def test_typing_payload_for_private_message_uses_participant_ids() -> None:
    payload = _typing_payload(
        {
            "type": "private",
            "sender_id": 9,
            "display_recipient": [
                {"id": 9, "email": "alice@example.local"},
                {"id": 10, "email": "Jarvis-bot@traceforge.local"},
            ],
        },
        op="start",
    )

    assert payload == {
        "op": "start",
        "type": "direct",
        "to": "[9, 10]",
    }


def test_typing_payload_for_stream_message_preserves_topic() -> None:
    payload = _typing_payload(
        {
            "type": "stream",
            "stream_id": 42,
            "subject": "安全排查",
        },
        op="stop",
    )

    assert payload == {
        "op": "stop",
        "type": "stream",
        "stream_id": "42",
        "topic": "安全排查",
    }
