from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('reportes', '0003_alter_configuracionreporte_modulo_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='reportegenerado',
            name='narrativa_ia',
            field=models.TextField(
                blank=True,
                verbose_name='Narrativa IA',
                help_text='Párrafo ejecutivo generado automáticamente por IAKasu (Claude Haiku)',
            ),
        ),
    ]
