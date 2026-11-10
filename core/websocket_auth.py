from channels.db import database_sync_to_async
from graphql_jwt.settings import jwt_settings
from graphql_jwt.shortcuts import get_user_by_token


class JwtCookieAuthMiddleware:
    """Authenticate Channels connections with the same JWT cookie as GraphQL."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        user = scope.get("user")
        token = scope.get("cookies", {}).get(jwt_settings.JWT_COOKIE_NAME)
        if (user is None or not user.is_authenticated) and token:
            try:
                scope["user"] = await database_sync_to_async(get_user_by_token)(token)
            except Exception:
                # The subscription resolver rejects anonymous connections. Keep
                # malformed or expired credentials out of application logs.
                pass
        return await self.app(scope, receive, send)
