from django.db import models

class Receipt(models.Model):
    uploaded_at = models.DateTimeField(auto_now_add=True)
    image = models.ImageField(upload_to='receipts/')
    json_data = models.JSONField(null=True, blank=True)

    def __str__(self):
        return f"Receipt {self.id} - {self.uploaded_at}"