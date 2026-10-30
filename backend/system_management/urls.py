from django.urls import path

from . import views

urlpatterns = [
    path("dashboard/summary/", views.dashboard_summary),
    path("system/login-logs/", views.login_logs),
    path("system/operation-logs/", views.operation_logs),
    path("system/login-logs/bulk-delete/", views.login_logs_bulk_delete),
    path("system/login-logs/clear/", views.login_logs_clear),
    path("system/operation-logs/bulk-delete/", views.operation_logs_bulk_delete),
    path("system/operation-logs/clear/", views.operation_logs_clear),
    path("system/users/", views.system_users),
    path("system/users/<int:user_id>/", views.system_user_detail),
    path("system/users/<int:user_id>/2fa/enable/", views.system_user_2fa_enable),
    path("system/users/<int:user_id>/2fa/disable/", views.system_user_2fa_disable),
    path("system/users/<int:user_id>/2fa/reset/", views.system_user_2fa_reset),
    path("system/users/<int:user_id>/session-audit/", views.system_user_session_audit),
    path("system/roles/", views.roles),
    path("system/role-options/", views.role_options),
    path("system/roles/<int:role_id>/users/", views.role_users),
    path("system/roles/<int:role_id>/", views.role_detail),
    path("system/permissions/", views.permissions),
    path("system/settings/", views.system_settings),
    path("system/settings/<str:setting_key>/", views.system_setting_detail),
]
