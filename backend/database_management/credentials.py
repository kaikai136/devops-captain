"""Resolve current credentials at each physical connection, never from a cached FK."""
from .models import ApplicationKey


def resolve_credentials(asset):
    from .services import decrypt_password

    mode = (getattr(asset, "options", None) or {}).get("authMethod", "password")
    if mode == "applicationKey":
        if not asset.application_key_id:
            raise ValueError("请编辑连接，重新选择应用密钥")
        try:
            key = ApplicationKey.objects.get(pk=asset.application_key_id)
        except ApplicationKey.DoesNotExist:
            raise ValueError("应用密钥不存在，请重新选择") from None
        if asset.db_type != "redis" and not key.username.strip():
            raise ValueError("所选应用密钥缺少用户名")
        return key.username, decrypt_password(key.password_encrypted)
    return asset.username, "" if mode == "none" else decrypt_password(getattr(asset, "password_encrypted", ""))
