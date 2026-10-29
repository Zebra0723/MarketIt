from __future__ import annotations


class LLMError(RuntimeError):
    pass


class LLM:
    name = "base"

    def __init__(self, model: str | None = None):
        self.model = model

    @classmethod
    def available(cls) -> bool:
        return True

    def complete(self, prompt: str, system: str | None = None, json_mode: bool = False) -> str:
        raise NotImplementedError
