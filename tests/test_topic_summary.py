from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from traceforge.application.presentation import format_topic_digest_reply
from traceforge.application.topic_summary import TopicSummaryWorkflow
from traceforge.application.topic_summary_synthesizer import TopicDigest, TopicSummarySynthesizer
from traceforge.core.todos import TodoRecord, TodoStatus
from traceforge.infrastructure.storage.sqlite_repository import SqliteTodoRepository
from traceforge.infrastructure.zulip.client import ZulipTopicMessage


class FakeZulip:
    def fetch_topic_messages_all(self, *, stream, topic, page_size=500, exclude_sender_email=None):
        now = datetime.now(timezone.utc)
        return [
            ZulipTopicMessage(1, "Neymar", "n@x", "我们先做认证模块", now),
            ZulipTopicMessage(2, "Peter", "p@x", "SQL 注入要优先处理", now),
        ]


class FakeModel:
    def complete_json(self, *, system_prompt, user_prompt, max_tokens=2000):
        return """{
          "background": "讨论认证与安全",
          "confirmed_facts": ["需要检查 SQL 注入"],
          "decisions": ["Peter 负责安全项"],
          "open_questions": [],
          "risks": ["注入风险"],
          "suggested_actions": ["补充测试用例"],
          "key_quotes": [{"time": "2026-08-31", "speaker": "Peter", "excerpt": "SQL 注入要优先"}]
        }"""


def test_topic_summary_workflow_with_digest(tmp_path) -> None:
    repo = SqliteTodoRepository(Path(tmp_path) / "t.db")
    st = repo.find_subtree("demo", code="software.cloud.agent")
    now = datetime.now(timezone.utc)
    repo.create_todo(
        TodoRecord(
            id="t1",
            title="SQL注入检查",
            description=None,
            status=TodoStatus.OPEN,
            priority=0,
            workspace_id="demo",
            subtree_id=st.id,
            channel_name="general",
            topic="agent开发",
            proposer_name="N",
            proposer_email="n@x",
            assignee_name="Peter",
            assignee_email="p@x",
            source_message_id="1",
            created_at=now,
            updated_at=now,
        )
    )
    wf = TopicSummaryWorkflow(
        repo,
        zulip_client=FakeZulip(),
        synthesizer=TopicSummarySynthesizer(FakeModel()),
    )
    result = wf.summarize(
        workspace_id="demo",
        channel_name="general",
        topic="agent开发",
    )
    assert result.digest is not None
    assert "Topic 摘要" in result.reply_text
    assert "认证与安全" in result.reply_text
    assert result.evidence[0]["message_count"] == 2


def test_topic_summary_fallback_without_llm(tmp_path) -> None:
    repo = SqliteTodoRepository(Path(tmp_path) / "t.db")
    wf = TopicSummaryWorkflow(repo, zulip_client=FakeZulip(), synthesizer=None)
    result = wf.summarize(
        workspace_id="demo",
        channel_name="general",
        topic="agent开发",
    )
    assert result.digest is None
    assert "无法生成结构化摘要" in result.reply_text


def test_format_topic_digest_reply() -> None:
    digest = TopicDigest(
        background="背景",
        confirmed_facts=("事实1",),
        decisions=("结论1",),
        open_questions=(),
        risks=("风险1",),
        suggested_actions=("建议1",),
        key_quotes=(("10:00", "A", "摘录"),),
    )
    text = format_topic_digest_reply(
        stream="general",
        topic="agent开发",
        message_count=5,
        todos=[],
        digest=digest,
    )
    assert "背景" in text
    assert "事实1" in text
    assert "关键发言" in text
