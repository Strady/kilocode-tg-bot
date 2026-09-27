"""Convert Markdown text into Telegram's limited HTML set.

Telegram's ``parse_mode=HTML`` supports only a handful of tags: ``<b>``, ``<i>``,
``<u>``, ``<s>``, ```` <code> ````, ````` <pre> `````, ````` <pre><code class="..."> `````,
``<a>``, ``<blockquote>``/``<blockquote expandable>``. Standard Markdown has no
direct mapping for headings, lists, tables or hr; this module maps them onto that
limited set (headings → bold, lists → ``•``/numbered lines, tables → a ``<pre>``
monospace block, hr → dropped).

Why a small hand-rolled parser instead of ``markdown-it-py``/``mistune``:

- The target set is narrow and the HTML escaping rule (escape ``<`` ``>`` ``&``
  *after* deciding what is a tag) is the #1 source of bugs. A purpose-built
  tokenizer keeps the "escape literals, keep generated tags raw" invariant
  explicit and testable.
- We avoid a heavyweight dependency for a handful of constructs and keep exact
  control over unsupported-markdown degradation (headings/lists/tables).
- Anything outside the recognised constructs is passed through escaped, so it
  degrades gracefully instead of being mangled.

The converter is *never* expected to raise: unterminated inline delimiters
(``**bold`` without a closer) are closed at end-of-input so the output is always
structurally well-formed. Telegram may still reject edge cases, in which case the
caller's ``send_html`` falls back to plain text.
"""

from __future__ import annotations

import re

