from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('chat', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='chat',
            name='active_workflow',
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
        migrations.AddField(
            model_name='chat',
            name='collected_data',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name='chat',
            name='context_cache',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name='chat',
            name='current_step',
            field=models.IntegerField(default=0),
        ),
    ]
