"""Parse the body GitHub produces from .github/ISSUE_TEMPLATE/add-item.yml."""

from __future__ import annotations

import re

from ..textutil import URL_RE

FIELDS = {
    "lego ideas link": "link",
    "link": "link",
    "notes": "notes",
}


def parse_issue_form(body: str) -> dict:
    sections: dict[str, str] = {}
    current = None
    lines: list[str] = []
    for line in (body or "").splitlines():
        heading = re.match(r"^###\s+(.*?)\s*$", line)
        if heading:
            if current:
                sections[current] = "\n".join(lines).strip()
            current, lines = heading.group(1).strip().lower(), []
        elif current:
            lines.append(line)
    if current:
        sections[current] = "\n".join(lines).strip()

    out = {"link": "", "notes": ""}
    for label, value in sections.items():
        if value == "_No response_":
            value = ""
        for prefix, key in FIELDS.items():
            if label.startswith(prefix):
                out[key] = value
                break

    if out["link"]:
        m = URL_RE.search(out["link"])
        out["link"] = m.group(0) if m else ""
    elif not sections:
        # Plain issue (not the form): first URL is the link, everything else is notes.
        m = URL_RE.search(body or "")
        if m:
            out["link"] = m.group(0)
            out["notes"] = (body.replace(m.group(0), "")).strip()
    return out
