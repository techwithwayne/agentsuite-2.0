# Import the os module for environment variable access
import os
# Import settings from django.conf to access Django project settings
from django.conf import settings
# Import OpenAI class from openai library for API interactions
from openai import OpenAI

# Define a function to create and return an OpenAI client instance
def get_openai_client():
    # Retrieve the OpenAI API key from environment variables or Django settings, default to None if not found
    api_key = os.getenv("OPENAI_API_KEY", getattr(settings, "OPENAI_API_KEY", None))
    # Create and return an OpenAI client with the retrieved API key
    return OpenAI(api_key=api_key)

# Define a dictionary of diagnostic categories for website issues, each with associated keywords
DIAGNOSTIC_CATEGORIES = {
    "Performance": ["slow", "lag", "takes forever", "8 seconds", "load time"],
    "Design/Layout": ["broken", "misaligned", "mobile", "images", "fonts", "responsive"],
    "Functionality": ["form", "button", "submit", "not working", "doesn't work"],
    "Access/Errors": ["403", "404", "500", "white screen", "can't log in", "error"],
    "Update/Plugin": ["plugin", "update", "theme", "broke", "conflict"],
    "Security/Hack": ["hacked", "spam", "malware", "injected", "redirect"],
    "Hosting/DNS": ["dns", "hosting", "cloudflare", "propagation", "server"]
}

# Define a function to get clarifying questions based on the issue category
def get_clarifying_questions(category):
    # Define fallback questions if no specific category matches
    fallback = [
        "Can you clarify the problem a bit more?",
        "What exactly happens when the issue occurs?",
        "When did the issue start and how often does it happen?"
    ]
    # Define a dictionary of questions for each diagnostic category
    question_bank = {
        "Performance": [
            "Is your site slow to load on all devices and browsers, or only some?",
            "Does it load slowly on both Wi-Fi and mobile data?",
            "Has anything recently changed on your site before it got slow?"
        ],
        "Design/Layout": [
            "What part of the design looks broken or off?",
            "Is the issue happening on mobile, desktop, or both?",
            "Has the layout issue always been there or did it just start recently?"
        ],
        "Functionality": [
            "Which feature or page isn't working as expected?",
            "What do you expect to happen vs what actually happens?",
            "Have you tested this in multiple browsers?"
        ],
        "Access/Errors": [
            "What error are you seeing (e.g. 403, 404, white screen)?",
            "When does the error appear - right when loading the site or after clicking something?",
            "Are others also seeing this error, or just you?"
        ],
        "Update/Plugin": [
            "Did the problem start after installing or updating a plugin or theme?",
            "Which plugins/themes have you recently changed?",
            "Have you tried deactivating plugins to see if one causes it?"
        ],
        "Security/Hack": [
            "What makes you think the site was hacked?",
            "Are you seeing popups, redirects, or strange content?",
            "Have you recently changed passwords or installed security tools?"
        ],
        "Hosting/DNS": [
            "Have you recently switched hosting providers or made DNS changes?",
            "Is your domain showing any errors in DNS tools?",
            "Have you contacted your hosting provider about this?"
        ]
    }
    # Return the questions for the given category or fallback if not found
    return question_bank.get(category, fallback)

# Define a function to classify the user's issue using OpenAI
def classify_issue(user_input):
    # Construct the prompt for the OpenAI model using string concatenation
    prompt = (
        "You are a helpful support agent. Categorize the user's website issue into one of these diagnostic categories:\n"
        + ", ".join(DIAGNOSTIC_CATEGORIES.keys()) + "\n\n"
        + "Respond in this format:\n"
        + "Category: <CATEGORY>\n"
        + "Confidence: <0-100>\n"
        + "ClarifyingQuestion: <QUESTION to understand issue better>\n\n"
        + "User Input:\n"
        + '"' + user_input + '"'
    )
    # Get the OpenAI client instance
    client = get_openai_client()
    # Create a chat completion request to classify the issue
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "You classify website problems into categories and ask clarifying questions."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.4
    )

    # Extract the response content and strip whitespace
    result = response.choices[0].message.content.strip()
    # Split the result into lines for parsing
    lines = result.splitlines()
    # Initialize default values for category, confidence, and clarifying question
    category = "Unclassified"
    confidence = 0
    clarifying_question = "Can you describe the issue a bit more so I can help?"

    # Loop through each line to parse the response
    for line in lines:
        # Check if the line starts with "Category:"
        if line.startswith("Category:"):
            # Extract and strip the category value
            category = line.replace("Category:", "").strip()
        # Check if the line starts with "Confidence:"
        elif line.startswith("Confidence:"):
            # Try to parse the confidence as an integer
            try:
                confidence = int(line.replace("Confidence:", "").strip())
            # If parsing fails, default to 50
            except:
                confidence = 50
        # Check if the line starts with "ClarifyingQuestion:"
        elif line.startswith("ClarifyingQuestion:"):
            # Extract and strip the clarifying question
            clarifying_question = line.replace("ClarifyingQuestion:", "").strip()

    # Return the parsed category, confidence, and clarifying question
    return category, confidence, clarifying_question

# Define a function to summarize the issue based on conversation history
def summarize_issue(history, category):
    # Extract user messages from the history
    user_messages = [m['content'] for m in history if m['role'] == 'user']
    # Construct the summary prompt using string concatenation
    summary_prompt = (
        "You are a helpful AI support agent. Summarize the user's issue based on this conversation in a friendly and clear way.\n\n"
        + "Category: " + category + "\n"
        + "Conversation:\n"
        + '\n'.join(user_messages) + "\n\n"
        + "Respond in 1-3 sentences like a website doctor would explain it to the user."
    )
    # Get the OpenAI client instance
    client = get_openai_client()
    # Create a chat completion request to summarize the issue
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "You summarize website problems conversationally, like a helpful doctor."},
            {"role": "user", "content": summary_prompt}
        ],
        temperature=0.6
    )
    # Return the stripped summary from the response
    return response.choices[0].message.content.strip()

