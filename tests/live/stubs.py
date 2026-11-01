"""A scripted stand-in for an OpenAI-compatible async client."""
import json
from types import SimpleNamespace as NS


def tool_call(name: str, **args):
    return NS(id=f"call_{name}", type="function", function=NS(name=name, arguments=json.dumps(args)))


def reply(content: str | None = None, tools: list | None = None):
    return NS(choices=[NS(message=NS(content=content, tool_calls=tools or None))])


class StubClient:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests: list[dict] = []
        self.chat = NS(completions=NS(create=self._create))

    async def _create(self, **kwargs):
        self.requests.append(kwargs)
        return self.responses.pop(0) if self.responses else reply("done")
