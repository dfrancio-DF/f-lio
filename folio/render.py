"""Markdown rendering shared by the native app and its UI checks."""

import html
import math
import re
import unicodedata
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from markdown_it import MarkdownIt
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name
from pygments.util import ClassNotFound


def highlight_code(code, language, _attrs):
    try:
        lexer = get_lexer_by_name(language)
    except ClassNotFound:
        return ""
    return highlight(code, lexer, HtmlFormatter(nowrap=True))


class SafeHTML(HTMLParser):
    """Allow document markup, never executable content or page-level styles."""

    allowed = set("p br hr h1 h2 h3 h4 h5 h6 a img em strong del s blockquote pre code ul ol li table thead tbody tr th td details summary kbd mark sup sub div span input dl dt dd figure figcaption abbr".split())
    void = {"br", "hr", "img", "input"}
    blocked = {"script", "style", "iframe", "object", "embed", "svg", "math", "template"}

    def __init__(self, base_uri):
        super().__init__(convert_charrefs=True)
        self.base_uri = base_uri
        self.parts = []
        self.suppressed = []

    def handle_starttag(self, tag, attrs):
        if tag in self.blocked:
            self.suppressed.append(tag)
            return
        if self.suppressed or tag not in self.allowed:
            return
        clean = []
        for key, value in attrs:
            value = value or ""
            if key in {"href", "src"}:
                if (key == "src" and tag != "img") or (key == "href" and tag != "a"):
                    continue
                value = re.sub(r"[\x00-\x1f\x7f]", "", value).strip()
                parsed = urlsplit(value)
                if parsed.scheme.lower() not in {"", "http", "https", "file", "mailto"}:
                    continue
                if key == "src" and parsed.scheme == "mailto":
                    continue
                if not value.startswith("#"):
                    value = urljoin(self.base_uri, value)
            elif key == "class":
                value = " ".join(c for c in value.split() if re.fullmatch(r"[\w-]+", c))
            elif key in {"alt", "title", "id", "colspan", "rowspan", "start", "align"}:
                pass
            elif tag == "input" and key in {"checked", "disabled"}:
                value = key
            else:
                continue
            clean.append(f'{key}="{html.escape(value, quote=True)}"')
        if tag == "input":
            clean.extend(['type="checkbox"', 'disabled="disabled"'])
        self.parts.append(f"<{tag}{(' ' + ' '.join(clean)) if clean else ''}>")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.void:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if self.suppressed:
            if tag == self.suppressed[-1]:
                self.suppressed.pop()
            return
        if tag in self.allowed and tag not in self.void:
            self.parts.append(f"</{tag}>")

    def handle_data(self, data):
        if not self.suppressed:
            self.parts.append(html.escape(data))


def render_document(source, path=None):
    parser = MarkdownIt("commonmark", {"html": True, "highlight": highlight_code})
    parser.enable(["table", "strikethrough"])
    tokens = parser.parse(source)
    headings, used = [], set()
    for index, token in enumerate(tokens):
        if token.type == "heading_open":
            inline = tokens[index + 1]
            title = "".join(child.content for child in (inline.children or []) if child.type in {"text", "code_inline", "image"})
            slug = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode().lower()
            slug = re.sub(r"[^\w-]+", "-", slug).strip("-") or "secao"
            anchor, suffix = slug, 1
            while anchor in used:
                anchor = f"{slug}-{suffix}"
                suffix += 1
            used.add(anchor)
            token.attrSet("id", anchor)
            headings.append({"id": anchor, "title": title, "level": int(token.tag[1])})
        elif token.type == "inline" and index and tokens[index - 1].type == "paragraph_open":
            children = token.children or []
            if children and children[0].type == "text":
                match = re.match(r"^\[([ xX])\] ", children[0].content)
                if match:
                    children[0].content = children[0].content[4:]
                    checkbox = parser.parseInline("")[0]
                    checkbox.type = "html_inline"
                    checkbox.content = '<input type="checkbox" disabled' + (' checked' if match[1].lower() == "x" else '') + '> '
                    children.insert(0, checkbox)
    rendered = parser.renderer.render(tokens, parser.options, {})
    base = Path(path).resolve().as_uri() if path else "file:///"
    cleaner = SafeHTML(base)
    cleaner.feed(rendered)
    count = len(re.findall(r"\b[\wÀ-ÿ]+\b", source))
    return {
        "html": "".join(cleaner.parts),
        "headings": headings,
        "title": next((h["title"] for h in headings if h["level"] == 1), Path(path).stem if path else "Bem-vindo ao Fólio"),
        "words": count,
        "minutes": max(1, math.ceil(count / 220)),
        "filename": Path(path).name if path else "Comece por aqui",
        "path": str(path) if path else "",
        "folder": str(Path(path).parent) if path else "Seu espaço de leitura",
    }
