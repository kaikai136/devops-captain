from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("database_management", "0002_asset_options")]
    operations = [
        migrations.CreateModel(
            name="AssetDirectory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=160)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("parent", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="children", to="database_management.assetdirectory")),
            ],
            options={"ordering": ["name", "id"]},
        ),
        migrations.AddField(
            model_name="databaseasset", name="directory",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="assets", to="database_management.assetdirectory"),
        ),
    ]
