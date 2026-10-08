from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("host_management", "0012_hostcredential_credential_type"),
    ]

    operations = [
        migrations.AlterField(
            model_name="hostcredential",
            name="username",
            field=models.CharField(blank=True, max_length=120),
        ),
    ]
