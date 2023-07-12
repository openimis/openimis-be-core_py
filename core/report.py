from core.reports import user_activity

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
]
