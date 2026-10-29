"""Parse the body GitHub produces from .github/ISSUE_TEMPLATE/add-item.yml."""

from __future__ import annotations

import re

from ..textutil import URL_RE

FIELDS = {
    "link": "link",
    "notes": "notes",
    "images": "image_mode",
    "image mode": "image_mode",
    "manual details": "manual",
}
IMAGE_MODES = ("auto", "link", "ai")


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

    out = {"link": "", "notes": "", "image_mode": "auto", "manual": ""}
    for label, value in sections.items():
        if value == "_No response_":
            value = ""
        for prefix, key in FIELDS.items():
            if label.startswith(prefix):
                out[key] = value
                break

    mode = out["image_mode"].lower().split()[0] if out["image_mode"] else "auto"
    out["image_mode"] = mode if mode in IMAGE_MODES else "auto"

    if out["link"]:
        m = URL_RE.search(out["link"])
        out["link"] = m.group(0) if m else ""
    elif not sections:
        # Plain issue (not the form): first URL is the link, everything else is notes.
        m = URL_RE.search(body or "")
        if m:
            out["link"] = m.group(0)
            out["notes"] = (body.replace(m.group(0), "")).strip()
        else:
            out["manual"] = (body or "").strip()
    return out
