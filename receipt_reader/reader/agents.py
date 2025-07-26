import google.generativeai as genai
import json
import os
from dotenv import load_dotenv

# It's good practice to configure dependencies within the module that uses them.
load_dotenv()
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

class ReceiptScanningAgent:
    """
    An AI agent responsible for analyzing receipt images and extracting structured data.
    """
    def __init__(self):
        """
        Initializes the agent by setting up the generative model and defining the core prompt.
        """
        self.model = genai.GenerativeModel("gemini-2.5-flash")
        self.prompt = """
            Analyze the provided receipt or invoice image. Your task is to meticulously extract the information below and format it into a precise JSON object.
            Based on the merchant's name and the items purchased, determine the most logical spending category.

            **JSON Fields to Extract:**
            - "Merchant Name": The name of the store or service provider.
            - "Transaction Date": The date of the transaction in YYYY-MM-DD format.
            - "Transaction Time": The time of the transaction.
            - "Items": A JSON array of objects. Each object must contain an "Item" (the name or description) and its corresponding "Price".
            - "Subtotal": The total cost *before* taxes are applied.
            - "Tax": The total tax amount. If multiple taxes are present (like VAT, GST, etc.), sum them together.
            - "Total Amount": The final, grand total paid.
            - "Category": Classify the expense into one of the following categories: "Food & Dining", "Transportation", "Groceries", "Shopping", "Utilities", "Health", "Entertainment", or "Other".

            **Important Rules:**
            1.  If a field's value is not present on the receipt, its value in the JSON must be `null`.
            2.  If no individual items can be identified, "Items" should be an empty array `[]`.
            3.  Your entire response must be **only the raw JSON object**. Do not wrap it in markdown fences like ```json or add any other explanatory text.
            """

    def process_receipt(self, image_path: str) -> dict:
        """
        Processes a single receipt image and returns the extracted data as a dictionary.
        """
        try:
            image_file = genai.upload_file(path=image_path)
            response = self.model.generate_content([self.prompt, image_file])

            cleaned_response_text = response.text.strip().replace("```json", "").replace("```", "")
            json_data = json.loads(cleaned_response_text)
            return json_data

        except Exception as e:
            raise ValueError(f"Agent failed to process receipt image: {str(e)}")


# --- NEW, ADVANCED CHATBOT AGENT ---
class ChatbotAgent:
    """
    An AI agent that acts as a personal financial advisor.
    It's designed for safe, accurate, and context-aware conversations.
    """
    def __init__(self):
        self.model = genai.GenerativeModel("gemini-2.5-flash")
        self.system_prompt = """
        You are 'SmartReceipts Advisor,' an expert AI personal financial assistant. Your mission is to provide safe, accurate, and helpful financial insights based primarily on the user's provided data. Keep it short, clear and crisp. Here you need to act as a financial advisor, answering questions about the user's spending, budgeting, and financial strategies.
        Always give short answers do not elaborate a lot. Use bullet points for lists to make them easy to digest. Content should be short but it should be clear and give great insights to the user.

        **YOUR CORE DIRECTIVES - YOU MUST FOLLOW THESE RULES:**

        1.  **DATA IS SUPREME:** Your primary source of truth is the user's `[USER'S RECEIPT DATA]`. If a question is about their spending (e.g., "how much did I spend on...?"), your answer **MUST** be derived from this data. **NEVER** invent or hallucinate transactions, amounts, or dates. If the data isn't there, say so.

        2.  **MAINTAIN CONTEXT:** Use the `[CONVERSATION HISTORY]` to understand follow-up questions. The user expects you to remember what you just talked about.

        3.  **SAFETY DISCLAIMER (MANDATORY):** When providing any general financial advice, strategies, or suggestions (e.g., ways to save, investment ideas), you **MUST** include the following disclaimer at the end of your response:
            `Please remember, I am an AI assistant and not a licensed financial advisor. You should consult with a professional for personalized financial decisions.`

        4.  **THINK STEP-BY-STEP:** Before answering, follow this internal thought process:
            -   Step 1: Analyze the `[USER'S NEW QUESTION]`. What is the core intent?
            -   Step 2: Check if the intent can be satisfied *directly* from the `[USER'S RECEIPT DATA]`. If yes, formulate an answer based only on that data.
            -   Step 3: If not, check the `[CONVERSATION HISTORY]` for context. Is this a follow-up?
            -   Step 4: If it's a general advice question, formulate a helpful, generic answer.
            -   Step 5: Apply the mandatory safety disclaimer if you provided general advice in Step 4.

        5.  **PERSONA & TONE:**
            -   Be professional, empathetic, and clear.
            -   Keep answers concise and use bullet points (`*`) for lists to make them easy to digest.
            -   All financial figures must be in Rupees (₹).
        """

    def get_response(self, query: str, history: list, receipt_data: str) -> str:
        """
        Generates a contextual and safe response from the financial advisor agent.

        Args:
            query: The user's latest message.
            history: A list of previous messages in the conversation.
            receipt_data: A JSON string of the user's receipt data.

        Returns:
            A string containing the AI's response.
        """
        formatted_history = ""
        for message in history:
            role = "User" if message.get('sender') == 'user' else "Advisor"
            formatted_history += f"{role}: {message.get('text')}\n"

        # Combine the system prompt with the dynamic data
        full_prompt = (
            f"{self.system_prompt}\n\n"
            f"--- CONTEXT FOR CURRENT QUERY ---\n"
            f"[USER'S RECEIPT DATA]:\n{receipt_data}\n\n"
            f"[CONVERSATION HISTORY]:\n{formatted_history}\n"
            f"[USER'S NEW QUESTION]:\n{query}\n"
            f"Advisor Response:"
        )

        try:
            response = self.model.generate_content(full_prompt)
            return response.text
        except Exception as e:
            # Provide a safe, generic error message to the user
            return "I apologize, but I encountered a problem trying to process your request. Please try again."