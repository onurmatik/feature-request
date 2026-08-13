from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings


@dataclass
class ContractApplicationError(Exception):
    code: str
    request_id: str
    details: dict

    @property
    def envelope(self):
        definition = settings.AGENT_CONTRACT["application_errors"][self.code]
        return {
            "code": self.code,
            "message": definition["message"],
            "retryable": definition["retryable"],
            "request_id": self.request_id,
            "details": self.details,
        }


class MissingScopeError(PermissionError):
    def __init__(self, required_scopes):
        self.required_scopes = tuple(required_scopes)
        super().__init__("OAuth scope is insufficient.")


def app_error(code: str, request_id: str, **details):
    return ContractApplicationError(code=code, request_id=request_id, details=details)
