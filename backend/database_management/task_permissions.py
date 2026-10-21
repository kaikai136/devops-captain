from accounts.permissions import has_feature_permission


def can_view_table_operation(user, mode):
    required = {
        "structure": ("view_data", "manage_schema"),
        "data": ("view_data", "modify_data"),
        "copy": ("view_data", "modify_data", "import_export"),
    }.get(mode)
    return bool(required and all(
        has_feature_permission(user, "databaseManagement", permission)
        for permission in required
    ))


def can_view_transfer_payload(user, task):
    if has_feature_permission(user, "databaseManagement", "import_export"):
        return True
    return task.get("scope") == "table-operation" and can_view_table_operation(user, task.get("operationMode"))


def can_monitor_transfer_tasks(user):
    if has_feature_permission(user, "databaseManagement", "import_export"):
        return True
    return any(can_view_table_operation(user, mode) for mode in ("structure", "data"))
