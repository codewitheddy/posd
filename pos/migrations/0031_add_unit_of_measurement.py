# Generated migration for Unit of Measurement

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0030_add_barcode_field'),
    ]

    operations = [
        migrations.CreateModel(
            name='UnitOfMeasurement',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(help_text='Unit name (e.g., Kilogram, Liter)', max_length=50)),
                ('abbreviation', models.CharField(help_text='Short form (e.g., kg, L, m)', max_length=10)),
                ('unit_type', models.CharField(choices=[('weight', 'Weight'), ('volume', 'Volume'), ('length', 'Length'), ('area', 'Area'), ('count', 'Count/Pieces'), ('other', 'Other')], default='count', max_length=20)),
                ('conversion_factor', models.DecimalField(decimal_places=4, default=1, help_text='Factor to convert to base unit (e.g., 0.001 for g to kg)', max_digits=10)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('base_unit', models.ForeignKey(blank=True, help_text='Base unit for conversion (e.g., kg for g)', null=True, on_delete=django.db.models.deletion.SET_NULL, to='pos.unitofmeasurement')),
                ('business', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='units', to='pos.business')),
            ],
            options={
                'verbose_name_plural': 'Units of Measurement',
                'ordering': ['unit_type', 'name'],
                'unique_together': {('business', 'abbreviation')},
            },
        ),
        migrations.AddField(
            model_name='product',
            name='unit',
            field=models.ForeignKey(blank=True, help_text='Unit of measurement (e.g., kg, L, pcs)', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='products', to='pos.unitofmeasurement'),
        ),
        migrations.AlterField(
            model_name='product',
            name='stock_quantity',
            field=models.DecimalField(decimal_places=3, default=0, help_text='Current stock quantity', max_digits=10),
        ),
        migrations.AlterField(
            model_name='product',
            name='low_stock_threshold',
            field=models.DecimalField(decimal_places=3, default=10, help_text='Alert when stock falls below this level', max_digits=10),
        ),
    ]
