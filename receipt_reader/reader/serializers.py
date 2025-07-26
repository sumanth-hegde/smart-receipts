from rest_framework import serializers
from reader.models import Receipt

class ReceiptSerializer(serializers.ModelSerializer):
    class Meta:
        model = Receipt
        fields = ['id', 'uploaded_at', 'image', 'json_data']