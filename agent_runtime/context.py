from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentContext:
    user: Any
    authenticated_client_id: str
    scopes: frozenset[str]
    request_id: str
    audit_extra: dict[str, Any] = field(default_factory=dict)

    @property
    def authenticated_actor_id(self) -> str:
        return str(self.user.pk)
