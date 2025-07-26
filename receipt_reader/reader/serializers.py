from rest_framework import serializers
from .models import Receipt, MonthlyBudget # <-- Import new model

class ReceiptSerializer(serializers.ModelSerializer):
    class Meta:
        model = Receipt
        # --- ADD 'category' TO FIELDS ---
        fields = ['id', 'uploaded_at', 'image', 'json_data', 'category']


# --- NEW SERIALIZER ---
class MonthlyBudgetSerializer(serializers.ModelSerializer):
    class Meta:
        model = MonthlyBudget
        fields = ['year', 'month', 'limit']