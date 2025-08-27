import json
import os
import requests
from dotenv import load_dotenv

load_dotenv()
API_URL = "https://api-inference.huggingface.co/models/facebook/bart-large-mnli"
HF_TOKEN = os.getenv("HF_API_KEY")

header = {
    "Authorization": f"Bearer {HF_TOKEN}"
}

def classify_email(subject, body):
    input_text = f"Subject: {subject}\n\nBody: {body}"
    labels = ["Billing", "Technical Support", "Sales", "Spam", "General Inquiry", "Introduction", "Order Status"]

    payload = {
        "inputs": input_text, 
        "parameters": {
            "candidate_labels": labels
        }
    }

    response = requests.post(API_URL, headers=header, json=payload)

    if response.status_code != 200:
        print("Error:", response.status_code, response.text)
        return None
    
    result = response.json()
    top_label = result["labels"][0]
    return top_label

def main():
    with open("emails.json", "r") as f:
        emails = json.load(f)
    
    for i, email in enumerate(emails):
        category = classify_email(email["subject"], email["body"])
        print(f"Email {i+1} classified as: {category}")

if __name__ == "__main__":
    main()