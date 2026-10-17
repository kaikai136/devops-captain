from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("web_terminal", "0005_ssh_gateway_audit")]

    operations = [
        migrations.AlterField(
            model_name="terminalfileaudit",
            name="operation",
            field=models.CharField(
                max_length=20,
                choices=[
                    ("list", "List"), ("read", "Read"), ("write", "Write"),
                    ("mkdir", "Mkdir"), ("remove", "Remove"), ("rename", "Rename"),
                    ("copy", "Copy"), ("move", "Move"), ("stat", "Stat"),
                ],
            ),
        ),
    ]