# Define a function to translate text using OpenAI if not English
def translate(text, lang):
    # If language is English or text is empty, return the original text
    if lang == "en" or not text:
        return text
    # Construct the translation prompt
    prompt = "Translate the following message into " + lang + ":\n\n" + text
    # Get the OpenAI client instance
    client = get_openai_client()
    # Create a chat completion request for translation
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "You are a professional translator."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.3
    )
    # Return the stripped translated text
    return response.choices[0].message.content.strip()

# Define the main function to get the agent's response based on conversation state
def get_agent_response(history, stage="initial", category=None, clarifications=0, lang="en"):
    # Get the last user input if history exists, else empty string
    last_user_input = history[-1]['content'] if history else ""
    # Lowercase and strip the user input for comparison
    user_input = last_user_input.lower().strip()

    # Define phrases that indicate conversation closing
    closing_phrases = ["thanks", "thank you", "bye", "goodbye", "that's all", "got it", "appreciate it", "ok cool"]
    # Check if stage is offered_report or report_sent and input contains closing phrase
    if stage in ["offered_report", "report_sent"] and any(phrase in user_input for phrase in closing_phrases):
        # Define the final message for closing the conversation
        final_msg = "You're very welcome! 😊 If you ever need more help, I'm just a click away. Take care!"
        # Return the response dict with translated message and updated state
        return {
            "response": translate(final_msg, lang),
            "next_stage": "closed",
            "category": category,
            "clarifications": clarifications,
            "typing_delay": 3
        }

    # Handle initial stage
    if stage == "initial":
        # Classify the issue based on last user input
        category, confidence, question = classify_issue(last_user_input)
        # Determine response text based on confidence level
        response_text = question if confidence >= 70 else "Hmm, I'm not quite sure yet - could you describe that a bit differently?"
        # Return the response dict with translated text and updated state
        return {
            "response": translate(response_text, lang),
            "next_stage": "clarifying" if confidence >= 70 else "initial",
            "category": category if confidence >= 70 else None,
            "clarifications": 1 if confidence >= 70 else clarifications + 1,
            "typing_delay": 4
        }

    # Handle clarifying stage
    elif stage == "clarifying":
        # Get the last clarifications messages from history
        asked = history[-clarifications:] if clarifications > 0 else []
        # Get the clarifying questions for the category
        clarifying_set = get_clarifying_questions(category)
        # Filter remaining questions not already asked by assistant
        remaining = [q for q in clarifying_set if q not in [m['content'] for m in asked if m['role'] == 'assistant']]

        # If enough clarifications or no remaining questions, summarize
        if clarifications >= 2 or not remaining:
            # Get the issue summary
            summary = summarize_issue(history, category)
            # Construct response text with summary and report offer
            response_text = summary + " Would you like me to email you a full diagnostic report with tips to fix it?"
            # Return the response dict with translated text and updated state
            return {
                "response": translate(response_text, lang),
                "next_stage": "summarize",
                "category": category,
                "clarifications": clarifications,
                "typing_delay": 4
            }

        # Determine batch size for next questions (up to 3)
        batch_size = min(3, len(remaining))
        # Get the batch of remaining questions
        batch = remaining[:batch_size]
        # Return the response dict with translated batch and updated state
        return {
            "response": translate("\n\n".join(batch), lang),
            "next_stage": "clarifying",
            "category": category,
            "clarifications": clarifications + 1,
            "typing_delay": 4
        }

    # Handle summarize stage
    elif stage == "summarize":
        # If user agrees to report, offer form
        if user_input in ["yes", "sure", "okay", "ok", "yep", "yeah"]:
            # Return response dict with form prompt
            return {
                "response": translate("No problem. Just enter your name and email below to get a report. It's free and tailored to your issue.", lang),
                "next_stage": "offered_report",
                "category": category,
                "clarifications": clarifications,
                "typing_delay": 4
            }
        # If user declines, stay in summarize
        elif user_input in ["no", "not now", "maybe later"]:
            # Return response dict with decline acknowledgment
            return {
                "response": translate("Totally fine! If you change your mind, just let me know and I'll prepare a report for you.", lang),
                "next_stage": "summarize",
                "category": category,
                "clarifications": clarifications,
                "typing_delay": 4
            }
        # Otherwise, re-ask about the report
        else:
            # Return response dict with report offer
            return {
                "response": translate("Would you like me to email you a full diagnostic report with tips to fix it?", lang),
                "next_stage": "summarize",
                "category": category,
                "clarifications": clarifications,
                "typing_delay": 4
            }

    # Handle offered_report stage
    elif stage == "offered_report":
        # Return response dict with form instruction
        return {
            "response": translate("Awesome. Just fill out your name and email below and I'll generate your custom report. 📬", lang),
            "next_stage": "offered_report",
            "category": category,
            "clarifications": clarifications,
            "typing_delay": 4
        }

    # Define fallback message for unknown stages
    fallback = "Let's take another look together. Could you explain a bit more?"
    # Return response dict with fallback and reset state
    return {
        "response": translate(fallback, lang),
        "next_stage": "initial",
        "category": None,
        "clarifications": 0,
        "typing_delay": 4
    }