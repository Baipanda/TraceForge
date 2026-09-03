from traceforge.tools.web_tools import _parse_tavily_detailed_text


def test_parse_tavily_detailed_text() -> None:
    text = """
Detailed Results:

Title: OpenAI - Wikipedia
URL: https://en.wikipedia.org/wiki/OpenAI
Content: OpenAI was founded in 2015.

Title: OpenAI
URL: https://openai.com
Content: Building AGI.
""".strip()
    results = _parse_tavily_detailed_text(text, limit=5)
    assert len(results) == 2
    assert results[0]["title"] == "OpenAI - Wikipedia"
    assert results[0]["url"].endswith("/wiki/OpenAI")
    assert "founded" in results[0]["snippet"]
