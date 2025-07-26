from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal

class Receipt(models.Model):
    uploaded_at = models.DateTimeField(auto_now_add=True)
    image = models.ImageField(upload_to='receipts/')
    json_data = models.JSONField(null=True, blank=True)
    # --- NEW FIELD ---
    category = models.CharField(max_length=50, null=True, blank=True, default='Other')


    def __str__(self):
        return f"Receipt {self.id} - {self.uploaded_at}"

# --- NEW MODEL ---
class MonthlyBudget(models.Model):
    """Stores the user's spending limit for a specific month and year."""
    year = models.IntegerField()
    month = models.IntegerField()
    limit = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )

    class Meta:
        # Ensures that there's only one budget entry per month/year combination
        unique_together = ('year', 'month')

    def __str__(self):
        return f"Budget for {self.year}-{self.month}: {self.limit}"