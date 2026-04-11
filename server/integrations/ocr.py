import pdfplumber
import io
import os
import requests
import json
from server.models import Invoice, LineItem
from decimal import Decimal
from typing import Optional

class InvoiceOCR:
    def __init__(self):
        self.hf_token = os.getenv("HF_TOKEN")
        self.llama_url = "https://api-inference.huggingface.co/models/meta-llama/Llama-3.1-70B-Instruct"

    def extract_text_from_pdf(self, file_bytes: bytes) -> str:
        """Extract raw text from PDF using pdfplumber."""
        text = ""
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        return text.strip()

    def llm_structured_extract(self, text: str) -> Invoice:
        """Use Llama-3.1-70B to extract Invoice JSON from raw text."""
        schema = Invoice.model_json_schema()
        prompt = f"""You are an invoice parser. Extract the following text into valid JSON matching this Pydantic schema.

Schema: {json.dumps(schema, indent=2)}

Rules:
1. Return ONLY valid JSON, no markdown, no explanation
2. Use ISO date format YYYY-MM-DD
3. All monetary values as strings for Decimal precision
4. If field missing, use null or empty list

Invoice text:
{text[:8000]}

JSON:"""

        headers = {"Authorization": f"Bearer {self.hf_token}"}
        payload = {
            "inputs": prompt,
            "parameters": {"max_new_tokens": 1500, "temperature": 0.0, "return_full_text": False}
        }

        resp = requests.post(self.llama_url, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()

        # Parse response - HF returns [{"generated_text": "..."}]
        generated = resp.json()[0]["generated_text"].strip()
        # Strip markdown fences if present
        if generated.startswith("```json"):
            generated = generated[7:]
        if generated.endswith("```"):
            generated = generated[:-3]

        return Invoice.model_validate_json(generated)

    def pdf_to_invoice(self, file_bytes: bytes) -> Invoice:
        """Main entry: PDF bytes → Invoice object in 3 seconds."""
        text = self.extract_text_from_pdf(file_bytes)
        if not text:
            raise ValueError("No text extracted from PDF. Try higher quality scan.")
        return self.llm_structured_extract(text)
