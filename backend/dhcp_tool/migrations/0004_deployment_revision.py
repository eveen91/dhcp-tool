from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("dhcp_tool", "0003_immutable_history")]

    operations = [
        migrations.AddField(
            model_name="deployment",
            name="revision",
            field=models.PositiveBigIntegerField(default=1),
        ),
    ]
