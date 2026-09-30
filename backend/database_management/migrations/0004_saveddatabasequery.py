from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("database_management", "0003_asset_directory"),
    ]

    operations = [
        migrations.CreateModel(
            name="SavedDatabaseQuery",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("database", models.CharField(blank=True, max_length=160)),
                ("schema", models.CharField(blank=True, max_length=160)),
                ("name", models.CharField(max_length=160)),
                ("sql", models.TextField(blank=True)),
                ("pinned", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("asset", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="saved_queries", to="database_management.databaseasset")),
                ("owner", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="saved_database_queries", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-pinned", "name", "id"]},
        ),
        migrations.AddConstraint(
            model_name="saveddatabasequery",
            constraint=models.UniqueConstraint(fields=("owner", "asset", "database", "schema", "name"), name="unique_saved_database_query"),
        ),
    ]
