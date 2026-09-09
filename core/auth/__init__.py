"""Token verification: a provider registry, a claims container and the
graphql_jwt decode handler.

The imports are deferred into the function so that `core.auth.keys` stays
importable from the providers without a circular import.
"""


def decode(token, context=None):
    """GRAPHQL_JWT["JWT_DECODE_HANDLER"]: verify a token, return its payload.

    Both token shapes are accepted for the whole migration window: the
    deployment-key form, selected by the `kid` header, and the per-user-key form
    every deployment carries today. Encoding is still `core.jwt`'s.
    """
    from core.auth.registry import resolve

    return dict(resolve(token).verify(token).raw)
