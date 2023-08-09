from core.reports import user_activity, registers_status

report_definitions = [
    {
        "name": "user_activity",
        "engine": 0,
        "default_report": user_activity.template,
        "description": "User activity",
        "module": "core",
        "python_query": user_activity.user_activity_query,
        "permission": ["131207"],
    },
    {
        "name": "registers_status",
        "engine": 0,
        "default_report": registers_status.template,
        "description": "Registers status",
        "module": "core",
        "python_query": registers_status.registers_status_query,
        "permission": ["131209"],
    },
]
