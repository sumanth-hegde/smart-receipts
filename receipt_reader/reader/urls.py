from django.urls import path
from .views import ReceiptProcessView, ReceiptListView, ChatbotView

urlpatterns = [
    path('process/', ReceiptProcessView.as_view(), name='receipt-process'),
    path('receipts/', ReceiptListView.as_view(), name='receipt-list'),
    path('chatbot/', ChatbotView.as_view(), name='chatbot'),
]