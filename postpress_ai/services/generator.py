from .openai_client import OpenAIClient

def generate_preview(subject: str, genre: str, tone: str) -> dict:
    client = OpenAIClient()
    return client.generate_article(subject, genre, tone)
