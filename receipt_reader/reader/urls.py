from django.urls import path
from .views import (
    ReceiptProcessView,
    ChatbotView,
    ExpenseReportView,
    BudgetView,
    ExpenseTrackerView
)

urlpatterns = [
    path('process/', ReceiptProcessView.as_view(), name='receipt-process'),
    path('chatbot/', ChatbotView.as_view(), name='chatbot'),
    path('expense-report/', ExpenseReportView.as_view(), name='expense-report'),
    path('budget/', BudgetView.as_view(), name='budget-manager'),
    path('tracker/', ExpenseTrackerView.as_view(), name='expense-tracker'),
]