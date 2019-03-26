| :bomb: Disclaimer |
| --- |
| This repository currently only contains bootsrapping material for the modularized openIMIS. Don't use it (or even connect it) to a production database. |

# openIMIS Backend Core reference module
This repository holds the files of the openIMIS Backend Core reference module.

It provides following basis entities:
* User and Language
* UUIDModel: abstract model for new entities (and later on migrated entities), enforcing the use of UUID is identifier
* ModuleConfiguration: a generic entity each module should use to let (admin)users providing the expected configuration (via a central management console).

Note:
openimis-be-core itself uses the ModuleConfiguration to define which calendar to 'mount'.
For example, to mount the nepali calendar (instead of the default gregorian one), set the following keys in the 'core' ModuleConfigyration:
```
{
    "calendar_module": ".calendars.ne_calendar",
    "datetime_module": ".datetimes.ne_datetime",
}
```

The core also exposes the configured calendar to be used instead of the standard python (gregorian) calendar. This calendar is dedicated to be switchable (and today openIMIS supports gregorian and nepali calendars) and provides helpers method to perform date calculations according to the configured calendar (add months, years,....)

Ensure you profit from this feature by importing calendar and datetime from core instead of the python standard ones:
```
from core import calendar, datetime
```
Your models should also use the provided custom fields:
```
from core.fields import DateField, DateTimeField
```