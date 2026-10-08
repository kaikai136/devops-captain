from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("host_management", "0011_managedhost_disk"),
    ]

    operations = [
        migrations.AddField(
            model_name="hostcredential",
            name="credential_type",
            field=models.CharField(
                choices=[("host", "主机密钥"), ("application", "应用密钥")],
                default="host",
                max_length=20,
            ),
        ),
    ]
