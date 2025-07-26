import google.generativeai as genai
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .serializers import ReceiptSerializer, MonthlyBudgetSerializer
import os
from dotenv import load_dotenv
from django.shortcuts import render
import json
from .models import Receipt, MonthlyBudget
from datetime import datetime
from decimal import Decimal
from collections import defaultdict
# --- IMPORT BOTH AGENTS ---
from .agents import ReceiptScanningAgent, ChatbotAgent

load_dotenv()

genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))


def home_view(request):
    """
    This view is responsible for rendering the main index.html page.
    """
    return render(request, 'index.html')


class ReceiptProcessView(APIView):
    def post(self, request, *args, **kwargs):
        serializer = ReceiptSerializer(data=request.data)
        if serializer.is_valid():
            receipt_instance = serializer.save()
            image_path = receipt_instance.image.path

            try:
                agent = ReceiptScanningAgent()
                json_response = agent.process_receipt(image_path)
                receipt_instance.json_data = json_response
                receipt_instance.category = json_response.get('Category', 'Other')
                receipt_instance.save()
                return Response(ReceiptSerializer(receipt_instance).data, status=status.HTTP_201_CREATED)
            except Exception as e:
                return Response({'error': f"An error occurred during processing: {str(e)}"},
                                status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ReceiptListView(APIView):
    def get(self, request, *args, **kwargs):
        receipts = Receipt.objects.all().order_by('-uploaded_at')
        serializer = ReceiptSerializer(receipts, many=True)
        return Response(serializer.data)


# --- UPDATED CHATBOT VIEW USING THE NEW AGENT ---
class ChatbotView(APIView):
    def post(self, request, *args, **kwargs):
        query = request.data.get('query')
        history = request.data.get('history', [])

        if not query:
            return Response({'error': 'A query is required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # 1. Gather all necessary data
            receipts = Receipt.objects.all().order_by('-uploaded_at')
            receipts_data = "[]"
            if receipts.exists():
                serializer = ReceiptSerializer(receipts, many=True)
                receipts_data = json.dumps(serializer.data)

            # 2. Instantiate the new, specialized agent
            agent = ChatbotAgent()

            # 3. Delegate the entire conversation logic to the agent
            response_text = agent.get_response(query, history, receipts_data)

            # 4. Return the agent's response
            return Response({'response': response_text})

        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ExpenseReportView(APIView):
    def get(self, request, *args, **kwargs):
        all_receipts = Receipt.objects.all()
        start_date_str = request.query_params.get('start_date')
        end_date_str = request.query_params.get('end_date')

        filtered_receipts = []

        if start_date_str and end_date_str:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            except ValueError:
                return Response({"error": "Invalid date format. Please use YYYY-MM-DD."},
                                status=status.HTTP_400_BAD_REQUEST)

            for receipt in all_receipts:
                if receipt.json_data and 'Transaction Date' in receipt.json_data:
                    date_str = receipt.json_data['Transaction Date']
                    try:
                        receipt_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                        if start_date <= receipt_date <= end_date:
                            filtered_receipts.append(receipt)
                    except (ValueError, TypeError):
                        continue
        else:
            filtered_receipts = all_receipts

        if not filtered_receipts:
            return Response({"error": "No receipts found for the selected criteria."}, status=status.HTTP_404_NOT_FOUND)

        most_expensive_item = None
        least_expensive_item = None
        max_price = -1
        min_price = float('inf')

        for receipt in filtered_receipts:
            data = receipt.json_data
            if data and 'Items' in data and isinstance(data['Items'], list):
                for item in data['Items']:
                    try:
                        if isinstance(item, dict) and 'Price' in item and item['Price'] is not None:
                            price = float(item['Price'])
                            if price > max_price:
                                max_price = price
                                most_expensive_item = {
                                    'Item': item.get('Item', 'N/A'),
                                    'Price': price,
                                    'Merchant': data.get('Merchant Name', 'N/A'),
                                    'Date': data.get('Transaction Date', 'N/A')
                                }
                            if price < min_price:
                                min_price = price
                                least_expensive_item = {
                                    'Item': item.get('Item', 'N/A'),
                                    'Price': price,
                                    'Merchant': data.get('Merchant Name', 'N/A'),
                                    'Date': data.get('Transaction Date', 'N/A')
                                }
                    except (ValueError, TypeError):
                        continue

        if not most_expensive_item and not least_expensive_item:
            return Response({"error": "Could not find any valid items in the selected receipts."},
                            status=status.HTTP_404_NOT_FOUND)

        report = {
            'most_expensive': most_expensive_item,
            'least_expensive': least_expensive_item
        }
        return Response(report, status=status.HTTP_200_OK)


class BudgetView(APIView):
    def get(self, request, *args, **kwargs):
        year = request.query_params.get('year', datetime.now().year)
        month = request.query_params.get('month', datetime.now().month)
        budget, _ = MonthlyBudget.objects.get_or_create(
            year=year, month=month,
            defaults={'limit': Decimal('0.00')}
        )
        serializer = MonthlyBudgetSerializer(budget)
        return Response(serializer.data)

    def post(self, request, *args, **kwargs):
        year = request.data.get('year', datetime.now().year)
        month = request.data.get('month', datetime.now().month)
        limit = request.data.get('limit')

        if not limit:
            return Response({'error': 'Limit is required.'}, status=status.HTTP_400_BAD_REQUEST)

        budget, created = MonthlyBudget.objects.update_or_create(
            year=year, month=month,
            defaults={'limit': Decimal(limit)}
        )
        serializer = MonthlyBudgetSerializer(budget)
        return Response(serializer.data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class ExpenseTrackerView(APIView):
    def get(self, request, *args, **kwargs):
        today = datetime.now()
        year = int(request.query_params.get('year', today.year))
        month = int(request.query_params.get('month', today.month))

        budget, _ = MonthlyBudget.objects.get_or_create(
            year=year, month=month,
            defaults={'limit': Decimal('10000.00')}
        )

        monthly_receipts = []
        total_spent = Decimal('0.00')
        category_summary = defaultdict(Decimal)
        most_expensive_item = {'Price': -1}


        all_receipts = Receipt.objects.filter(uploaded_at__year=year, uploaded_at__month=month).order_by('-uploaded_at')

        for receipt in all_receipts:
            if receipt.json_data and 'Transaction Date' in receipt.json_data:
                try:
                    receipt_date = datetime.strptime(receipt.json_data['Transaction Date'], '%Y-%m-%d').date()
                    if receipt_date.year == year and receipt_date.month == month:
                        monthly_receipts.append(receipt)
                        total = Decimal(str(receipt.json_data.get('Total Amount', 0)))
                        total_spent += total
                        category_summary[receipt.category or 'Other'] += total


                        if 'Items' in receipt.json_data and isinstance(receipt.json_data['Items'], list):
                            for item in receipt.json_data['Items']:
                                if isinstance(item, dict) and 'Price' in item and item['Price'] is not None:
                                    price = float(item['Price'])
                                    if price > most_expensive_item['Price']:
                                        most_expensive_item = {
                                            'Item': item.get('Item', 'N/A'),
                                            'Price': price
                                        }
                except (ValueError, TypeError):
                    continue

        suggestion = None
        if total_spent > budget.limit and most_expensive_item['Price'] > 0:
            try:
                search_query = f"price for {most_expensive_item['Item']} in India"
                model = genai.GenerativeModel("gemini-1.5-flash")
                prompt = f"""
                A user has overspent their budget. Their most expensive purchase was "{most_expensive_item['Item']}".
                Perform a quick web search to find a better price or deal for this item.
                Summarize your findings in a short, helpful suggestion. For example: "You could save money on this. I found it for a lower price at [Store/Website]."
                Provide a single, concise paragraph.
                """
                response = model.generate_content(prompt)
                suggestion = response.text.strip()
            except Exception as e:
                suggestion = f"Could not fetch suggestions at this time. Error: {str(e)}"

        response_data = {
            'budget': MonthlyBudgetSerializer(budget).data,
            'total_spent': total_spent,
            'transactions': ReceiptSerializer(monthly_receipts, many=True).data,
            'suggestion': suggestion,
            'category_summary': category_summary
        }


        return Response(response_data)