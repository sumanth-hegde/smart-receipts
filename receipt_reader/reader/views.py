import google.generativeai as genai
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .serializers import ReceiptSerializer, MonthlyBudgetSerializer  # <-- Import new serializer
import os
from dotenv import load_dotenv
from django.shortcuts import render
import json
from .models import Receipt, MonthlyBudget  # <-- Import new model
from datetime import datetime
from decimal import Decimal
from collections import defaultdict # <-- Import defaultdict


load_dotenv()

# Configure the Gemini API
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
                model = genai.GenerativeModel("gemini-1.5-flash")
                image_file = genai.upload_file(path=image_path)

                # --- UPDATED PROMPT WITH CATEGORIZATION ---
                prompt = """
                Analyze the provided receipt or invoice image. Your task is to meticulously extract the information below and format it into a precise JSON object.
                Based on the merchant's name and the items purchased, determine the most logical spending category.

                **JSON Fields to Extract:**
                - "Merchant Name": The name of the store or service provider.
                - "Transaction Date": The date of the transaction in YYYY-MM-DD format.
                - "Transaction Time": The time of the transaction.
                - "Items": A JSON array of objects. Each object must contain an "Item" (the name or description) and its corresponding "Price".
                - "Subtotal": The total cost *before* taxes are applied.
                - "Tax": The total tax amount. If multiple taxes are present, sum them together.
                - "Total Amount": The final, grand total paid.
                - "Category": Classify the expense into one of the following categories: "Food & Dining", "Transportation", "Groceries", "Shopping", "Utilities", "Health", "Entertainment", or "Other".

                **Important Rules:**
                1.  If a field's value is not present on the receipt, its value in the JSON must be `null`.
                2.  If no individual items can be identified, "Items" should be an empty array `[]`.
                3.  Your entire response must be **only the raw JSON object**. Do not wrap it in markdown fences like ```json or add any other explanatory text.
                """


                response = model.generate_content([prompt, image_file])

                cleaned_response_text = response.text.strip().replace("```json", "").replace("```", "")
                json_response = json.loads(cleaned_response_text)

                # --- SAVE EXTRACTED DATA AND THE NEW CATEGORY ---
                receipt_instance.json_data = json_response
                receipt_instance.category = json_response.get('Category', 'Other') # Default to 'Other'
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


class ChatbotView(APIView):
    def post(self, request, *args, **kwargs):
        query = request.data.get('query')
        history = request.data.get('history', [])

        if not query:
            return Response({'error': 'A query is required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            receipts = Receipt.objects.all().order_by('-uploaded_at')
            serializer = ReceiptSerializer(receipts, many=True)
            receipts_data = "[]"
            if receipts.exists():
                receipts_data = json.dumps(serializer.data)

            model = genai.GenerativeModel("gemini-1.5-flash")

            formatted_history = ""
            for message in history:
                role = "User" if message.get('sender') == 'user' else "You"
                formatted_history += f"{role}: {message.get('text')}\n"

            # --- START: PROMPT UPDATED FOR CONCISENESS ---
            prompt = f"""
            You are a friendly and helpful AI assistant specializing in personal finance. You are having a conversation with a user. Make it short, give the main points only.

            **Your Role & Rules:**
            1.  **Maintain Context:** Use the "Previous Conversation" to understand follow-up questions.
            2.  **Prioritize User Data:** First, always try to answer the user's question using their personal "Receipt Data".
            3.  **Provide General Advice:** If the question is for general advice and cannot be answered from the receipt data, use your own knowledge to provide helpful, actionable tips.
            4.  **Be Concise and Clear:** Keep your answers brief. When giving a list of suggestions, use bullet points (`*`) for easy reading. Avoid long introductory or concluding paragraphs.
            5.  **Be Conversational:** Keep your tone friendly and helpful.
            6.  **Currency:** All financial figures must be in Rupees (₹).

            **Receipt Data (JSON):**
            {receipts_data}

            **Previous Conversation:**
            {formatted_history}

            **User's New Message:**
            "{query}"
            """
            # --- END: PROMPT UPDATED FOR CONCISENESS ---

            response = model.generate_content(prompt)
            return Response({'response': response.text})

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


# --- NEW VIEW FOR MANAGING BUDGET ---
class BudgetView(APIView):
    def get(self, request, *args, **kwargs):
        year = request.query_params.get('year', datetime.now().year)
        month = request.query_params.get('month', datetime.now().month)
        budget, _ = MonthlyBudget.objects.get_or_create(
            year=year, month=month,
            defaults={'limit': Decimal('0.00')}  # Default to 0 if not set
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


# --- UPDATED VIEW FOR THE EXPENSE TRACKER PAGE ---
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
        # --- NEW: Use defaultdict to sum spending by category ---
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
                        # --- NEW: Aggregate spending into categories ---
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

        # --- UPDATED RESPONSE ---
        response_data = {
            'budget': MonthlyBudgetSerializer(budget).data,
            'total_spent': total_spent,
            'transactions': ReceiptSerializer(monthly_receipts, many=True).data,
            'suggestion': suggestion,
            # --- NEW: Add category summary to the response ---
            'category_summary': category_summary
        }


        return Response(response_data)