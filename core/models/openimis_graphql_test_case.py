import json
from django.conf import settings
from graphene_django.utils.testing import GraphQLTestCase
import uuid
import logging
from graphene import DateTime as graphene_DateTime
import datetime
import time
from django.test import RequestFactory
from django.middleware.csrf import get_token
from graphql_jwt.shortcuts import get_token as get_token_jwt
from django.contrib.auth.models import AnonymousUser
from django.contrib.sessions.backends.db import SessionStore
from django.core.cache import cache
from core.utils import clear_current_user
from django.db import transaction

logger = logging.getLogger(__name__)


class BaseTestContext:
    def __init__(self, user=None, method="GET", path="/", data=None, headers=None):
        """
        Initialize a test context with realistic request attributes.

        Args:
            user: User instance (authenticated or None for anonymous).
            method: HTTP method (e.g., "GET", "POST").
            path: URL path (e.g., "/api/endpoint/").
            data: Request payload (dict for POST/PUT, None for GET).
            headers: Custom HTTP headers (dict).
        """
        cookies = {}
        self.factory = RequestFactory()

        # Initialize session
        self.session = SessionStore()
        if user is not None:
            self.user = user
            self.session.create()  # Create a new session
            self.session["user_id"] = str(
                user.id
            )  # Store user ID or other relevant data
            self.session.save()  # Save session to generate session_key
            self.jwt = get_token_jwt(self.user, self)
            cookies["JWT"] = self.jwt
        else:
            self.user = AnonymousUser()

        # Create request
        self.method = method.upper()
        self.request = self.factory.generic(
            method=self.method,
            path=path,
            data=json.dumps(data) if data else {},  # Ensure JSON data is serialized
            content_type="application/json",
        )

        # Attach session and user to request
        self.request.session = self.session
        self.request.user = self.user

        # Set up META dictionary
        self.META = self.request.META
        self.META["REQUEST_METHOD"] = self.method
        self.META["PATH_INFO"] = path
        self.META["SERVER_NAME"] = "testserver"
        self.META["SERVER_PORT"] = "80"

        # Add CSRF token if needed
        if self.method in ["POST", "PUT", "PATCH"]:
            self.META["CSRF_COOKIE"] = get_token(self.request)
            self.request.CSRF_TOKEN = self.META["CSRF_COOKIE"]

        # Add CORS headers
        self.META["HTTP_ORIGIN"] = "http://testclient.com"
        self.META["HTTP_ACCESS_CONTROL_REQUEST_METHOD"] = self.method

        # Add custom headers
        if headers:
            for key, value in headers.items():
                meta_key = f"HTTP_{key.upper().replace('-', '_')}"
                self.META[meta_key] = value

        # Add cookies (e.g., session ID and JWT token)
        cookies["sessionid"] = self.session.session_key
        if cookies:
            cookie_string = "; ".join(
                f"{key}={value}" for key, value in cookies.items()
            )
            self.META["HTTP_COOKIE"] = cookie_string

    def update_meta(self, key, value):
        """Utility method to update META dictionary."""
        self.META[key] = value
        self.request.META = self.META

    def get_request(self):
        """Return the constructed request object."""
        return self.request

    def get_jwt(self):
        """Return the JWT token."""
        return getattr(self, "jwt", None)


