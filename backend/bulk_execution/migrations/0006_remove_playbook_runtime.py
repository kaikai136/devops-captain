from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bulk_execution", "0005_playbook_log_output"),
    ]

    operations = [
        migrations.AlterField(
            model_name="bulkexecutiontask",
            name="execution_type",
            field=models.CharField(
                choices=[("shell", "Shell"), ("file_upload", "File upload")],
                default="shell",
                max_length=20,
            ),
        ),
        migrations.RemoveField(
            model_name="bulkexecutiontask",
            name="log_output",
        ),
        migrations.RemoveField(
            model_name="bulkexecutiontask",
            name="log_output_truncated",
        ),
    ]
