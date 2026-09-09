def decode(token, context=None):
    """GRAPHQL_JWT["JWT_DECODE_HANDLER"]. Accepts both token shapes."""
    # Imported here, not at module level: the providers import core.auth.keys.
    from core.auth.registry import resolve

    return dict(resolve(token).verify(token).raw)
