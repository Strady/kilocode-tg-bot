"""Unit tests for the Markdown → Telegram-HTML converter.

Covers every construct the converter maps: headings, bold, italic, strike,
inline code, fenced code blocks (with/without language), lists (nested/numbered),
links, short & long quotes (expandable), tables, hr, ``< > &`` escaping in text
and code, a snapshot-like mixed example, and resilience to unterminated markdown.
"""

from __future__ import annotations

import pytest
from kilocode_tg_bot.formatting.markdown_to_tg_html import (
    EXPANDABLE_QUOTE_CHARS,
    markdown_to_telegram_html,
)


@pytest.mark.parametrize(
    ("markdown", "expected"),
    [
        # headings → bold on their own line (all levels collapse to <b>)
        ("# One", "<b>One</b>"),
        ("## Two", "<b>Two</b>"),
        ("###### Six", "<b>Six</b>"),
        # bold
        ("**bold**", "<b>bold</b>"),
        ("__bold__", "<b>bold</b>"),
        ("a **b** c", "a <b>b</b> c"),
        # italic (but not intraword underscores like snake_case)
        ("*ita*", "<i>ita</i>"),
        ("_ita_", "<i>ita</i>"),
        ("use snake_case_name", "use snake_case_name"),
        ("foo_bar_baz", "foo_bar_baz"),
        # strikethrough
        ("~~gone~~", "<s>gone</s>"),
        # inline code
        ("`x = 1`", "<code>x = 1</code>"),
        ("run `cmd` now", "run <code>cmd</code> now"),
        # fenced code block with a language
        ("```python\nprint(1)\n```", '<pre><code class="language-python">print(1)</code></pre>'),
        # fenced code block without a language
        ("```\nraw\n```", "<pre><code>raw</code></pre>"),
        # links
        ("[docs](https://x.dev)", '<a href="https://x.dev">docs</a>'),
        # nested emphasis inside a link label
        ("[**api** ref](https://x.dev)", '<a href="https://x.dev"><b>api</b> ref</a>'),
    ],
)
def test_single_constructs(markdown: str, expected: str) -> None:
    assert markdown_to_telegram_html(markdown) == expected


@pytest.mark.parametrize(
    ("markdown", "expected"),
    [
        ("- one\n- two", "• one\n• two"),
        ("* one\n* two", "• one\n• two"),
        ("1. first\n2. second", "1. first\n2. second"),
        ("3) third", "3) third"),
        # nested list → indentation only (no <ul>/<li>)
        ("- top\n  - nested", "• top\n  • nested"),
    ],
)
def test_lists(markdown: str, expected: str) -> None:
    assert markdown_to_telegram_html(markdown) == expected


def test_short_quote() -> None:
    expected = "<blockquote>hello<br/>world</blockquote>"
    assert markdown_to_telegram_html("> hello\n> world") == expected


def test_long_quote_is_expandable() -> None:
    body = "x" * (EXPANDABLE_QUOTE_CHARS + 10)
    html = markdown_to_telegram_html(f"> {body}")
    assert html.startswith("<blockquote expandable>")
    assert html.endswith("</blockquote>")


def test_multi_quote_is_expandable() -> None:
    html = markdown_to_telegram_html("\n".join(f"> line {i}" for i in range(8)))
    assert html.startswith("<blockquote expandable>")


def test_table_renders_as_monospace() -> None:
    markdown = "| a | b |\n|---|---|\n| 1 | 2 |"
    html = markdown_to_telegram_html(markdown)
    assert html == "<pre><code>a | b\n1 | 2</code></pre>"


def test_horizontal_rule_dropped() -> None:
    assert markdown_to_telegram_html("before\n---\nafter") == "before\nafter"


@pytest.mark.parametrize(
    ("markdown", "expected"),
    [
        ("a < b", "a &lt; b"),
        ("x & y", "x &amp; y"),
        ("5 > 3", "5 &gt; 3"),
        # escaping inside inline code
        ("`a < b`", "<code>a &lt; b</code>"),
    ],
)
def test_html_escaping(markdown: str, expected: str) -> None:
    assert markdown_to_telegram_html(markdown) == expected


def test_escaping_inside_code_block() -> None:
    markdown = "```html\n<div class=\"x\">a</div>\n```"
    html = markdown_to_telegram_html(markdown)
    # `<`/`>`/`&` are escaped inside <pre>; plain quotes are fine for Telegram
    assert "<div" not in html
    assert "&lt;div class=\"x\"&gt;a&lt;/div&gt;" in html


def test_mixed_realistic_snapshot() -> None:
    markdown = (
        "## Plan\n"
        "- do **first**\n"
        "- use `y()`\n"
        "\n"
        "Then *done*:\n"
        "\n"
        "> keep calm\n"
        "\n"
        "[more](https://example.com)"
    )
    expected = (
        "<b>Plan</b>\n"
        "• do <b>first</b>\n"
        "• use <code>y()</code>\n"
        "Then <i>done</i>:\n"
        "<blockquote>keep calm</blockquote>\n"
        '<a href="https://example.com">more</a>'
    )
    assert markdown_to_telegram_html(markdown) == expected


# --- resilience: incomplete markdown must not crash or emit invalid HTML --------


@pytest.mark.parametrize(
    "markdown",
    [
        "hello **world",       # unterminated bold
        "*unclosed",           # unterminated italic
        "```python\nprint(1)", # unterminated code fence
        "[click](https://x",   # unterminated link
        "## no space",         # '#' without following space stays literal
    ],
)
def test_incomplete_markdown_does_not_raise(markdown: str) -> None:
    html = markdown_to_telegram_html(markdown)
    assert isinstance(html, str)
    # no unbalanced open tags left behind
    for tag in ("<b>", "<i>", "<s>", "<pre>"):
        assert html.count(tag) >= html.count(tag.replace("<", "</"))


def test_empty_input() -> None:
    assert markdown_to_telegram_html("") == ""
    assert markdown_to_telegram_html("   ") == ""
