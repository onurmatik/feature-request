"""Shared primitives for embedding OAuth-backed MCP servers in Django products."""

__version__ = "0.3.0"

from .challenges import build_auth_failure_challenge, build_bearer_challenge
from .cimd import (
    ClientMetadataDocument,
    ClientMetadataError,
    fetch_client_metadata_document,
    parse_client_metadata_document,
    validate_client_metadata_url,
)
from .dcr import (
    DynamicClientRegistrationError,
    PublicClientRegistration,
    parse_public_client_registration,
)
from .http import MCPAuthCORSMiddleware, non_header_bearer_sources
from .metadata import (
    build_authorization_server_metadata,
    build_protected_resource_metadata,
    validated_scope_catalog,
)
from .oauth import credential_digest, generate_opaque_credential, normalize_scopes
from .redirects import (
    CallbackProfile,
    callback_profile,
    redirect_uri_matches,
    validate_registered_redirect_uri,
)
from .resource import (
    CanonicalResourceError,
    canonical_resource_equal,
    canonical_resource_from_pairs,
    validate_canonical_url,
)
from .tokens import DigestTokenVerifier

__all__ = [
    "CallbackProfile",
    "CanonicalResourceError",
    "ClientMetadataDocument",
    "ClientMetadataError",
    "DigestTokenVerifier",
    "DynamicClientRegistrationError",
    "MCPAuthCORSMiddleware",
    "PublicClientRegistration",
    "build_auth_failure_challenge",
    "build_authorization_server_metadata",
    "build_bearer_challenge",
    "build_protected_resource_metadata",
    "callback_profile",
    "canonical_resource_equal",
    "canonical_resource_from_pairs",
    "credential_digest",
    "fetch_client_metadata_document",
    "generate_opaque_credential",
    "non_header_bearer_sources",
    "normalize_scopes",
    "parse_client_metadata_document",
    "parse_public_client_registration",
    "redirect_uri_matches",
    "validate_canonical_url",
    "validate_client_metadata_url",
    "validate_registered_redirect_uri",
    "validated_scope_catalog",
]
