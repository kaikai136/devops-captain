from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("database_management", "0005_databasetransfertask")]
    operations = [migrations.AddField(
        model_name="databaseasset", name="connection_secrets_encrypted",
        field=models.TextField(blank=True),
    )]
