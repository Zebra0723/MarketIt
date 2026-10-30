"""Tiny GitHub REST client for issue comments (uses the Actions GITHUB_TOKEN)."""

from __future__ import annotations

import logging

from . import http
from .config import env, redact

log = logging.getLogger(__name__)
API = "https://api.github.com"


class GitHub:
    def __init__(self, token: str, repo: str):
        self.repo = repo
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        self._public: bool | None = None

    @classmethod
    def from_env(cls) -> "GitHub | None":
        token, repo = env("GITHUB_TOKEN"), env("GITHUB_REPOSITORY")
        return cls(token, repo) if token and repo else None

    def comment(self, issue: int, body: str) -> int | None:
        try:
            resp = http.post(f"{API}/repos/{self.repo}/issues/{issue}/comments", json={"body": redact(body)}, headers=self.headers)
            return resp.json().get("id")
        except Exception as exc:
            log.warning("couldn't comment on issue #%s: %s", issue, exc)
            return None

    def create_issue(self, title: str, body: str, labels: list[str]) -> int | None:
        try:
            resp = http.post(f"{API}/repos/{self.repo}/issues", json={"title": title, "body": body, "labels": labels}, headers=self.headers)
            return resp.json()["number"]
        except Exception as exc:
            log.warning("couldn't create issue: %s", exc)
            return None

    def react(self, issue: int, content: str = "+1") -> None:
        """Add a reaction to an issue (GitHub ignores duplicates)."""
        try:
            http.post(f"{API}/repos/{self.repo}/issues/{issue}/reactions", json={"content": content}, headers=self.headers)
        except Exception as exc:
            log.info("couldn't react on issue #%s: %s", issue, exc)

    def add_labels(self, issue: int, labels: list[str]) -> None:
        try:
            http.post(f"{API}/repos/{self.repo}/issues/{issue}/labels", json={"labels": labels}, headers=self.headers)
        except Exception as exc:
            log.warning("couldn't label issue #%s: %s", issue, exc)

    def paged(self, path: str, params: dict, max_pages: int = 10) -> list[dict]:
        """GET a list endpoint, following pagination."""
        out, page = [], 1
        while page <= max_pages:
            batch = http.get(f"{API}/repos/{self.repo}/{path}", params={**params, "per_page": 100, "page": page},
                             headers=self.headers).json()
            out.extend(batch)
            if len(batch) < 100:
                break
            page += 1
        return out

    def repo_is_public(self) -> bool:
        if self._public is None:
            try:
                self._public = not http.get(f"{API}/repos/{self.repo}", headers=self.headers).json().get("private", True)
            except Exception:
                self._public = False
        return self._public

    def file_url(self, path_in_repo: str) -> str:
        branch = env("GITHUB_REF_NAME") or "main"
        return f"https://github.com/{self.repo}/blob/{branch}/{path_in_repo}?raw=true"
