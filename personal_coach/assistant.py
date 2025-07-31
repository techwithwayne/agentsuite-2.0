# assistant.py
# This file connects to OpenAI's Assistant v2 and handles conversation flow

import os
from django.conf import settings
from openai import OpenAI

# Get your API key from the environment or Django settings
api_key = os.getenv("OPENAI_API_KEY", getattr(settings, "OPENAI_API_KEY", None))
client = OpenAI(api_key=api_key)

# Set your Assistant ID here after you create it at https://platform.openai.com/assistants
ASSISTANT_ID = "asst_YOUR_ASSISTANT_ID"

# Creates a new thread for each user session (optional: persist if needed)
def create_thread():
    thread = client.beta.threads.create()
    return thread.id

# Sends a message to the assistant thread and returns the latest messages
def send_message(thread_id, message_text):
    client.beta.threads.messages.create(
        thread_id=thread_id,
        role="user",
        content=message_text
    )

    run = client.beta.threads.runs.create_and_poll(
        thread_id=thread_id,
        assistant_id=ASSISTANT_ID
    )

    messages = client.beta.threads.messages.list(thread_id=thread_id)
    return messages
