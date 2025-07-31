from openai import OpenAI

client = OpenAI(api_key='api')
try:
    assistant = client.beta.assistants.create(
        name="Test Assistant",
        model="gpt-4o",
        instructions="Test."
    )
    print("Success! Assistant ID:", assistant.id)
    client.beta.assistants.delete(assistant.id)  # Clean up
except Exception as e:
    print("Error:", str(e))
    
import openai

# Set your API key
api_key = 'YOUR_API_KEY_HERE'  # Replace with your actual key
openai.api_key = api_key

try:
    # Attempt a simple API call to list models (this is free and quick)
    response = openai.models.list()
    print("API key is valid! Here's a sample response:")
    print(response)  # If successful, you'll see a list of models
except openai.AuthenticationError as e:
    print("API key is invalid. Error details:")
    print(e)
except Exception as e:
    print("An unexpected error occurred:")
    print(e)