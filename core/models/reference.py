"""
Kenyan Reference Data Models
Includes 47 Counties of Kenya, Commercial Banks, and Central Bank clearing codes.
"""
from django.db import models


class KenyaCounty(models.Model):
    """
    47 Counties of Kenya under the Constitution of Kenya 2010.
    """
    code = models.CharField(max_length=3, unique=True, help_text="County Code (001-047)")
    name = models.CharField(max_length=100, unique=True, db_index=True)
    capital = models.CharField(max_length=100, blank=True)
    region = models.CharField(
        max_length=50,
        blank=True,
        choices=[
            ('coast', 'Coast'),
            ('north_eastern', 'North Eastern'),
            ('eastern', 'Eastern'),
            ('central', 'Central'),
            ('rift_valley', 'Rift Valley'),
            ('western', 'Western'),
            ('nyanza', 'Nyanza'),
            ('nairobi', 'Nairobi'),
        ]
    )

    class Meta:
        verbose_name = 'Kenya County'
        verbose_name_plural = 'Kenya Counties'
        ordering = ['code']

    def __str__(self):
        return f"{self.code} - {self.name}"


class KenyaBank(models.Model):
    """
    Registry of Kenyan Commercial Banks and Microfinance Institutions.
    Includes Central Bank of Kenya (CBK) clearing codes and SWIFT/BIC codes.
    """
    bank_code = models.CharField(max_length=20, unique=True, help_text="CBK Clearing Code (e.g. 01, 11, 68)")
    name = models.CharField(max_length=150, db_index=True)
    swift_code = models.CharField(max_length=20, blank=True, help_text="SWIFT / BIC Code")
    paybill_number = models.CharField(max_length=20, blank=True, help_text="M-Pesa Paybill number for bank deposit")
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        verbose_name = 'Kenyan Bank'
        verbose_name_plural = 'Kenyan Banks'
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.bank_code})"
