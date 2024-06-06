import json
from django.conf import settings
from graphene_django.utils.testing import GraphQLTestCase
import uuid
import logging
from graphene import Schema
from graphene.test import Client
import datetime
import time

logger = logging.getLogger(__name__)


class openIMISGraphQLTestCase(GraphQLTestCase):
    GRAPHQL_URL = f"/{settings.SITE_ROOT()}graphql"
    GRAPHQL_SCHEMA = True

    class BaseTestContext:
        def __init__(self, user):
            self.user = user
    # client = None
    @classmethod
    def setUpClass(cls):
        # cls.client=Client(cls.schema)
        super(openIMISGraphQLTestCase, cls).setUpClass()

    def get_mutation_result(self, mutation_uuid, token, internal=False):
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
                        id,status,error,clientMutationId,clientMutationLabel,clientMutationDetails,requestDateTime,jsonExt
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
                    raise ValueError("mutation has no edge field")
            else:
                raise ValueError("mutation has no data field")
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
            mutation_type = list(content['data'].keys())[0]
            return self.get_mutation_result(
                content['data'][mutation_type]['clientMutationId'],
                token
            )
        else:
            return json.loads(response.content)

    def send_mutation(self, mutation_type, input_params, token, follow=True, raw=False):
        if "clientMutationId" not in input_params:
            input_params["clientMutationId"] = uuid.uuid4()
        response = self.query(
            f"""
        mutation 
        {{
            {mutation_type}(input: {{
               {input_params if raw else self.build_params(input_params)}
            }})  

          {{
            internalId
            clientMutationId
          }}
        }}
        """,
            headers={"HTTP_AUTHORIZATION": f"Bearer {token}"},
        )
        self.assertResponseNoErrors(response)
        content = json.loads(response.content)
        if follow:
            return self.get_mutation_result(
                content["data"][mutation_type]["internalId"], token, internal=True
            )
        else:
            return content

    # This validates the status code and if you get errors
    def build_params(self, params):
        def wrap_arg(v):
            if isinstance(v, str):
                return f'"{v}"'
            if isinstance(v, list):
                return json.dumps(v)
            if isinstance(v, bool):
                return str(v).lower()
            if isinstance(v, datetime.date):
                return graphene.DateTime.serialize(
                    datetime.datetime.fromordinal(v.toordinal())
                )
            return v

        params_as_args = [
            f"{k}:{wrap_arg(v)}" for k, v in params.items() if v is not None
        ]
        return ", ".join(params_as_args)