# Quote blocks longer than this (in characters) are rendered as expandable.
EXPANDABLE_QUOTE_CHARS = 400
# Quote blocks taller than this (in lines) are rendered as expandable.
EXPANDABLE_QUOTE_LINES = 6

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_HORIZONTAL_RULE = re.compile(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$")
_FENCE = re.compile(r"^\s*(```+|~~~+)\s*([\w.+-]*)\s*$")
_UL_ITEM = re.compile(r"^(\s*)(?:[-*+])\s+(.*)$")
_OL_ITEM = re.compile(r"^(\s*)(\d+[.)])\s+(.*)$")
_QUOTE = re.compile(r"^\s*> ?(.*)$")

# One combined tokenizer for all inline constructs. The order matters: code and
# bold are checked before single-char emphasis so ``**bold**`` and `` `code` ``
# are not split by ``*``/``_``. Boundaries: emphasis needs a non-alphanumeric
# opener to avoid (but never force) word-internal ``snake_case_name``.
_INLINE = re.compile(
    r"(?P<cd>`+)(?P<cbody>[^`]+?)(?P=cd)"            # inline code
    r"|(?P<bd>\*\*|__)(?P<bbody>.+?)(?P=bd)"          # bold
    r"|(?P<st>~~)(?P<sbody>.+?)(?P=st)"               # strikethrough
    r"|(?P<it>(?<!\w)[*_])(?P<ibody>.+?)(?P=it)(?!\w)"  # italic
    r"|!?\[(?P<label>[^\]\n]*)\]\((?P<url>[^)\n]+)\)"  # link / image
)

_ESCAPE = {"<": "&lt;", ">": "&gt;", "&": "&amp;"}


def markdown_to_telegram_html(text: str) -> str:
    """Convert ``text`` (markdown) into Telegram-compatible HTML."""
    if text is None or text == "":
        return ""
    return "\n".join(_block_lines(text.split("\n")))


def escape(text: str) -> str:
    """Escape ``< > &`` in literal (non-tag) text."""
    if not text:
        return text
    return "".join(_ESCAPE.get(ch, ch) for ch in text)


# ---- block-level handling -----------------------------------------------------


def _block_lines(lines: list[str]) -> list[str]:
    out: list[str] = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        fence = _FENCE.match(line)
        if fence:
            i = _consume_fence(out, lines, i, fence)
            continue
        if _HORIZONTAL_RULE.match(line):
            i += 1
            continue
        if not line.strip():
            i += 1
            continue
        heading = _HEADING.match(line)
        if heading:
            out.append(f"<b>{_inline(heading.group(2))}</b>")
            i += 1
            continue
        if _QUOTE.match(line):
            i = _consume_quote(out, lines, i)
            continue
        if _is_table(lines, i):
            i = _consume_table(out, lines, i)
            continue
        if _UL_ITEM.match(line) or _OL_ITEM.match(line):
            i = _consume_list(out, lines, i)
            continue
        out.append(_inline(line.rstrip()))
        i += 1
    return out


def _consume_fence(out: list[str], lines: list[str], i: int, m: re.Match[str]) -> int:
    """Emit one fenced code block starting at ``lines[i]``; return next index."""
    lang = escape(m.group(2).strip())
    body: list[str] = []
    j = i + 1
    while j < len(lines) and not _FENCE.match(lines[j]):
        body.append(lines[j])
        j += 1
    # if j hit end-of-input, the fence was unterminated — still emit valid HTML
    code = escape("\n".join(body))
    if lang:
        out.append(f'<pre><code class="language-{lang}">{code}</code></pre>')
    else:
        out.append(f"<pre><code>{code}</code></pre>")
    return min(j + 1, len(lines))


def _consume_quote(out: list[str], lines: list[str], i: int) -> int:
    """Emit a ``<blockquote>`` covering the run of ``> `` lines from ``lines[i]``."""
    body: list[str] = []
    j = i
    while j < len(lines):
        m = _QUOTE.match(lines[j])
        if m:
            body.append(m.group(1))
            j += 1
        elif not lines[j].strip():
            body.append("")
            j += 1
        else:
            break
    inner = "<br/>".join(_inline(b) for b in body).strip()
    inner = inner.rstrip("<br/>").strip()
    if len(inner) > EXPANDABLE_QUOTE_CHARS or len(body) >= EXPANDABLE_QUOTE_LINES:
        out.append(f"<blockquote expandable>{inner}</blockquote>")
    else:
        out.append(f"<blockquote>{inner}</blockquote>")
    return j


def _consume_list(out: list[str], lines: list[str], i: int) -> int:
    """Emit list items with manual markers (no <ul>/<li>); return next index."""
    j = i
    items: list[tuple[int, str, str]] = []  # (indent, marker, content)
    while j < len(lines):
        line = lines[j]
        ul = _UL_ITEM.match(line)
        ol = _OL_ITEM.match(line)
        if ul:
            items.append((len(ul.group(1)), "•", ul.group(2)))
        elif ol:
            items.append((len(ol.group(1)), ol.group(2), ol.group(3)))
        elif line.strip() and not (_QUOTE.match(line) or _FENCE.match(line)):
            # continuation line (wrapped text) belongs to the previous item
            indent = len(line) - len(line.lstrip())
            items.append((indent, "", line.strip()))
        else:
            break
        j += 1
    for indent, marker, content in items:
        pad = "  " * (indent // 2)
        prefix = f"{pad}{marker} " if marker else f"{pad}  "
        out.append(f"{prefix}{_inline(content.rstrip())}")
    return j


def _is_table(lines: list[str], i: int) -> bool:
    if i + 1 >= len(lines):
        return False
    return "|" in lines[i] and _is_sep_row(lines[i + 1])


def _is_sep_row(line: str) -> bool:
    stripped = line.strip()
    return bool("-" in stripped and re.fullmatch(r"\|?[\s:|-]+\|?", stripped or ""))


def _consume_table(out: list[str], lines: list[str], i: int) -> int:
    """Emit a markdown table as a monospace ``<pre>``, dropping the separator row."""
    rows: list[str] = []
    j = i
    # consume the header row + separator + any following rows that still hold pipes
    while j < len(lines) and "|" in lines[j]:
        rows.append(lines[j])
        j += 1
    body_rows = [rows[0]] + rows[2:] if len(rows) >= 2 else rows
    text = "\n".join(_strip_table_row(r) for r in body_rows)
    out.append(f"<pre><code>{escape(text)}</code></pre>")
    return j


def _strip_table_row(row: str) -> str:
    return row.strip().strip("|").strip()


# ---- inline-level handling ----------------------------------------------------


def _inline(text: str) -> str:
    """Apply inline markdown to one line, escaping literals, closing open tags.

    The scanner emits literal chunks (escaped) and generated tags (raw). Recursion
    re-runs inline parsing on link/emphasis *content* so that e.g. ``[**x**](u)``
    still bolds. Any tags still open at the end are closed.
    """
    parts: list[str] = []
    pos = 0
    for m in _INLINE.finditer(text):
        parts.append(escape(text[pos : m.start()]))
        pos = m.end()
        parts.append(_render_match(text, m))
    parts.append(escape(text[pos:]))
    return "".join(parts)


def _render_match(text: str, m: re.Match[str]) -> str:
    if m.group("cd") is not None:
        return f"<code>{escape(m.group('cbody'))}</code>"
    if m.group("bd") is not None:
        return f"<b>{_inline(m.group('bbody'))}</b>"
    if m.group("st") is not None:
        return f"<s>{_inline(m.group('sbody'))}</s>"
    if m.group("it") is not None:
        return f"<i>{_inline(m.group('ibody'))}</i>"
    if m.group("label") is not None:
        label = _inline(m.group("label"))
        url = escape(m.group("url"))
        return f'<a href="{url}">{label}</a>'
    return escape(m.group(0))
