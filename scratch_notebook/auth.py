from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from fastmcp.server.auth.auth import AccessToken, AuthProvider


@dataclass(slots=True)
class TokenRecord:
    principal: str
    token: str


class ScratchTokenAuthProvider(AuthProvider):
    """Simple bearer-token verifier backed by the static config registry."""

    def __init__(
        self,
        tokens: Mapping[str, str],
        *,
        base_url: str | None = None,
        required_scopes: list[str] | None = None,
    ) -> None:
        super().__init__(base_url=base_url, required_scopes=required_scopes)
        cleaned: dict[str, str] = {}
        reverse: dict[str, str] = {}
        for principal, token in tokens.items():
            if not principal or not token:
                continue
            normalized_principal = str(principal).strip()
            normalized_token = str(token).strip()
            if not normalized_principal or not normalized_token:
                continue
            cleaned[normalized_principal] = normalized_token
            reverse[normalized_token] = normalized_principal
        self._tokens: dict[str, str] = cleaned
        self._token_to_principal: dict[str, str] = reverse

    async def verify_token(self, token: str) -> AccessToken | None:
        """Return an access token when the bearer token matches the registry."""

        if not token:
            return None
        principal = self._token_to_principal.get(token.strip())
        if principal is None:
            return None
        scopes = list(self.required_scopes) if self.required_scopes else []
        return AccessToken(
            token=token,
            client_id=principal,
            scopes=scopes,
            claims={"tenant_id": principal},
        )

    @property
    def tokens(self) -> dict[str, str]:
        return dict(self._tokens)
