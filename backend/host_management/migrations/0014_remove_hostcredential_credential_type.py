from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("host_management", "0013_hostcredential_username_optional")]
    operations = [migrations.RemoveField(model_name="hostcredential", name="credential_type")]
