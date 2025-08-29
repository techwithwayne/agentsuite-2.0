# assistant_runner.py
# Import standard libraries
import os
import json
import re
import requests

# Import Django settings and models
from django.conf import settings
from django.core.mail import send_mail
from webdoctor.models import UserInteraction, DiagnosticReport

# Import OpenAI client
from openai import OpenAI

# Define tools (copied from ai_agent.py for consistency)
send_email_diagnostic_tool = {
    "type": "function",
    "function": {
        "name": "send_email_diagnostic",
        "description": "Send a diagnostic report to the user by email.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "User's name for the email greeting"
                },
                "email": {
                    "type": "string",
                    "description": "User's email address to send the report to"
                },
                "issue": {
                    "type": "string",
                    "description": "Summary of the user’s website issue"
                }
            },
            "required": ["name", "email", "issue"]
        }
    }
}

recommend_fixes_tool = {
    "type": "function",
    "function": {
        "name": "recommend_fixes",
        "description": "Suggest website fixes based on a known diagnostic category.",
        "parameters": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": [
                        "Performance",
                        "Design/Layout",
                        "Functionality",
                        "Access/Errors",
                        "Update/Plugin",
                        "Security/Hack",
                        "Hosting/DNS"
                    ],
                    "description": "The diagnosed category of the user's issue"
                }
            },
            "required": ["category"]
        }
    }
}

SHIRLEY_TOOLS = [
    send_email_diagnostic_tool,
    recommend_fixes_tool,
    {
        "type": "function",
        "function": {
            "name": "measure_speed",
            "description": "Check a website's performance using Google's PageSpeed API.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The full URL of the website to test, including https://"
                    }
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_plugin_list",
            "description": "Scan a WordPress website's HTML for plugin hints (e.g., Elementor, WooCommerce, etc).",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The public URL of the WordPress site to scan"
                    }
                },
                "required": ["url"]
            }
        }
    }
]

# Get the API key from environment or settings
def get_openai_client():
    api_key = os.getenv("OPENAI_API_KEY", getattr(settings, "OPENAI_API_KEY", None))
    print("Loaded OpenAI API key in app:", api_key[:10] + "..." if api_key else "None")
    print("Key source:", "Environment" if os.getenv("OPENAI_API_KEY") else "Django settings")
    if not api_key:
        raise ValueError("❌ Missing OpenAI API key.")
    if not api_key.startswith("sk-") and not api_key.startswith("sk-proj-"):
        raise ValueError(f"❌ Invalid API key format: {api_key[:10]}...")
    return OpenAI(api_key=api_key)

