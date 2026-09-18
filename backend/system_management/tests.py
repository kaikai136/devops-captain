from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.models import Session
from django.core.management import call_command
from django.test import RequestFactory, TestCase
from django.utils import timezone
from unittest.mock import Mock, patch
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import pyotp

from accounts.models import UserProfile
from host_management.models import HostCredential, HostGroup, ManagedHost
from web_terminal.models import TerminalCommandAudit, TerminalFileAudit, TerminalSession
from .models import LoginLog, OperationLog, SystemSetting
from .dashboard import parse_cip_output
from .services import (
    BUILTIN_ADMIN_EMAIL,
    BUILTIN_ADMIN_FIRST_NAME,
    BUILTIN_ADMIN_USERNAME,
    FEATURE_PERMISSION_CODE_BY_KEY,
    PAGE_ACTION_PERMISSION_CODE_BY_KEY,
    UI_PERMISSION_CODES,
    ensure_builtin_admin,
    ensure_feature_permissions,
    cleanup_expired_logs,
    record_login_log,
    record_operation_log,
)


class LoginLogTests(TestCase):
    def test_record_login_log_saves_request_metadata(self):
        user = ensure_builtin_admin()
        request = RequestFactory().post("/api/auth/login/")
        request.META["REMOTE_ADDR"] = "127.0.0.1"
        request.META["HTTP_USER_AGENT"] = "unit-test"

        record_login_log(request, "admin", LoginLog.STATUS_SUCCESS, "登录成功", user)

        log = LoginLog.objects.get()
        self.assertEqual(log.user, user)
        self.assertEqual(log.username, BUILTIN_ADMIN_USERNAME)
        self.assertEqual(str(log.ip_address), "127.0.0.1")
        self.assertEqual(log.user_agent, "unit-test")
        self.assertEqual(log.status, LoginLog.STATUS_SUCCESS)


class OperationLogTests(TestCase):
    def test_record_operation_log_saves_request_metadata(self):
        user = ensure_builtin_admin()
        request = RequestFactory().post("/api/system/users/")
        request.user = user
        request.META["REMOTE_ADDR"] = "127.0.0.1"
        request.META["HTTP_USER_AGENT"] = "unit-test"

        record_operation_log(request, "用户管理", "新建用户", "viewer", "用户ID: 12")

        log = OperationLog.objects.get()
        self.assertEqual(log.user, user)
        self.assertEqual(log.username, BUILTIN_ADMIN_USERNAME)
        self.assertEqual(log.module, "用户管理")
        self.assertEqual(log.action, "新建用户")
        self.assertEqual(log.target, "viewer")
        self.assertEqual(log.detail, "用户ID: 12")
        self.assertEqual(str(log.ip_address), "127.0.0.1")
        self.assertEqual(log.user_agent, "unit-test")


class OperationLogApiTests(TestCase):
    def setUp(self):
        self.operator = get_user_model().objects.create_user(username="operator", password="pass", is_staff=True)
        self.client.force_login(self.operator)
        OperationLog.objects.create(
            user=self.operator,
            username="operator",
            module="用户管理",
            action="新建用户",
            target="viewer",
            detail="用户ID: 12",
            ip_address="1.1.1.1",
            user_agent="unit-test",
        )
        OperationLog.objects.create(
            user=self.operator,
            username="operator",
            module="角色管理",
            action="调整权限用户",
            target="运维角色",
            detail="绑定用户数: 1",
            ip_address="2.2.2.2",
            user_agent="unit-test",
        )

    def test_operation_log_api_filters_and_paginates(self):
        response = self.client.get(
            "/api/system/operation-logs/",
            {"module": "用户", "action": "新建", "keyword": "viewer", "ip": "1.1", "page": 1, "pageSize": 10},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["page"], 1)
        self.assertEqual(data["pageSize"], 10)
        self.assertEqual(data["results"][0]["username"], "operator")
        self.assertEqual(data["results"][0]["module"], "用户管理")
        self.assertEqual(data["results"][0]["action"], "新建用户")
        self.assertEqual(data["results"][0]["ipAddress"], "1.1.1.1")


class LoginLogApiTests(TestCase):
    def setUp(self):
        self.operator = get_user_model().objects.create_user(username="operator", password="pass", is_staff=True)
        self.client.force_login(self.operator)
        LoginLog.objects.create(
            user=self.operator,
            username="admin",
            ip_address="1.1.1.1",
            user_agent="PC / Windows 10 / Edge 149.0.0",
            status=LoginLog.STATUS_SUCCESS,
        )
        LoginLog.objects.create(
            username="admin",
            ip_address="1.1.1.1",
            user_agent="PC / Mac OS X 10.15.7 / Edge 149.0.0",
            status=LoginLog.STATUS_FAILED,
            message="用户名或密码错误，连续多次错误账户将会被禁用",
        )
        LoginLog.objects.create(
            username="guest",
            ip_address="2.2.2.2",
            user_agent="PC / Mac OS X 10.15.7 / Chrome 119.0.0",
            status=LoginLog.STATUS_SUCCESS,
        )

    def test_login_log_api_filters_and_paginates(self):
        response = self.client.get(
            "/api/system/login-logs/",
            {"username": "admin", "ip": "1.1", "status": LoginLog.STATUS_FAILED, "page": 1, "pageSize": 10},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["page"], 1)
        self.assertEqual(data["pageSize"], 10)
        self.assertEqual(data["results"][0]["username"], "admin")
        self.assertEqual(data["results"][0]["status"], LoginLog.STATUS_FAILED)
        self.assertEqual(data["results"][0]["ipAddress"], "1.1.1.1")

    def test_login_log_api_returns_requested_page(self):
        response = self.client.get("/api/system/login-logs/", {"page": 2, "pageSize": 2})

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total"], 3)
        self.assertEqual(len(data["results"]), 1)


