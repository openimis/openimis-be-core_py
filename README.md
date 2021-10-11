# openIMIS Backend Core reference module
This repository holds the files of the openIMIS Backend Core reference module.
It is a required module of [openimis-be_py](https://github.com/openimis/openimis-be_py).

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)

## Code climate (develop branch)

[![Maintainability](https://img.shields.io/codeclimate/maintainability/openimis/openimis-be-core_py.svg)](https://codeclimate.com/github/openimis/openimis-be-core_py/maintainability)
[![Test Coverage](https://img.shields.io/codeclimate/coverage/openimis/openimis-be-core_py.svg)](https://codeclimate.com/github/openimis/openimis-be-core_py)

## LGTM

[![Total alerts](https://img.shields.io/lgtm/alerts/g/openimis/openimis-be-core_py.svg?logo=lgtm&logoWidth=18)](https://lgtm.com/projects/g/openimis/openimis-be-core_py/alerts/)

## ORM mapping:
* UUIDModel: abstract model for new entities (and later on migrated entities), enforcing the use of UUID is identifier
* VersionedModel: abstract model implementing the legacy 'in table archiving' mechanism
* HistoryModel: abstract model implementing the django-simple-history archiving mechanism with standard mutaitons 
* HistoryBusinessModel: abstract model implementing the django-simple-history archiving mechanism with ValidFrom and ValidTo date and with standard and replace mutations
* core_ModuleConfiguration > ModuleConfiguration: a generic entity each module should use to let (admin)users provide the expected configuration (via a central management console).
* core_FieldControl > FieldControl: allow to hide or mark readonly fields in UI (tables, forms,...)
* tblLanguages > Language: in openIMIS, UI language defined, by user from database (i.e. not the browser settings, request parameter,...)
* tblUsers > InteractiveUser: the openIMIS legacy users, with access to frontend (see openimis-fe_js project)
* tblRole > Role: the openIMIS legacy roles (apply only on InteractiveUser)
* tblRoleRight > RoleRight: the openIMIS legacy rights (apply only on InteractiveUser)
* tblUserRole > UserRole: m-n link between users and their roles
* tblOfficer > Officer (Known usages: policy.models.Policy and claim.models.Feedback)
* core_TechnicalUser > TechnicalUser: backend-only users (external apps using FHIR API,...)
* core_User > User: aggregate entity to bridge Django security on either InteractiveUser (i_user) or TechnicalUser (t_user)
* core_User_groups > UserGroup: bridge of custom User model to Django permission model
* core_Mutation_Log > MutationLog: the generic audit/tracking of any GraphQL mutation (payload as json)


## Listened Django Signals
None

## GraphQL Queries
* module_configurations
* mutation_logs
* role
* role_right
* modules_permissions
* languages

## GraphQL Mutations
* createRole
* updateRole
* deleteRole
* duplicateRole

## Generic features

### Calendars
This module provides a configurable calendar 'mount' abstracting all calendar aspects(fields, dates and calculations,...) from the other modules.
Using the core.calendar and core.datetime, you enable your module to non-Gregorian calendars.
Today, openIMIS supports Gregorian and Nepali calendars.
The mounted calendar and datetime provide helpers method to perform date calculations according to the configured calendar (add months, years,....)

Ensure you profit from this feature by importing calendar and datetime from core instead of the python standard ones:
```
from core import calendar, datetime
```
Your models should also use the provided custom fields:
```
from core.fields import DateField, DateTimeField
```

### UserManager
openIMIS backend is configured for SSO, receiving the user (login) in the REMOTE_USER http header. Since django security is defined uppon User (core_User table), the UserManager auto-provision the received login (REMOTE_USER) as User, binding it (i_user) to the corresponding InteractiveUser record.
The auto-provisioning assigns a default Group (name can be parameterized) from which django permissions are calculated (with UserRole - Role - RoleRight contributed from InteractiveUser).
Note: if not existing, the default group is created at startup.

### Mutations & Signals
The OpenIMISMutation class of this module provides the template code for
all openIMIS mutations. Based on "async_mutations" it detaches (or not)
the processing to a workers process (via queuing). It also automatically
triggers 4 signals per mutation: one at a global level (should you want
to listen to all mutations, regardless of module) and 3 at module level:
* **signal_mutation_module_validate**: this is called when validating the
  requested mutation. Returning errors here will reject the mutation
  (see below)
* **signal_mutation_module_before_mutating**: sent after the validation and
  before performing the actual mutation
* **signal_mutation_module_after_mutating**: sent when the mutation has
  finished

To register a module on a (mutation) signal, one can register a callback
via bind_signals() in his module's schema.py file.

```
from core.schema import signal_mutation_module_validate, signal_mutation_module_before_mutating, signal_mutation_module_after_mutating


def on_claim_mutation(sender, **kwargs):
    errors = []
    # errors.extend(trigger_my_extension(kwargs))
    return errors


def bind_signals():
    signal_mutation_module_validate["claim"].connect(on_claim_mutation)
```

If the callback raises an exception, the mutation is marked as failed,
with a generic error message.

If the callback returns an array of error message:
```
[{'message': 'message to the user', 'code': 'optional error code', 'detail': 'optional error detail'}]
```
If the callback returns None (or an empty array), the mutation is marked as successful.

__Important Note__: by default the callback is executed __in transaction__ and, as a consequence, will (in case of exception/errors) cancel the complete mutation. If this is not the desired behaviour, the callback must explicitely detach to separate transaction (process).

#### Service signals 
In addition, the core provides the possibility to register additional signals via 
the `register_service_signal` decorator. Registered signals are stored in
the `core.signals.REGISTERED_SERVICE_SIGNALS` dictionary. Signal name has to be unique.  
**Example use:**
```python
@register_service_signal('create_policy', PolicyServiceClass)
def create_policy(self, *args, **kwargs):
    ...
```
Will create new RegisteredServiceSignal instance available from  
`REGISTERED_SERVICE_SIGNALS['create_policy'].`

When running the application, the modules are searched for the `bind_service_signals()` 
function in the module_name/signals.py directory. This method should use `core.signals.bind_service_signal`
function to connect new signals. Receivers can be registered also in other places.

### Graphene Custom Types & Helper Classes/Methods
* schema.SmallInt: Integer, with values ranging from -32768 to +32767
* schema.TinyInt: Integer (8 bit), with values ranging from 0 to 255
* utils.filter_validity: many openIMIS entities have a validity_from/validity_to, this filters provides a helper implementing the vality logic based on date (today if None)
Sample usage:
```
Insuree.objects.get(
        Q(chf_id=kwargs.get('chfId')),
        *filter_validity(**kwargs)
    )
```
* utils.prefix_filterset: helper method to provide dynamic filtering on related (FK) entities
Sample usage:
```
class ClaimGQLType(DjangoObjectType):
    """
    Main element for a Claim. It can contain items and/or services.
    The filters are possible on BatchRun, Insuree, HealthFacility, Admin and ICD in addition to the Claim fields
    themselves.
    """

    class Meta:
        model = Claim
        exclude_fields = ('row_id',)
        interfaces = (graphene.relay.Node,)
        filter_fields = {
            "uuid": ["exact"],
            "code": ["exact", "istartswith", "icontains", "iexact"],
            "status": ["exact"],
            "date_claimed": ["exact", "lt", "lte", "gt", "gte"],
            "date_from": ["exact", "lt", "lte", "gt", "gte"],
            "date_to": ["exact", "lt", "lte", "gt", "gte"],
            "feedback_status": ["exact"],
            "review_status": ["exact"],
            "claimed": ["exact", "lt", "lte", "gt", "gte"],
            "approved": ["exact", "lt", "lte", "gt", "gte"],
            "visit_type": ["exact"],
            **prefix_filterset("icd__", DiagnosisGQLType._meta.filter_fields),
            **prefix_filterset("admin__", ClaimAdminGQLType._meta.filter_fields),
            **prefix_filterset("health_facility__", HealthFacilityGQLType._meta.filter_fields),
            **prefix_filterset("insuree__", InsureeGQLType._meta.filter_fields),
            **prefix_filterset("batch_run__", BatchRunGQLType._meta.filter_fields)
        }
        connection_class = ExtendedConnection
```
* schema.OrderedDjangoFilterConnectionField: extension of the `graphene_django.filter.DjangoFilterConnectionField` class, providing a generic implementation of the `orderBy` GraphQL query parameter
Sample usage:
```
class Query(graphene.ObjectType):
    claims = OrderedDjangoFilterConnectionField(
        ClaimGQLType, orderBy=graphene.List(of_type=graphene.String))
```
* ExtendedConnection: extension of the `graphene.Connection` class, implementing the `totalCount` and `edgesCount` GraphQL Pagination values.

#### GQL Decorators
* @mutation_on_uuids_from_filter: additional decorator for async_mutate allowing executing mutations by filters instead
of list of uuids. Example usage (claim submit mutation from claim module):
```python
__filter_handlers = {
        'services': 'services__service__code__in',
        'items': 'items__item__code__in'
    }
...
@classmethod
@mutation_on_uuids_from_filter(Claim, ClaimGQLType, 'additional_filters', __filter_handlers)
def async_mutate(cls, user, **data):
    ...
```
### Django Admin
It also provides the admin console forms (UI), including the
TechnicalUserForm (ability to add technical users from the console)

### Django Lookup
* jsoncontains - the module introduces an additional `jsoncontains` filtering parameter to the django query, 
  which allows filtering by json field attributes in the SQL Server database. Filtering by simple data types and nested 
  arguments. The use is as follows:
  ```
  claim.objects.filter(json_ext__jsoncontains={'amount': 10.00, 'adress': { 'country': 'X', 'city': 'Y'}})
  ```
  
### WebSocket client
The module gives access to WebSocket clients allowing external socket communication. 
Two types of clients are available: 
* `BaseWebSocketClient` - for sending synchronous requests.
* `AsyncWebSocketClient` - for asynchronous communication.

Content of `send` can be string or bytes.
The `add_action_on_receive(callable)` method allows defining custom action to be performed 
when message is received from the server. If no action is set the client returns received messages in `receive()` method. 
Client require opening connection before sending and receiving messages. 
It is also possible to open connection temporally in with context:

```
socket = BaseWebSocketClient('ws://socket_url')
with websocket_instance.connect() as connection: # keeps connection open
  socket_instance.send("message") # sends message
```

    
## Additional endpoints
* core/users/current_user: provides information on the logged (in
  session) user: login, rights, attached health facility,...
  
## Abstract calculation rule class
* core/abs_calculation_rule: here is defined the abstract calculation rule class that might be used
    for defining some calculation rules.
* class is a representation of calculation rule. Here are defined some informations about rule and how some actions 
    are implemented. 
* members
  - version (static) - the version is used to keep track of the changes in the version of the calculation rule,
  - status - integer, {inactive, future, active, archived}
  - uuid (static) -  to follow the version of the calculation
  - calculation_rule_name (static) - short name of the calculation rule
  - description (static) - text about the calculation rule how works, for what purpose is defined etc
  - list of impacted class and parameters - the representation of available parameters and their values/properties for chosen model. Example:
 ```
CLASS_RULE_PARAM_VALIDATION = [
    {
        "class": "ContributionPlan",
        "parameters": [
            {
                "type": "select",
                "name": "rate",
                "label": {
                    "en": "Percentage of income",
                    "fr": "Pourcentage du salaire"
                },
                "rights": {
                    "read": "151201",
                    "write": "151202",
                    "update": "151203",
                    "replace": "151206",
                },
                'optionSet': [
                    {
                        "value": "5",
                        "label": {
                            "en": "5%",
                            "fr": "5%"
                        }
                    },
                    {
                        "value": "10",
                        "label": {
                            "en": "10%",
                            "fr": "10%"
                        }
                    },
                    {
                        "value": "15",
                        "label": {
                            "en": "15%",
                            "fr": "15%"
                        }
                    },
                ],
                "default": "5"
            },
   },
]
```
* abstract methods defined on rule level
  - ready() - method to register signals so as to wait for actions. This method makes sure the calculation is registered - status "active" 
    (if not the line should be added with "inactive status") and register the signals only if it is active
    all rules, if active will have to register to the signal sent by "getRuleDetails"
  - check_calculation(instance) - this function will get the calculation relative the instance
  - active_for_object(object, context) - this method will contains the checks if the calculation need to be executed for the object on that context. 
      The default context will be:
      - create
      - update 
      - delete
      - submit
      - amend
      - replace
      - check
      - validate
     
    This function is required because the same class can have different calculation based on the object members values (like product etc)
 
  - calculate(instance, *args) - Function that will do the calculation based on the parameters
  - get_linked_class(List[classname]) - that function will return the possible instance that can have a link to the calculation
* generic methods defined on abstract class level
  - get_rule_name(classname) - return an object which is representation of calculaton rule
  - get_rule_details(classname) - return the data about class and parameters
  - get_parameters(class_name, instance) - Function to obtain the required parameter and its properties for an instance of certain model. 
      This function is registered to the module signal via the ready function if the rule is active
  - run_calculation_rules(instance, context) - trigger the calculations. This function is registered to the module signal via the ready function if the rule is active 

## Configuration options (can be changed via core.ModuleConfiguration)
* auto_provisioning_user_group: assigned user group when REMOTE_USER
  user is auto-provisioned(default: "user")
* calendar_package: the package from which to mount the calendar (default: "core")
* calendar_module: the module mounted as calendar (default:
  ".calendars.ad_calendar", pre-canned alternative:
  ".calendars.ne_calendar")
* datetime_package: the package from which to mount the datetime (default: "core")
* datetime_module: the module mounted as datetime (default:
  ".datetimes.ad_datetime", pre-canned alternative:
  ".datetimes.ne_datetime")
* shortstrfdate: short format date when printing to screen, in logs,...
  (default: "%d/%m/%Y")
* longstrfdate: short format date when printing to screen, in logs,...
  (default: "%a %d %B %Y")
* iso_raw_date: wherever iso date format is (true=)in 'local' calendar
  or (false=)gregorian calendar (default: "False", to keep valid iso
  dates for 30/02/2076 and the like)
* age_of_majority: (default: "18")
* async_mutations: wherever mutations are (true=) processed via message
  queuing or (false=) in interactive server process (default: "False")
* currency: Country currency (default: "$")
* gql_query_roles_perms: required rights to call role, roleRight and modulesPermissions GraphQL Queries (default: ["152101"])
* gql_mutation_create_roles_perms: required rights to call createRole GraphQL Mutation (default: ["122002"])
* gql_mutation_update_roles_perms: required rights to call updateRole  GraphQL Mutation (default: ["122003"])
* gql_mutation_delete_roles_perms: required rights to call deleteRole GraphQL Mutation (default: ["152104"])
* gql_mutation_duplicate_roles_perms: required rights to call duplicateRole GraphQL Mutation (default: ["152105"])

## openIMIS Modules Dependencies
N.A.
