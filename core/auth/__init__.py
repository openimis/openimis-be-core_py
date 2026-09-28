def decode(token, context=None):
    """GRAPHQL_JWT["JWT_DECODE_HANDLER"]. Accepts both token shapes."""
    # Imported here, not at module level: the providers import core.auth.keys.
    from core.auth import revocation
    from core.auth.registry import resolve

    claims = resolve(token).verify(token)
    revocation.assert_not_revoked(claims)
    return dict(claims.raw)