class BuiltinAdminTests(TestCase):
    def setUp(self):
        self.operator = get_user_model().objects.create_user(username="operator", password="pass", is_staff=True)
        self.client.force_login(self.operator)

    def complete_slider(self) -> str:
        challenge_response = self.client.get("/api/auth/slider-challenge/")
        self.assertEqual(challenge_response.status_code, 200)
        challenge = challenge_response.json()
        verify_response = self.client.post(
            "/api/auth/slider-verify/",
            data={"challengeId": challenge["challengeId"], "offsetX": challenge["targetX"], "elapsedMs": 400},
            content_type="application/json",
        )
        self.assertEqual(verify_response.status_code, 200)
        return verify_response.json()["sliderToken"]

    def test_system_user_list_creates_builtin_admin(self):
        response = self.client.get("/api/system/users/")

        self.assertEqual(response.status_code, 200)
        admin = get_user_model().objects.get(username=BUILTIN_ADMIN_USERNAME)
        self.assertEqual(admin.email, BUILTIN_ADMIN_EMAIL)
        self.assertEqual(admin.first_name, BUILTIN_ADMIN_FIRST_NAME)
        self.assertTrue(admin.is_active)
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_superuser)
        self.assertTrue(admin.check_password("Admin@123456"))
        self.assertTrue(any(item["username"] == BUILTIN_ADMIN_USERNAME and item["isBuiltinAdmin"] for item in response.json()))

    def test_builtin_admin_is_bound_to_admin_role(self):
        admin = ensure_builtin_admin()

        role = Group.objects.filter(name="\u7ba1\u7406\u5458").first()

        self.assertIsNotNone(role)
        self.assertTrue(admin.groups.filter(id=role.id).exists())
        self.assertEqual(set(role.permissions.values_list("codename", flat=True)), UI_PERMISSION_CODES)

    def test_builtin_admin_password_is_not_reset_after_profile_change(self):
        admin = ensure_builtin_admin()
        admin.set_password("ChangedPass123")
        admin.save(update_fields=["password"])

        ensured = ensure_builtin_admin()

        self.assertTrue(ensured.check_password("ChangedPass123"))
        self.assertFalse(ensured.check_password("Admin@123456"))

    def test_builtin_admin_cannot_be_deleted(self):
        admin = ensure_builtin_admin()

        response = self.client.delete(f"/api/system/users/{admin.id}/")

        self.assertEqual(response.status_code, 400)
        self.assertTrue(get_user_model().objects.filter(id=admin.id).exists())

    def test_builtin_admin_core_fields_stay_fixed_when_updated(self):
        admin = ensure_builtin_admin()

        response = self.client.put(
            f"/api/system/users/{admin.id}/",
            data={
                "username": "renamed",
                "email": "renamed@example.com",
                "firstName": "Renamed",
                "isActive": False,
                "isStaff": False,
                "roleIds": [],
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        admin.refresh_from_db()
        self.assertEqual(admin.username, BUILTIN_ADMIN_USERNAME)
        self.assertEqual(admin.email, BUILTIN_ADMIN_EMAIL)
        self.assertEqual(admin.first_name, BUILTIN_ADMIN_FIRST_NAME)
        self.assertTrue(admin.is_active)
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_superuser)

    def test_builtin_admin_password_can_be_reset_from_user_list(self):
        admin = ensure_builtin_admin()

        response = self.client.put(
            f"/api/system/users/{admin.id}/",
            data={
                "username": admin.username,
                "email": admin.email,
                "firstName": admin.first_name,
                "isActive": admin.is_active,
                "isStaff": admin.is_staff,
                "roleIds": [],
                "password": "ChangedPass123",
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        admin.refresh_from_db()
        self.assertTrue(admin.check_password("ChangedPass123"))

    def test_system_user_list_returns_two_factor_status(self):
        UserProfile.objects.create(user=self.operator, totp_enabled=True, totp_secret=pyotp.random_base32())

        response = self.client.get("/api/system/users/")

        self.assertEqual(response.status_code, 200)
        operator = next(item for item in response.json() if item["username"] == "operator")
        self.assertTrue(operator["twoFactorEnabled"])
        self.assertEqual(operator["twoFactorStatus"], "enabled")

    def test_system_user_list_returns_session_audit_status(self):
        UserProfile.objects.create(user=self.operator, session_audit_enabled=False)

        response = self.client.get("/api/system/users/")

        self.assertEqual(response.status_code, 200)
        operator = next(item for item in response.json() if item["username"] == "operator")
        self.assertFalse(operator["sessionAuditEnabled"])

    def test_staff_can_require_user_two_factor_setup(self):
        target = get_user_model().objects.create_user(username="viewer", password="UserPass123")

        response = self.client.post(f"/api/system/users/{target.id}/2fa/enable/", data={}, content_type="application/json")

        self.assertEqual(response.status_code, 200)
        profile = UserProfile.objects.get(user=target)
        self.assertTrue(profile.totp_required)
        self.assertEqual(response.json()["twoFactorStatus"], "required")

    def test_staff_can_enable_existing_user_two_factor_without_rebinding(self):
        target = get_user_model().objects.create_user(username="viewer", password="UserPass123")
        secret = pyotp.random_base32()
        profile = UserProfile.objects.create(user=target, totp_enabled=False, totp_secret=secret)

        response = self.client.post(f"/api/system/users/{target.id}/2fa/enable/", data={}, content_type="application/json")

        self.assertEqual(response.status_code, 200)
        profile.refresh_from_db()
        self.assertTrue(profile.totp_enabled)
        self.assertFalse(profile.totp_required)
        self.assertEqual(profile.totp_secret, secret)
        self.assertEqual(response.json()["twoFactorStatus"], "enabled")

    def test_staff_can_disable_user_two_factor(self):
        target = get_user_model().objects.create_user(username="viewer", password="UserPass123")
        secret = pyotp.random_base32()
        profile = UserProfile.objects.create(user=target, totp_enabled=True, totp_secret=secret)

        response = self.client.post(f"/api/system/users/{target.id}/2fa/disable/", data={}, content_type="application/json")

        self.assertEqual(response.status_code, 200)
        profile.refresh_from_db()
        self.assertFalse(profile.totp_enabled)
        self.assertEqual(profile.totp_secret, secret)
        self.assertFalse(profile.totp_required)
        self.assertFalse(profile.totp_reset_required)
        self.assertEqual(response.json()["twoFactorStatus"], "disabled")

    def test_staff_disable_user_two_factor_allows_plain_login(self):
        target = get_user_model().objects.create_user(username="viewer", password="UserPass123")
        UserProfile.objects.create(user=target, totp_enabled=True, totp_secret=pyotp.random_base32())
        disable_response = self.client.post(f"/api/system/users/{target.id}/2fa/disable/", data={}, content_type="application/json")
        self.assertEqual(disable_response.status_code, 200)

        self.client.logout()
        slider_token = self.complete_slider()
        login_response = self.client.post(
            "/api/auth/login/",
            data={"account": "viewer", "password": "UserPass123", "remember": False, "sliderToken": slider_token},
            content_type="application/json",
        )

        self.assertEqual(login_response.status_code, 200)
        self.assertEqual(login_response.json()["user"]["username"], "viewer")

    def test_staff_can_reset_user_two_factor_for_rebinding(self):
        target = get_user_model().objects.create_user(username="viewer", password="UserPass123")
        old_secret = pyotp.random_base32()
        profile = UserProfile.objects.create(user=target, totp_enabled=True, totp_secret=old_secret)

        response = self.client.post(f"/api/system/users/{target.id}/2fa/reset/", data={}, content_type="application/json")

        self.assertEqual(response.status_code, 200)
        profile.refresh_from_db()
        self.assertFalse(profile.totp_enabled)
        self.assertTrue(profile.totp_required)
        self.assertEqual(profile.totp_secret, "")
        self.assertEqual(profile.totp_pending_secret, "")
        self.assertFalse(profile.totp_reset_required)
        self.assertIsNone(profile.totp_confirmed_at)
        self.assertEqual(response.json()["twoFactorStatus"], "required")

    def test_staff_reset_user_two_factor_requires_setup_on_next_login(self):
        target = get_user_model().objects.create_user(username="viewer", password="UserPass123")
        old_secret = pyotp.random_base32()
        UserProfile.objects.create(user=target, totp_enabled=True, totp_secret=old_secret)
        reset_response = self.client.post(f"/api/system/users/{target.id}/2fa/reset/", data={}, content_type="application/json")
        self.assertEqual(reset_response.status_code, 200)

        self.client.logout()
        slider_token = self.complete_slider()
        login_response = self.client.post(
            "/api/auth/login/",
            data={"account": "viewer", "password": "UserPass123", "remember": False, "sliderToken": slider_token},
            content_type="application/json",
        )

        self.assertEqual(login_response.status_code, 200)
        self.assertTrue(login_response.json()["twoFactorSetupRequired"])
        self.assertNotEqual(login_response.json()["secret"], old_secret)
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 401)

    def test_user_two_factor_actions_reject_builtin_admin_and_self(self):
        admin = ensure_builtin_admin()

        builtin_response = self.client.post(f"/api/system/users/{admin.id}/2fa/enable/", data={}, content_type="application/json")
        self_disable_response = self.client.post(f"/api/system/users/{self.operator.id}/2fa/disable/", data={}, content_type="application/json")
        self_reset_response = self.client.post(f"/api/system/users/{self.operator.id}/2fa/reset/", data={}, content_type="application/json")

        self.assertEqual(builtin_response.status_code, 400)
        self.assertEqual(self_disable_response.status_code, 400)
        self.assertEqual(self_reset_response.status_code, 400)

    def test_non_staff_cannot_manage_user_two_factor(self):
        user = get_user_model().objects.create_user(username="viewer", password="UserPass123")
        self.client.force_login(user)

        response = self.client.post(f"/api/system/users/{self.operator.id}/2fa/enable/", data={}, content_type="application/json")

        self.assertEqual(response.status_code, 403)

    def test_staff_can_toggle_user_session_audit(self):
        target = get_user_model().objects.create_user(username="viewer", password="UserPass123")

        response = self.client.post(
            f"/api/system/users/{target.id}/session-audit/",
            data={"enabled": False},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        profile = UserProfile.objects.get(user=target)
        self.assertFalse(profile.session_audit_enabled)
        self.assertFalse(response.json()["sessionAuditEnabled"])

    def test_staff_can_toggle_builtin_admin_session_audit(self):
        admin = ensure_builtin_admin()

        response = self.client.post(
            f"/api/system/users/{admin.id}/session-audit/",
            data={"enabled": False},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        profile = UserProfile.objects.get(user=admin)
        self.assertFalse(profile.session_audit_enabled)
        self.assertFalse(response.json()["sessionAuditEnabled"])

    def test_builtin_admin_can_toggle_own_session_audit(self):
        admin = ensure_builtin_admin()
        self.client.force_login(admin)

        response = self.client.post(
            f"/api/system/users/{admin.id}/session-audit/",
            data={"enabled": False},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        profile = UserProfile.objects.get(user=admin)
        self.assertFalse(profile.session_audit_enabled)

    def test_user_session_audit_actions_reject_non_builtin_self(self):
        self_response = self.client.post(
            f"/api/system/users/{self.operator.id}/session-audit/",
            data={"enabled": False},
            content_type="application/json",
        )

        self.assertEqual(self_response.status_code, 400)

    def test_non_staff_cannot_manage_user_session_audit(self):
        user = get_user_model().objects.create_user(username="viewer", password="UserPass123")
        self.client.force_login(user)

        response = self.client.post(
            f"/api/system/users/{self.operator.id}/session-audit/",
            data={"enabled": False},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)


class FeaturePermissionTests(TestCase):
    def setUp(self):
        self.operator = get_user_model().objects.create_user(username="operator", password="pass", is_staff=True)
        self.client.force_login(self.operator)

    def test_permission_api_returns_feature_permissions(self):
        response = self.client.get("/api/system/permissions/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        codenames = {item["codename"] for item in payload}
        self.assertIn(FEATURE_PERMISSION_CODE_BY_KEY["dashboard"], codenames)
        self.assertIn(FEATURE_PERMISSION_CODE_BY_KEY["hosts"], codenames)
        self.assertIn(FEATURE_PERMISSION_CODE_BY_KEY["bulkExecution"], codenames)
        self.assertIn(FEATURE_PERMISSION_CODE_BY_KEY["companyDevices"], codenames)
        self.assertIn(FEATURE_PERMISSION_CODE_BY_KEY["operationLogs"], codenames)
        self.assertIn(PAGE_ACTION_PERMISSION_CODE_BY_KEY[("hosts", "create")], codenames)
        self.assertIn(PAGE_ACTION_PERMISSION_CODE_BY_KEY[("hosts", "quick_commands")], codenames)
        self.assertIn(PAGE_ACTION_PERMISSION_CODE_BY_KEY[("bulkExecution", "execute")], codenames)
        self.assertIn(PAGE_ACTION_PERMISSION_CODE_BY_KEY[("bulkExecution", "refresh")], codenames)
        self.assertIn(PAGE_ACTION_PERMISSION_CODE_BY_KEY[("operationLogs", "refresh")], codenames)
        self.assertTrue(all(item["isFeature"] for item in payload))
        self.assertTrue(any(item["permissionType"] == "page" and item["featureKey"] == "hosts" for item in payload))
        self.assertTrue(any(item["permissionType"] == "page" and item["featureKey"] == "bulkExecution" for item in payload))
        self.assertTrue(any(item["permissionType"] == "page" and item["featureKey"] == "companyDevices" for item in payload))
        self.assertTrue(any(item["permissionType"] == "action" and item["featureKey"] == "hosts" and item["actionKey"] == "create" for item in payload))
        self.assertTrue(any(item["permissionType"] == "action" and item["featureKey"] == "bulkExecution" and item["actionKey"] == "execute" for item in payload))

    def test_role_can_store_feature_permissions(self):
        ensure_feature_permissions()
        permission = Permission.objects.get(codename=FEATURE_PERMISSION_CODE_BY_KEY["hosts"])

        response = self.client.post(
            "/api/system/roles/",
            data={"name": "主机操作员", "permissionIds": [permission.id]},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        role = Group.objects.get(name="主机操作员")
        self.assertTrue(role.permissions.filter(id=permission.id).exists())

    def test_role_list_returns_bound_user_count(self):
        role = Group.objects.create(name="绑定用户角色")
        first_user = get_user_model().objects.create_user(username="role-user-a", password="pass")
        second_user = get_user_model().objects.create_user(username="role-user-b", password="pass")
        first_user.groups.add(role)
        second_user.groups.add(role)

        response = self.client.get("/api/system/roles/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        role_payload = next(item for item in payload if item["id"] == role.id)
        self.assertEqual(role_payload["userCount"], 2)

    def test_role_users_can_update_bound_users(self):
        role = Group.objects.create(name="权限用户角色")
        previous_role = Group.objects.create(name="旧角色")
        first_user = get_user_model().objects.create_user(username="role-bound-a", password="pass")
        second_user = get_user_model().objects.create_user(username="role-bound-b", password="pass")
        first_user.groups.add(role)
        second_user.groups.add(previous_role)

        response = self.client.put(
            f"/api/system/roles/{role.id}/users/",
            data={"userIds": [second_user.id]},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        role.refresh_from_db()
        self.assertFalse(first_user.groups.filter(id=role.id).exists())
        self.assertTrue(second_user.groups.filter(id=role.id).exists())
        self.assertFalse(second_user.groups.filter(id=previous_role.id).exists())
        self.assertEqual(list(second_user.groups.values_list("id", flat=True)), [role.id])
        self.assertEqual(response.json()["role"]["userCount"], 1)

    def test_role_users_reject_builtin_admin(self):
        role = Group.objects.create(name="内置管理员保护角色")
        admin = ensure_builtin_admin()

        response = self.client.put(
            f"/api/system/roles/{role.id}/users/",
            data={"userIds": [admin.id]},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(admin.groups.filter(id=role.id).exists())

    def test_system_user_create_writes_operation_log(self):
        response = self.client.post(
            "/api/system/users/",
            data={
                "username": "logged-user",
                "firstName": "Logged User",
                "password": "UserPass123",
                "isActive": True,
                "roleIds": [],
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        log = OperationLog.objects.get(action="新建用户")
        self.assertEqual(log.username, "operator")
        self.assertEqual(log.module, "用户管理")
        self.assertEqual(log.target, "logged-user")

    def test_role_users_update_writes_operation_log(self):
        role = Group.objects.create(name="日志角色")
        user = get_user_model().objects.create_user(username="logged-role-user", password="pass")

        response = self.client.put(
            f"/api/system/roles/{role.id}/users/",
            data={"userIds": [user.id]},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        log = OperationLog.objects.get(action="调整权限用户")
        self.assertEqual(log.module, "角色管理")
        self.assertEqual(log.target, "日志角色")
        self.assertIn("logged-role-user", log.detail)

    def test_generic_write_request_writes_operation_log(self):
        response = self.client.post(
            "/api/host-management/groups/",
            data={"name": "审计分组"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        log = OperationLog.objects.get(module="主机分组", action="新建")
        self.assertEqual(log.username, "operator")
        self.assertEqual(log.target, "审计分组")
        self.assertIn("/api/host-management/groups/", log.detail)

    def test_failed_write_request_does_not_write_operation_log(self):
        response = self.client.post(
            "/api/host-management/groups/",
            data={"name": ""},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(OperationLog.objects.filter(module="主机分组").exists())

    def test_manual_operation_log_is_not_duplicated_by_middleware(self):
        response = self.client.post(
            "/api/system/users/",
            data={
                "username": "single-log-user",
                "firstName": "Single Log User",
                "password": "UserPass123",
                "isActive": True,
                "roleIds": [],
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(OperationLog.objects.filter(module="用户管理", action="新建用户", target="single-log-user").count(), 1)

    def test_existing_page_permission_inherits_new_action_permissions(self):
        ensure_feature_permissions()
        page_permission = Permission.objects.get(codename=FEATURE_PERMISSION_CODE_BY_KEY["hosts"])
        action_permission = Permission.objects.get(codename=PAGE_ACTION_PERMISSION_CODE_BY_KEY[("hosts", "create")])
        role = Group.objects.create(name="Host viewer")
        role.permissions.add(page_permission)
        action_permission.delete()

        ensure_feature_permissions()

        action_permission = Permission.objects.get(codename=PAGE_ACTION_PERMISSION_CODE_BY_KEY[("hosts", "create")])
        self.assertTrue(role.permissions.filter(id=action_permission.id).exists())

    def test_non_staff_user_permission_can_access_and_create_system_users(self):
        ensure_feature_permissions()
        user = get_user_model().objects.create_user(username="user-manager", password="pass", is_staff=False)
        role = Group.objects.create(name="User manager")
        role.permissions.add(
            Permission.objects.get(codename=FEATURE_PERMISSION_CODE_BY_KEY["users"]),
            Permission.objects.get(codename=PAGE_ACTION_PERMISSION_CODE_BY_KEY[("users", "create")]),
        )
        user.groups.add(role)
        self.client.force_login(user)

        list_response = self.client.get("/api/system/users/")
        create_response = self.client.post(
            "/api/system/users/",
            data={
                "username": "created-by-role",
                "firstName": "Role User",
                "password": "UserPass123",
                "isActive": True,
                "roleIds": [],
            },
            content_type="application/json",
        )

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(create_response.status_code, 201)
        self.assertTrue(get_user_model().objects.filter(username="created-by-role").exists())

    def test_non_staff_user_page_permission_does_not_grant_user_write_actions(self):
        ensure_feature_permissions()
        user = get_user_model().objects.create_user(username="user-viewer", password="pass", is_staff=False)
        role = Group.objects.create(name="User viewer")
        role.permissions.add(Permission.objects.get(codename=FEATURE_PERMISSION_CODE_BY_KEY["users"]))
        user.groups.add(role)
        self.client.force_login(user)

        list_response = self.client.get("/api/system/users/")
        create_response = self.client.post(
            "/api/system/users/",
            data={"username": "blocked-user", "password": "UserPass123", "roleIds": []},
            content_type="application/json",
        )

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(create_response.status_code, 403)
        self.assertFalse(get_user_model().objects.filter(username="blocked-user").exists())

    def test_user_page_permission_can_load_role_options_without_role_management(self):
        ensure_feature_permissions()
        user = get_user_model().objects.create_user(username="user-options-viewer", password="pass", is_staff=False)
        viewer_role = Group.objects.create(name="User options viewer")
        target_role = Group.objects.create(name="Assignable role")
        viewer_role.permissions.add(Permission.objects.get(codename=FEATURE_PERMISSION_CODE_BY_KEY["users"]))
        user.groups.add(viewer_role)
        self.client.force_login(user)

        options_response = self.client.get("/api/system/role-options/")
        roles_response = self.client.get("/api/system/roles/")

        self.assertEqual(options_response.status_code, 200)
        self.assertEqual(roles_response.status_code, 403)
        self.assertIn({"id": target_role.id, "name": target_role.name}, options_response.json())
        self.assertNotIn("permissionIds", options_response.json()[0])


class DashboardSummaryApiTests(TestCase):
    def setUp(self):
        ensure_feature_permissions()
        ManagedHost.objects.all().delete()
        HostCredential.objects.all().delete()
        HostGroup.objects.all().delete()
        LoginLog.objects.all().delete()
        self.dashboard_permission = Permission.objects.get(codename=FEATURE_PERMISSION_CODE_BY_KEY["dashboard"])
        self.user = get_user_model().objects.create_user(username="viewer", password="pass")
        self.operator = get_user_model().objects.create_user(username="operator", password="pass", is_staff=True)
        self.admin = get_user_model().objects.create_superuser(username="root", password="pass")

    def test_dashboard_requires_login(self):
        response = self.client.get("/api/dashboard/summary/")

        self.assertEqual(response.status_code, 401)

    def test_dashboard_requires_access_permission(self):
        self.client.force_login(self.user)

        response = self.client.get("/api/dashboard/summary/")

        self.assertEqual(response.status_code, 403)

    @patch("system_management.dashboard.get_egress_network")
    def test_dashboard_returns_summary_for_permitted_user(self, mock_egress):
        mock_egress.return_value = {
            "ip": "203.0.113.8",
            "location": "中国 江苏 南京",
            "isp": "电信",
            "url": "http://www.cip.cc/203.0.113.8",
            "raw": "",
            "checkedAt": timezone.now().isoformat(),
            "status": "ok",
            "error": "",
        }
        role = Group.objects.create(name="dashboard-viewer")
        role.permissions.add(self.dashboard_permission)
        self.user.groups.add(role)
        group = HostGroup.objects.create(name="生产", sort_order=1)
        ManagedHost.objects.create(name="linux-01", group=group, private_ip="192.168.1.10", cpu=4, memory=8, os="ubuntu", verified=True)
        ManagedHost.objects.create(name="win-01", group=group, private_ip="192.168.1.11", cpu=8, memory=16, os="windows", verify_status="failed")
        HostCredential.objects.create(name="root-key", username="root")
        LoginLog.objects.create(user=self.user, username="viewer", ip_address="10.0.0.8", status=LoginLog.STATUS_SUCCESS)
        LoginLog.objects.create(username="viewer", ip_address="10.0.0.9", status=LoginLog.STATUS_FAILED)
        self.client.force_login(self.user)

        response = self.client.get("/api/dashboard/summary/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["users"]["total"], 4)
        self.assertEqual(payload["assets"]["total"], 2)
        self.assertEqual(payload["assets"]["verified"], 1)
        self.assertEqual(payload["assets"]["failed"], 1)
        self.assertEqual(payload["assets"]["cpuCores"], 12)
        self.assertEqual(payload["assets"]["memoryGb"], 24)
        self.assertEqual(payload["assets"]["credentials"], 1)
        self.assertEqual(payload["egressNetwork"]["ip"], "203.0.113.8")
        self.assertEqual(len(payload["loginTrend"]), 7)
        self.assertTrue(any(item["label"] == "生产" and item["value"] == 2 for item in payload["groupRanking"]))

    @patch("system_management.dashboard.get_egress_network")
    def test_superuser_can_access_dashboard_without_role_permission(self, mock_egress):
        mock_egress.return_value = {"ip": "", "location": "", "isp": "", "url": "", "raw": "", "checkedAt": "", "status": "error", "error": ""}
        self.client.force_login(self.admin)

        response = self.client.get("/api/dashboard/summary/")

        self.assertEqual(response.status_code, 200)

    @patch("system_management.dashboard.subprocess.run")
    @patch("system_management.dashboard.cache")
    def test_egress_network_parses_cip_output(self, mock_cache, mock_run):
        from .dashboard import get_egress_network

        mock_cache.get.return_value = None
        mock_run.return_value = Mock(
            returncode=0,
            stdout="IP\t: 222.94.156.34\n地址\t: 中国 江苏 南京\n运营商\t: 电信\n\nURL\t: http://www.cip.cc/222.94.156.34\n",
            stderr="",
        )

        payload = get_egress_network()

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["ip"], "222.94.156.34")
        self.assertEqual(payload["location"], "中国 江苏 南京")
        self.assertEqual(payload["isp"], "电信")

    @patch("system_management.dashboard.subprocess.run")
    @patch("system_management.dashboard.cache")
    def test_egress_network_handles_curl_failure(self, mock_cache, mock_run):
        from .dashboard import get_egress_network

        mock_cache.get.return_value = None
        mock_run.return_value = Mock(returncode=28, stdout="", stderr="operation timed out")

        payload = get_egress_network()

        self.assertEqual(payload["status"], "error")
        self.assertIn("timed out", payload["error"])

    def test_parse_cip_output_tolerates_missing_fields(self):
        parsed = parse_cip_output("地址\t: 中国 江苏 南京\n")

        self.assertEqual(parsed["ip"], "")
        self.assertEqual(parsed["location"], "中国 江苏 南京")


class SystemSettingsApiTests(TestCase):
    def setUp(self):
        self.operator = get_user_model().objects.create_user(username="operator", password="pass", is_staff=True)
        self.user = get_user_model().objects.create_user(username="viewer", password="pass", is_staff=False)
        self.client.force_login(self.operator)

    def test_staff_can_create_update_and_read_watermark_setting(self):
        response = self.client.post(
            "/api/system/settings/",
            data={
                "key": "watermark",
                "label": "水印设置",
                "description": "页面水印配置",
                "value": {"enabled": True, "text": "CAPTAIN", "pages": ["ip", "sessionAudits", "webTerminal", "ip"]},
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["value"], {"enabled": True, "text": "CAPTAIN", "pages": ["ip", "sessionAudits", "webTerminal"]})

        update_response = self.client.put(
            "/api/system/settings/watermark/",
            data={"value": {"enabled": False, "text": "", "pages": ["hosts"]}},
            content_type="application/json",
        )

        self.assertEqual(update_response.status_code, 200)
        self.assertFalse(update_response.json()["value"]["enabled"])

    def test_watermark_setting_accepts_all_navigation_pages(self):
        response = self.client.post(
            "/api/system/settings/",
            data={
                "key": "watermark",
                "value": {
                    "enabled": True,
                    "text": "CAPTAIN",
                    "pages": ["bulkExecution", "companyDevices", "securityScan"],
                },
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["value"]["pages"], ["bulkExecution", "companyDevices", "securityScan"])

    def test_logged_in_user_can_read_watermark_but_cannot_write(self):
        SystemSetting.objects.create(key="watermark", value={"enabled": True, "text": "CAPTAIN", "pages": ["ip"]})
        self.client.force_login(self.user)

        read_response = self.client.get("/api/system/settings/watermark/")
        write_response = self.client.put(
            "/api/system/settings/watermark/",
            data={"value": {"enabled": False, "text": "", "pages": []}},
            content_type="application/json",
        )

        self.assertEqual(read_response.status_code, 200)
        self.assertEqual(read_response.json()["value"]["text"], "CAPTAIN")
        self.assertEqual(write_response.status_code, 403)

    def test_logged_in_user_can_read_display_settings_but_cannot_write(self):
        SystemSetting.objects.create(key="site_identity", value={"appName": "Ops Hub", "totpIssuer": "Ops Hub"})
        self.client.force_login(self.user)

        read_response = self.client.get("/api/system/settings/site_identity/")
        write_response = self.client.put(
            "/api/system/settings/site_identity/",
            data={"value": {"appName": "Blocked"}},
            content_type="application/json",
        )

        self.assertEqual(read_response.status_code, 200)
        self.assertEqual(read_response.json()["value"]["appName"], "Ops Hub")
        self.assertEqual(write_response.status_code, 403)

    def test_site_identity_validation_normalizes_empty_fields(self):
        response = self.client.post(
            "/api/system/settings/",
            data={
                "key": "site_identity",
                "label": "品牌变量",
                "value": {"appName": "", "logoImageUrl": "/brand.png", "iconUrl": "https://example.com/icon.png"},
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()["value"]
        self.assertEqual(payload["appName"], "运维船长")
        self.assertEqual(payload["logoImageUrl"], "/brand.png")
        self.assertEqual(payload["iconUrl"], "https://example.com/icon.png")

    def test_display_setting_validation_rejects_invalid_url_color_size_weight_and_font(self):
        invalid_url = self.client.post(
            "/api/system/settings/",
            data={"key": "site_identity", "value": {"logoImageUrl": "javascript:alert(1)"}},
            content_type="application/json",
        )
        invalid_color = self.client.post(
            "/api/system/settings/",
            data={"key": "dashboard_hero", "value": {"color": "purple"}},
            content_type="application/json",
        )
        invalid_size = self.client.post(
            "/api/system/settings/",
            data={"key": "dashboard_hero", "value": {"fontSize": 72}},
            content_type="application/json",
        )
        invalid_weight = self.client.post(
            "/api/system/settings/",
            data={"key": "dashboard_hero", "value": {"fontWeight": 950}},
            content_type="application/json",
        )
        invalid_font = self.client.post(
            "/api/system/settings/",
            data={"key": "dashboard_hero", "value": {"font": "Poppins"}},
            content_type="application/json",
        )

        self.assertEqual(invalid_url.status_code, 400)
        self.assertEqual(invalid_color.status_code, 400)
        self.assertEqual(invalid_size.status_code, 400)
        self.assertEqual(invalid_weight.status_code, 400)
        self.assertEqual(invalid_font.status_code, 400)

    def test_anonymous_user_cannot_read_watermark(self):
        SystemSetting.objects.create(key="watermark", value={"enabled": True, "text": "CAPTAIN", "pages": ["ip"]})
        self.client.logout()

        response = self.client.get("/api/system/settings/watermark/")

        self.assertEqual(response.status_code, 401)

    def test_anonymous_user_can_read_public_display_settings(self):
        SystemSetting.objects.create(key="login_content", value={"title": "Hello"})
        self.client.logout()

        response = self.client.get("/api/system/settings/login_content/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["value"]["title"], "Hello")

    def test_ui_theme_is_public_and_only_staff_can_update_it(self):
        SystemSetting.objects.create(key="ui_theme", value={"preset": "teal", "customPrimary": "#0F766E"})
        self.client.logout()

        public_response = self.client.get("/api/system/settings/ui_theme/")

        self.assertEqual(public_response.status_code, 200)
        self.assertEqual(public_response.json()["value"]["preset"], "teal")

        self.client.force_login(self.user)
        forbidden_response = self.client.put(
            "/api/system/settings/ui_theme/",
            data={"value": {"preset": "emerald", "customPrimary": "#059669"}},
            content_type="application/json",
        )

        self.assertEqual(forbidden_response.status_code, 403)

    def test_ui_theme_validation_accepts_presets_and_rejects_invalid_values(self):
        valid_response = self.client.post(
            "/api/system/settings/",
            data={"key": "ui_theme", "value": {"preset": "custom", "customPrimary": "#123ABC"}},
            content_type="application/json",
        )
        invalid_preset = self.client.put(
            "/api/system/settings/ui_theme/",
            data={"value": {"preset": "rainbow", "customPrimary": "#123ABC"}},
            content_type="application/json",
        )
        invalid_color = self.client.put(
            "/api/system/settings/ui_theme/",
            data={"value": {"preset": "custom", "customPrimary": "blue"}},
            content_type="application/json",
        )

        self.assertEqual(valid_response.status_code, 201)
        self.assertEqual(valid_response.json()["value"], {"preset": "custom", "customPrimary": "#123ABC"})
        self.assertEqual(invalid_preset.status_code, 400)
        self.assertEqual(invalid_color.status_code, 400)

    def test_watermark_validation_defaults_empty_text_when_enabled(self):
        response = self.client.post(
            "/api/system/settings/",
            data={"key": "watermark", "value": {"enabled": True, "text": "", "pages": ["ip"]}},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["value"]["text"], "{username}")

    def test_watermark_validation_rejects_unknown_page(self):
        response = self.client.post(
            "/api/system/settings/",
            data={"key": "watermark", "value": {"enabled": False, "text": "", "pages": ["unknown"]}},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)

    def test_log_retention_setting_defaults_missing_fields_and_accepts_zero(self):
        response = self.client.post(
            "/api/system/settings/",
            data={
                "key": "log_retention",
                "label": "日志保留",
                "value": {
                    "loginLogsDays": 0,
                    "rdpRecordingEnabled": True,
                },
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.json()["value"],
            {
                "loginLogsDays": 0,
                "operationLogsDays": 180,
                "terminalCommandAuditDays": 180,
                "terminalFileAuditDays": 180,
                "terminalSessionDays": 180,
                "rdpRecordingEnabled": True,
                "rdpRecordingDays": 30,
            },
        )

    def test_log_retention_setting_rejects_invalid_day_values(self):
        for field, value in {
            "loginLogsDays": -1,
            "operationLogsDays": 3651,
            "terminalCommandAuditDays": 1.5,
            "terminalFileAuditDays": "1.5",
            "terminalSessionDays": True,
        }.items():
            with self.subTest(field=field, value=value):
                response = self.client.post(
                    "/api/system/settings/",
                    data={"key": "log_retention", "value": {field: value}},
                    content_type="application/json",
                )

                self.assertEqual(response.status_code, 400)

    def test_log_retention_setting_requires_boolean_rdp_switch(self):
        response = self.client.post(
            "/api/system/settings/",
            data={"key": "log_retention", "value": {"rdpRecordingEnabled": "true"}},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)

    def test_auth_session_setting_defaults_missing_fields(self):
        response = self.client.post(
            "/api/system/settings/",
            data={"key": "auth_session", "label": "登录会话", "value": {}},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["value"], {"loginExpiryMinutes": 480})

    def test_auth_session_setting_accepts_custom_expiry_minutes(self):
        response = self.client.post(
            "/api/system/settings/",
            data={"key": "auth_session", "label": "登录会话", "value": {"loginExpiryMinutes": 1440}},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["value"]["loginExpiryMinutes"], 1440)

    def test_auth_session_update_expires_existing_logged_in_sessions(self):
        SystemSetting.objects.create(key="auth_session", value={"loginExpiryMinutes": 480})
        store = SessionStore()
        store["_auth_user_id"] = str(self.operator.id)
        store["_auth_user_backend"] = "django.contrib.auth.backends.ModelBackend"
        store.save()

        response = self.client.put(
            "/api/system/settings/auth_session/",
            data={"value": {"loginExpiryMinutes": 1}},
            content_type="application/json",
        )
        session = Session.objects.get(session_key=store.session_key)
        data = session.get_decoded()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["value"]["loginExpiryMinutes"], 1)
        self.assertIn("_auth_user_id", data)
        self.assertLessEqual(data["ops_auth_started_at"] - timezone.now().timestamp(), 1)
        self.assertLessEqual(data["ops_auth_expires_at"] - timezone.now().timestamp(), 61)

    def test_auth_session_setting_rejects_invalid_expiry_minutes(self):
        for value in [0, 43201, "1.5", True]:
            with self.subTest(value=value):
                response = self.client.post(
                    "/api/system/settings/",
                    data={"key": "auth_session", "value": {"loginExpiryMinutes": value}},
                    content_type="application/json",
                )

                self.assertEqual(response.status_code, 400)

    def test_terminal_settings_defaults_missing_fields_and_accepts_zero_disables(self):
        response = self.client.post(
            "/api/system/settings/",
            data={
                "key": "terminal_settings",
                "label": "终端设置",
                "value": {
                    "sshConnectTimeoutSeconds": 10,
                    "sshKeepaliveSeconds": 0,
                    "webSocketHeartbeatSeconds": 0,
                    "idleDisconnectMinutes": 0,
                },
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.json()["value"],
            {
                "sshConnectTimeoutSeconds": 10,
                "sshBannerTimeoutSeconds": 30,
                "sshAuthTimeoutSeconds": 20,
                "sshConnectAttempts": 3,
                "sshRetryDelayMs": 800,
                "sshKeepaliveSeconds": 0,
                "webSocketHeartbeatSeconds": 0,
                "idleDisconnectMinutes": 0,
                "initialReadTimeoutSeconds": 3,
                "initialReadIdleTimeoutMs": 350,
                "commandReadTimeoutSeconds": 30,
                "commandReadIdleTimeoutMs": 350,
                "readerPollIntervalMs": 30,
                "cwdHookSuppressEchoMs": 2000,
                "cwdHookDrainTimeoutMs": 800,
                "cwdHookDrainIdleTimeoutMs": 120,
                "defaultCols": 120,
                "defaultRows": 36,
                "defaultFontSize": 17,
                "scrollbackLines": 5000,
                "bulkExecutionMaxTargets": 500,
            },
        )

    def test_terminal_settings_rejects_invalid_numeric_values(self):
        for field, value in {
            "sshConnectTimeoutSeconds": 0,
            "sshBannerTimeoutSeconds": 301,
            "sshAuthTimeoutSeconds": "1.5",
            "sshConnectAttempts": True,
            "sshRetryDelayMs": -1,
            "defaultFontSize": 40,
            "bulkExecutionMaxTargets": 1001,
        }.items():
            with self.subTest(field=field, value=value):
                response = self.client.post(
                    "/api/system/settings/",
                    data={"key": "terminal_settings", "value": {field: value}},
                    content_type="application/json",
                )

                self.assertEqual(response.status_code, 400)

    def test_logged_in_user_can_read_terminal_settings_but_cannot_write(self):
        SystemSetting.objects.create(key="terminal_settings", value={"sshKeepaliveSeconds": 20})
        self.client.force_login(self.user)

        read_response = self.client.get("/api/system/settings/terminal_settings/")
        write_response = self.client.put(
            "/api/system/settings/terminal_settings/",
            data={"value": {"sshKeepaliveSeconds": 10}},
            content_type="application/json",
        )

        self.assertEqual(read_response.status_code, 200)
        self.assertEqual(write_response.status_code, 403)


class LogRetentionCleanupTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="cleanup-user", password="pass")
        self.group = HostGroup.objects.create(name="cleanup")
        self.host = ManagedHost.objects.create(name="cleanup-host", group=self.group, private_ip="10.0.0.8", os="ubuntu")

    def set_created_at(self, instance, value):
        instance.__class__.objects.filter(id=instance.id).update(created_at=value)
        instance.refresh_from_db()

    def test_cleanup_expired_logs_deletes_each_expired_category(self):
        now = timezone.now()
        SystemSetting.objects.create(
            key="log_retention",
            value={
                "loginLogsDays": 10,
                "operationLogsDays": 20,
                "terminalCommandAuditDays": 30,
                "terminalFileAuditDays": 40,
                "terminalSessionDays": 50,
                "rdpRecordingEnabled": False,
                "rdpRecordingDays": 30,
            },
        )
        old_login = LoginLog.objects.create(username="old", ip_address="10.0.0.1", status=LoginLog.STATUS_SUCCESS)
        fresh_login = LoginLog.objects.create(username="fresh", ip_address="10.0.0.2", status=LoginLog.STATUS_SUCCESS)
        old_operation = OperationLog.objects.create(username="old", module="m", action="a")
        fresh_operation = OperationLog.objects.create(username="fresh", module="m", action="a")
        old_session = TerminalSession.objects.create(host=self.host)
        fresh_session = TerminalSession.objects.create(host=self.host)
        session_with_command = TerminalSession.objects.create(host=self.host)
        session_with_file = TerminalSession.objects.create(host=self.host)
        session_with_recording = TerminalSession.objects.create(host=self.host, protocol=TerminalSession.PROTOCOL_RDP, recording_file="keep.guac")
        old_command = TerminalCommandAudit.objects.create(
            session=session_with_command,
            host=self.host,
            user=self.user,
            username=self.user.username,
            command="whoami",
            executed_at=now - timezone.timedelta(days=31),
        )
        fresh_command = TerminalCommandAudit.objects.create(
            session=fresh_session,
            host=self.host,
            user=self.user,
            username=self.user.username,
            command="uptime",
            executed_at=now - timezone.timedelta(days=2),
        )
        old_file = TerminalFileAudit.objects.create(
            session=session_with_file,
            host=self.host,
            user=self.user,
            username=self.user.username,
            operation=TerminalFileAudit.OPERATION_READ,
            path="/tmp/old",
        )
        fresh_file = TerminalFileAudit.objects.create(
            session=fresh_session,
            host=self.host,
            user=self.user,
            username=self.user.username,
            operation=TerminalFileAudit.OPERATION_READ,
            path="/tmp/fresh",
        )

        self.set_created_at(old_login, now - timezone.timedelta(days=11))
        self.set_created_at(fresh_login, now - timezone.timedelta(days=2))
        self.set_created_at(old_operation, now - timezone.timedelta(days=21))
        self.set_created_at(fresh_operation, now - timezone.timedelta(days=2))
        for session in [old_session, session_with_command, session_with_file, session_with_recording]:
            self.set_created_at(session, now - timezone.timedelta(days=51))
        self.set_created_at(fresh_session, now - timezone.timedelta(days=2))
        self.set_created_at(old_command, now - timezone.timedelta(days=31))
        self.set_created_at(fresh_command, now - timezone.timedelta(days=2))
        self.set_created_at(old_file, now - timezone.timedelta(days=41))
        self.set_created_at(fresh_file, now - timezone.timedelta(days=2))

        result = cleanup_expired_logs(now=now)

        self.assertEqual(result["loginLogs"], 1)
        self.assertEqual(result["operationLogs"], 1)
        self.assertEqual(result["terminalCommandAudits"], 1)
        self.assertEqual(result["terminalFileAudits"], 1)
        self.assertEqual(result["terminalSessions"], 1)
        self.assertFalse(LoginLog.objects.filter(id=old_login.id).exists())
        self.assertTrue(LoginLog.objects.filter(id=fresh_login.id).exists())
        self.assertFalse(OperationLog.objects.filter(id=old_operation.id).exists())
        self.assertTrue(OperationLog.objects.filter(id=fresh_operation.id).exists())
        self.assertFalse(TerminalCommandAudit.objects.filter(id=old_command.id).exists())
        self.assertTrue(TerminalCommandAudit.objects.filter(id=fresh_command.id).exists())
        self.assertFalse(TerminalFileAudit.objects.filter(id=old_file.id).exists())
        self.assertTrue(TerminalFileAudit.objects.filter(id=fresh_file.id).exists())
        self.assertFalse(TerminalSession.objects.filter(id=old_session.id).exists())
        self.assertTrue(TerminalSession.objects.filter(id=session_with_command.id).exists())
        self.assertTrue(TerminalSession.objects.filter(id=session_with_file.id).exists())
        self.assertTrue(TerminalSession.objects.filter(id=session_with_recording.id).exists())

    def test_cleanup_expired_logs_dry_run_and_zero_retention_do_not_delete(self):
        now = timezone.now()
        SystemSetting.objects.create(
            key="log_retention",
            value={
                "loginLogsDays": 0,
                "operationLogsDays": 1,
                "terminalCommandAuditDays": 1,
                "terminalFileAuditDays": 1,
                "terminalSessionDays": 1,
                "rdpRecordingEnabled": False,
                "rdpRecordingDays": 0,
            },
        )
        login = LoginLog.objects.create(username="old", ip_address="10.0.0.1", status=LoginLog.STATUS_SUCCESS)
        operation = OperationLog.objects.create(username="old", module="m", action="a")
        self.set_created_at(login, now - timezone.timedelta(days=365))
        self.set_created_at(operation, now - timezone.timedelta(days=2))

        result = cleanup_expired_logs(now=now, dry_run=True)

        self.assertEqual(result["loginLogs"], 0)
        self.assertEqual(result["operationLogs"], 1)
        self.assertTrue(LoginLog.objects.filter(id=login.id).exists())
        self.assertTrue(OperationLog.objects.filter(id=operation.id).exists())

    def test_cleanup_logs_command_cleans_rdp_recordings(self):
        now = timezone.now()
        SystemSetting.objects.create(
            key="log_retention",
            value={
                "loginLogsDays": 180,
                "operationLogsDays": 180,
                "terminalCommandAuditDays": 180,
                "terminalFileAuditDays": 180,
                "terminalSessionDays": 180,
                "rdpRecordingEnabled": False,
                "rdpRecordingDays": 30,
            },
        )
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            old_file = root / "old.guac"
            old_file.write_text("old", encoding="utf-8")
            session = TerminalSession.objects.create(
                host=self.host,
                protocol=TerminalSession.PROTOCOL_RDP,
                recording_enabled=True,
                recording_file=old_file.name,
            )
            self.set_created_at(session, now - timezone.timedelta(days=40))
            output = StringIO()

            with patch("django.utils.timezone.now", return_value=now), patch("web_terminal.services.rdp.rdp_recording_root", return_value=root):
                call_command("cleanup_logs", stdout=output)

            session.refresh_from_db()
            self.assertFalse(old_file.exists())
            self.assertEqual(session.recording_file, "")
            self.assertIn("rdpRecordings=1", output.getvalue())


class SystemUserLoginFlowTests(TestCase):
    def setUp(self):
        self.operator = get_user_model().objects.create_user(username="operator", password="pass", is_staff=True)
        self.client.force_login(self.operator)

    def complete_slider(self) -> str:
        challenge_response = self.client.get("/api/auth/slider-challenge/")
        self.assertEqual(challenge_response.status_code, 200)
        challenge = challenge_response.json()
        verify_response = self.client.post(
            "/api/auth/slider-verify/",
            data={"challengeId": challenge["challengeId"], "offsetX": challenge["targetX"], "elapsedMs": 400},
            content_type="application/json",
        )
        self.assertEqual(verify_response.status_code, 200)
        return verify_response.json()["sliderToken"]

    def test_created_system_user_can_login_with_initial_password(self):
        response = self.client.post(
            "/api/system/users/",
            data={
                "username": "new-user",
                "firstName": "新用户",
                "email": "new-user@example.com",
                "password": "UserPass123",
                "isActive": True,
                "isStaff": False,
                "roleIds": [],
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.json()["canLogin"])

        user = get_user_model().objects.get(username="new-user")
        self.assertTrue(user.is_active)
        self.assertTrue(user.has_usable_password())
        self.assertTrue(user.check_password("UserPass123"))

        self.client.logout()
        slider_token = self.complete_slider()
        login_response = self.client.post(
            "/api/auth/login/",
            data={"account": "new-user", "password": "UserPass123", "remember": False, "sliderToken": slider_token},
            content_type="application/json",
        )

        self.assertEqual(login_response.status_code, 200)
        self.assertEqual(login_response.json()["user"]["username"], "new-user")

    def test_create_system_user_rejects_weak_password(self):
        response = self.client.post(
            "/api/system/users/",
            data={
                "username": "weak-user",
                "password": "password",
                "isActive": True,
                "isStaff": False,
                "roleIds": [],
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("大写字母", response.json()["error"])
