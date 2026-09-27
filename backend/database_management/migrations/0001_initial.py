from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings

class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [migrations.CreateModel(name="DatabaseAsset", options={"ordering": ["-updated_at", "id"]}, fields=[
        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
        ("name", models.CharField(max_length=160)), ("db_type", models.CharField(choices=[("mysql", "MySQL")], default="mysql", max_length=20)),
        ("host", models.CharField(max_length=255)), ("port", models.PositiveIntegerField(default=3306)), ("username", models.CharField(max_length=120)),
        ("password_encrypted", models.TextField(blank=True)), ("database", models.CharField(blank=True, max_length=120)), ("remark", models.TextField(blank=True)),
        ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
        ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="database_assets", to=settings.AUTH_USER_MODEL)),
    ])]
