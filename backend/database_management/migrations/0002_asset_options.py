from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("database_management", "0001_initial")]
    operations = [
        migrations.AlterField(
            model_name="databaseasset", name="db_type",
            field=models.CharField(max_length=20, default="mysql", choices=[
                ("mysql", "MySQL"), ("mariadb", "MariaDB"),
                ("postgresql", "PostgreSQL"), ("kingbase", "Kingbase"),
                ("sqlserver", "SQL Server"), ("sqlite", "SQLite"),
                ("redis", "Redis"), ("clickhouse", "ClickHouse"),
                ("oracle", "Oracle"), ("dameng", "Dameng"),
            ]),
        ),
        migrations.AddField(
            model_name="databaseasset", name="options",
            field=models.JSONField(default=dict, blank=True),
        ),
    ]