# Shirley thread manager — handles persistent assistant logic
def run_shirley(message, session):
    client = get_openai_client()

    # Create or reuse thread
    thread_id = session.get("shirley_thread_id", None)
    if thread_id and len(thread_id) > 64:
        print(f"⚠️ Thread ID too long, resetting: {thread_id}")
        thread_id = None

    if thread_id:
        try:
            thread = client.beta.threads.retrieve(thread_id)
        except Exception as e:
            print("⚠️ Could not retrieve thread — resetting. Error:", e)
            thread = client.beta.threads.create()
            thread_id = thread.id
    else:
        thread = client.beta.threads.create()
        thread_id = thread.id

    session["shirley_thread_id"] = thread_id

    # Add message to thread
    client.beta.threads.messages.create(
        thread_id=thread_id,
        role="user",
        content=message
    )

    # Run assistant with tools
    try:
        run = client.beta.threads.runs.create(
            thread_id=thread_id,
            assistant_id=getattr(settings, "OPENAI_ASSISTANT_ID", os.getenv("OPENAI_ASSISTANT_ID")),
            tools=SHIRLEY_TOOLS,
            tool_choice="auto"
        )

        # Poll for completion or action
        while run.status in ['queued', 'in_progress', 'requires_action']:
            run = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)

            if run.status == 'requires_action':
                tool_outputs = []
                for tool_call in run.required_action.submit_tool_outputs.tool_calls:
                    function_name = tool_call.function.name
                    arguments = json.loads(tool_call.function.arguments)

                    if function_name == "send_email_diagnostic":
                        name = arguments["name"]
                        email = arguments["email"]
                        issue = arguments["issue"]

                        if not re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', email):
                            output = {"error": "Invalid email format"}
                        else:
                            UserInteraction.objects.create(name=name, email=email, issue_description=issue)
                            report_content = (
                                f"Diagnostic Report for {name}\n"
                                f"Issue: {issue}\n"
                                f"Suggested Actions: Check hosting performance, optimize images, or contact Wayne’s team for a free consultation."
                            )
                            DiagnosticReport.objects.create(
                                user_email=email,
                                issue_details=issue,
                                report_content=report_content
                            )
                            try:
                                send_mail(
                                    'Diagnostic Report',
                                    report_content,
                                    settings.DEFAULT_FROM_EMAIL,
                                    [email],
                                    fail_silently=False,
                                )
                                output = {"message": "Report sent to your email!"}
                            except Exception as e:
                                output = {"error": f"Failed to send email: {str(e)}"}

                    elif function_name == "recommend_fixes":
                        category_arg = arguments["category"]
                        fixes = {
                            "Performance": [
                                "Optimize images and use lazy loading.",
                                "Minify CSS, JavaScript, and HTML.",
                                "Enable browser caching.",
                                "Use a Content Delivery Network (CDN).",
                                "Reduce server response time."
                            ],
                            "Design/Layout": [
                                "Ensure responsive design for mobile devices.",
                                "Check for broken links and images.",
                                "Improve typography and color contrast for readability.",
                                "Organize content with proper headings and sections.",
                                "Test layout in different browsers."
                            ],
                            "Functionality": [
                                "Debug JavaScript errors in console.",
                                "Test forms and interactive elements.",
                                "Ensure compatibility with different devices.",
                                "Update plugins and themes.",
                                "Check for conflicts between scripts."
                            ],
                            "Access/Errors": [
                                "Verify DNS settings and hosting status.",
                                "Check for 404 errors and redirect properly.",
                                "Monitor server logs for errors.",
                                "Ensure SSL certificate is valid.",
                                "Test website accessibility from different locations."
                            ],
                            "Update/Plugin": [
                                "Update WordPress core, themes, and plugins.",
                                "Backup site before updates.",
                                "Test updates in a staging environment.",
                                "Remove unused plugins.",
                                "Check for plugin compatibility issues."
                            ],
                            "Security/Hack": [
                                "Install security plugins like Wordfence or Sucuri.",
                                "Change passwords and use two-factor authentication.",
                                "Scan for malware and clean infected files.",
                                "Secure file permissions.",
                                "Monitor for suspicious activity."
                            ],
                            "Hosting/DNS": [
                                "Contact hosting provider for support.",
                                "Check DNS propagation.",
                                "Verify domain registration and expiration.",
                                "Optimize hosting plan for traffic needs.",
                                "Set up proper email configurations if needed."
                            ]
                        }
                        suggested_fixes = fixes.get(category_arg, ["No fixes available for this category."])
                        output = {'fixes': suggested_fixes}

                    elif function_name == "measure_speed":
                        url = arguments["url"]
                        try:
                            api_url = f"https://www.googleapis.com/pagespeedonline/v5/runPagespeed?url={url}"
                            response = requests.get(api_url)
                            response.raise_for_status()
                            result = response.json()
                            lighthouse = result.get('lighthouseResult', {})
                            metrics = {
                                'performance_score': lighthouse.get('categories', {}).get('performance', {}).get('score', 0) * 100,
                                'fcp': lighthouse.get('audits', {}).get('first-contentful-paint', {}).get('displayValue', ''),
                                'lcp': lighthouse.get('audits', {}).get('largest-contentful-paint', {}).get('displayValue', ''),
                                'cls': lighthouse.get('audits', {}).get('cumulative-layout-shift', {}).get('displayValue', ''),
                                'tbt': lighthouse.get('audits', {}).get('total-blocking-time', {}).get('displayValue', ''),
                            }
                            output = metrics
                        except Exception as e:
                            output = {'error': str(e)}

                    elif function_name == "get_plugin_list":
                        url = arguments["url"]
                        try:
                            response = requests.get(url)
                            response.raise_for_status()
                            html = response.text
                            plugin_slugs = set(re.findall(r'/wp-content/plugins/([^/]+)/', html))
                            slug_to_name = {
                                'elementor': 'Elementor',
                                'woocommerce': 'WooCommerce',
                                'wordpress-seo': 'Yoast SEO',
                                'contact-form-7': 'Contact Form 7',
                                'jetpack': 'Jetpack',
                                'akismet': 'Akismet',
                                'wp-super-cache': 'WP Super Cache',
                                'all-in-one-seo-pack': 'All in One SEO',
                                'gravityforms': 'Gravity Forms',
                                'wpforms-lite': 'WPForms',
                                'google-analytics-for-wordpress': 'MonsterInsights',
                                'updraftplus': 'UpdraftPlus',
                                'wordfence': 'Wordfence Security',
                                'really-simple-ssl': 'Really Simple SSL',
                                'duplicate-post': 'Duplicate Post',
                                # Add more as needed
                            }
                            plugins = [slug_to_name.get(slug, slug.capitalize().replace('-', ' ')) for slug in plugin_slugs]
                            output = {'plugins': plugins}
                        except Exception as e:
                            output = {'error': str(e)}

                    tool_outputs.append({
                        "tool_call_id": tool_call.id,
                        "output": json.dumps(output)
                    })

                run = client.beta.threads.runs.submit_tool_outputs(
                    thread_id=thread_id,
                    run_id=run.id,
                    tool_outputs=tool_outputs
                )

        if run.status == 'failed':
            raise RuntimeError("❌ Assistant run failed.")

        # Get latest message
        messages = client.beta.threads.messages.list(thread_id=thread_id)
        latest = next((m for m in messages.data if m.role == "assistant"), None)

        if not latest:
            raise RuntimeError("❌ No assistant message returned.")

        # Parse as JSON for v2
        try:
            assistant_msg = json.loads(latest.content[0].text.value)
        except json.JSONDecodeError as e:
            print("Error parsing assistant response as JSON:", e)
            assistant_msg = {
                "response": "Error: Invalid response format from assistant",
                "next_stage": "initial",
                "category": None,
                "clarifications": 0
            }

        return {
            "response": assistant_msg["response"],
            "next_stage": assistant_msg["next_stage"],
            "category": assistant_msg["category"] if assistant_msg["category"] != "None" else None,
            "clarifications": assistant_msg["clarifications"],
            "thread_id": thread_id,
            "run_id": run.id,
            "message_id": latest.id,
            "role": latest.role,
            "timestamp": latest.created_at,
        }
    except Exception as e:
        print("Error in run_shirley:", str(e))
        return {
            "response": f"Error: Failed to get response from assistant ({str(e)})",
            "next_stage": "initial",
            "category": None,
            "clarifications": 0,
            "thread_id": thread_id,
            "run_id": None,
            "message_id": None,
            "role": "assistant",
            "timestamp": None
        }