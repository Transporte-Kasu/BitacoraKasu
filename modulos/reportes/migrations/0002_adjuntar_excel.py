from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('reportes', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='configuracionreporte',
            name='adjuntar_excel',
            field=models.BooleanField(
                default=False,
                help_text='Adjunta un archivo Excel con el detalle completo del período al correo',
                verbose_name='Adjuntar Excel',
            ),
        ),
    ]