class openIMISGraphQLTestCase(GraphQLTestCase):
    GRAPHQL_URL = f"/{settings.SITE_ROOT()}graphql"
    GRAPHQL_SCHEMA = True
    """
    Enhanced version that wraps every test in an atomic transaction.
    Prevents GraphQL validation errors (400) from closing the DB connection.
    """
    def _execute_test(self):
        with transaction.atomic():
            super()._execute_test()

    def run(self, result=None):
        """
        Override run() to ensure atomic block even when pytest-django calls it.
        """
        with transaction.atomic():
            super().run(result)

    @classmethod
    def setUpClass(cls):
        # cls.client=Client(cls.schema)
        clear_current_user()
        cache.clear()
        super(openIMISGraphQLTestCase, cls).setUpClass()

    def setUp(self):
        # cls.client=Client(cls.schema)
        clear_current_user()
        cache.clear()
        super().setUp()

    def get_mutation_result(
        self, mutation_uuid, token, internal=False, allow_exceptions=True
    ):
        content = None
        while True:
            # wait for the mutation to be done
            # wait for the mutation to be done
            if internal:
                filter_uuid = f""" id: "{mutation_uuid}" """
            else:
                filter_uuid = f""" clientMutationId: "{mutation_uuid}" """

            response = self.query(
                f"""
                {{
                mutationLogs({filter_uuid})
                {{
                pageInfo {{ hasNextPage, hasPreviousPage, startCursor, endCursor}}
                edges
                {{
                    node
                    {{
                        id,status,error,{
                            'clientMutationId,' if not internal
                            else ''
                        }clientMutationLabel,clientMutationDetails,requestDateTime,jsonExt
                    }}
                }}
                }}
                }}

                """,
                headers={"HTTP_AUTHORIZATION": f"Bearer {token}"},
            )
            content = json.loads(response.content)
            if "data" in content:
                if "mutationLogs" in content["data"]:
                    if "edges" in content["data"]["mutationLogs"]:
                        for e in content["data"]["mutationLogs"]["edges"]:
                            if "node" in e:
                                e = e["node"]
                                if e and "status" in e and e["status"] != 0:
                                    self._assert_mutationEdge_no_error(e)
                                    return content
                else:
                    if allow_exceptions:
                        raise ValueError("mutation has no edge field")
                    else:
                        logger.error("mutation has no edge field")
                        return content
            else:
                if allow_exceptions:
                    raise ValueError("mutation has no data field")
                else:
                    logger.error("mutation has no data field")
                    return content
            time.sleep(1)
        if self._assert_mutationEdge_no_error(content):
            return None

    def _assert_mutationEdge_no_error(self, e):

        if "error" in e and e["error"]:
            raise ValueError(
                f"At least one edge of the mutation has error: {e['error']}"
            )
            return False
        elif "errors" in e and e["errors"]:
            raise ValueError(
                f"At least one edge of the mutation has error: {e['errors']}"
            )
            return False
        elif "status" in e and e["status"] == 1:
            raise ValueError("Mutation failed with status 1")
            return False
        return True

    def send_mutation_raw(self, mutation_raw, token, variables_param=None, follow=True):
        params = {"headers": {"HTTP_AUTHORIZATION": f"Bearer {token}"}}
        if variables_param:
            params["variables"] = variables_param
        response = self.query(
            mutation_raw,
            **params,
        )
        self.assertResponseNoErrors(response)
        content = json.loads(response.content)

        if follow:
            mutation_type = list(content["data"].keys())[0]
            return self.get_mutation_result(
                content["data"][mutation_type]["internalId"], token, internal=True
            )
        else:
            return json.loads(response.content)

    def send_mutation(
        self,
        mutation_type,
        input_params,
        token,
        follow=True,
        raw=False,
        add_client_mutation_id=False,
        allow_exceptions=True,
    ):
        # copy to avoid adding clientMutationId to the calling param
        input_params = dict(input_params)
        if add_client_mutation_id and "clientMutationId" not in input_params:
            input_params["clientMutationId"] = str(uuid.uuid4())
        response = self.query(
            f"""
        mutation
        {{
            {mutation_type}(input: {{
               {input_params if raw else self.build_params(input_params)}
            }})

          {{
            internalId
            {'clientMutationId' if 'clientMutationId' in input_params else ''}
          }}
        }}
        """,
            headers={"HTTP_AUTHORIZATION": f"Bearer {token}"},
        )
        if allow_exceptions:
            self.assertResponseNoErrors(response)
        content = json.loads(response.content)
        if follow:
            return self.get_mutation_result(
                content["data"][mutation_type]["internalId"],
                token,
                internal=True,
                allow_exceptions=allow_exceptions,
            )
        else:
            return content

    # This validates the status code and if you get errors
    def build_params(self, params):
        def wrap_arg(v):
            if isinstance(v, uuid.UUID):
                return f'"{str(v).lower()}"'
            if isinstance(v, str):
                return f'"{str(v)}"'
            if isinstance(v, list):
                return f"[{','.join([str(wrap_arg(vv)) for vv in v])}]"
            if isinstance(v, dict):
                return str(self.build_params(v))
            if isinstance(v, bool):
                return str(v).lower()
            if isinstance(v, datetime.date):
                return graphene_DateTime.serialize(
                    datetime.datetime.fromordinal(v.toordinal())
                )
            return v

        params_as_args = [
            f"{k}:{wrap_arg(v)}" for k, v in params.items() if v is not None
        ]
        return ", ".join(params_as_args)

    def tearDown(self):
        cache.clear()
        clear_current_user()
        super().tearDown()
