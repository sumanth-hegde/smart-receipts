import google.generativeai as genai
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .serializers import ReceiptSerializer
import os
from dotenv import load_dotenv
from django.shortcuts import render
import json
from .models import Receipt

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

                # --- NEW, MORE ROBUST PROMPT ---
                prompt = """
                Analyze the provided receipt or invoice image. Your task is to meticulously extract the information below and format it into a precise JSON object.
                The receipt can be from any type of merchant (e.g., supermarket, pharmacy, gas station, restaurant).

                **JSON Fields to Extract:**
                - "Merchant Name": The name of the store or service provider.
                - "Transaction Date": The date of the transaction.
                - "Transaction Time": The time of the transaction.
                - "Items": A JSON array of objects. Each object must contain an "Item" (the name or description) and its corresponding "Price".
                - "Subtotal": The total cost *before* taxes are applied.
                - "Tax": The total tax amount. If multiple taxes are present (like VAT, GST, etc.), sum them together.
                - "Total Amount": The final, grand total paid.

                **Important Rules:**
                1.  If a field's value is not present on the receipt, its value in the JSON must be `null`.
                2.  If no individual items can be identified, "Items" should be an empty array `[]`.
                3.  Your entire response must be **only the raw JSON object**. Do not wrap it in markdown fences like ```json or add any other explanatory text.
                """

                response = model.generate_content([prompt, image_file])

                # Clean the response to ensure it is valid JSON
                cleaned_response_text = response.text.strip().replace("```json", "").replace("```", "")

                json_response = json.loads(cleaned_response_text)

                receipt_instance.json_data = json_response
                receipt_instance.save()

                return Response(ReceiptSerializer(receipt_instance).data, status=status.HTTP_201_CREATED)

            except Exception as e:
                # Handle potential errors from the API or JSON parsing
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
        if not query:
            return Response({'error': 'A query is required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            receipts = Receipt.objects.all().order_by('-uploaded_at')
            if not receipts.exists():
                return Response(
                    {'response': "I don't have any receipt data to search through yet. Please scan a receipt first!"})

            serializer = ReceiptSerializer(receipts, many=True)
            receipts_data = json.dumps(serializer.data)

            model = genai.GenerativeModel("gemini-1.5-flash")

            prompt = f"""
            You are a friendly and helpful AI assistant for managing personal finances based on receipt data.
            Based *only* on the provided JSON data of receipts, answer the user's question.
            Do not make up information. If the answer cannot be found in the provided data, say so politely.

            Here is the available receipt data:
            {receipts_data}

            Here is the user's question:
            "{query}"

            Provide a concise and conversational answer and make sure while giving the answer just change the currency from dollars to rupees.
            """

            response = model.generate_content(prompt)
            return Response({'response': response.text})

        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# --- NEW VIEW FOR EXPENSE REPORT ---
class ExpenseReportView(APIView):
    def get(self, request, *args, **kwargs):
        receipts = Receipt.objects.all()
        if not receipts.exists():
            return Response({"error": "No receipts available to generate a report."}, status=status.HTTP_404_NOT_FOUND)

        most_expensive_item = None
        least_expensive_item = None
        max_price = -1
        min_price = float('inf')

        for receipt in receipts:
            data = receipt.json_data
            # Ensure data and Items list exist and are not empty
            if data and 'Items' in data and isinstance(data['Items'], list):
                for item in data['Items']:
                    try:
                        # Ensure item is a dict and has Price
                        if isinstance(item, dict) and 'Price' in item and item['Price'] is not None:
                            price = float(item['Price'])

                            # Check for most expensive
                            if price > max_price:
                                max_price = price
                                most_expensive_item = {
                                    'Item': item.get('Item', 'N/A'),
                                    'Price': price,
                                    'Merchant': data.get('Merchant Name', 'N/A'),
                                    'Date': data.get('Transaction Date', 'N/A')
                                }

                            # Check for least expensive
                            if price < min_price:
                                min_price = price
                                least_expensive_item = {
                                    'Item': item.get('Item', 'N/A'),
                                    'Price': price,
                                    'Merchant': data.get('Merchant Name', 'N/A'),
                                    'Date': data.get('Transaction Date', 'N/A')
                                }
                    except (ValueError, TypeError):
                        # Ignore items where price is not a valid number
                        continue

        if not most_expensive_item and not least_expensive_item:
            return Response({"error": "Could not find any valid items to generate a report."},
                            status=status.HTTP_404_NOT_FOUND)

        report = {
            'most_expensive': most_expensive_item,
            'least_expensive': least_expensive_item
        }
        return Response(report, status=status.HTTP_200_OK)