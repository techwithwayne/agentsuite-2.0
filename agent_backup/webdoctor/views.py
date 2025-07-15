import json
import markdown
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.core.mail import EmailMultiAlternatives
from django.utils.html import strip_tags
from django.conf import settings
from django.shortcuts import render
from .models import Conversation
from .ai_agent import get_agent_response
from django.views.decorators.clickjacking import xframe_options_exempt

# Add this to align with ai_agent
website_issue_keywords = [
    "wordpress", "site", "website", "plugin", "loading", "error", "broken",
    "dashboard", "page", "theme", "host", "domain", "ssl", "update", "redirect",
    "database", "server", "hosting", "caching", "maintenance"
]

# Helper to enforce one short paragraph + invitation line
def enforce_short_response(gpt_response, is_diagnostic, invitation="But tell me your issue and let’s see if I can help."):
    if is_diagnostic:
        return gpt_response.strip()
    import re
    paragraphs = re.split(r'\n{2,}', gpt_response.strip())
    first_paragraph = paragraphs[0] if paragraphs else gpt_response.strip()
    words = first_paragraph.split()
    trimmed = " ".join(words[:30])
    final = f"{trimmed.strip()}\n\n{invitation}"
    return final

@csrf_exempt
def chat_with_agent(request):
    if request.method != "POST":
        return JsonResponse({"error": "Only POST allowed"}, status=405)

    try:
        data = json.loads(request.body)

        name = data.get("name", "").strip()
        email = data.get("email", "").strip()
        subject = data.get("subject", "").strip()
        user_message = data.get("message", "").strip()
        session_id = data.get("session_id", "").strip()

        if not user_message:
            return JsonResponse({"error": "Empty message provided."}, status=400)

        # Determine if this is a diagnostic message
        is_diagnostic = any(keyword in user_message.lower() for keyword in website_issue_keywords)

        # Retrieve last 5 conversation pairs for memory
        context_convos = []
        if session_id:
            past_convos = Conversation.objects.filter(session_id=session_id).order_by('-timestamp')[:5][::-1]
            for convo in past_convos:
                context_convos.append({"role": "user", "content": convo.user_message})
                context_convos.append({"role": "assistant", "content": convo.agent_response})

        # Generate AI response with memory
        raw_response = get_agent_response(user_message, context_convos)
        response = enforce_short_response(raw_response, is_diagnostic)

        # Check if fallback triggered
        if response.strip().lower().startswith("i'm here to help with your website issues"):
            return JsonResponse({"response": response, "fallback": True, "diagnostic": True})

        # Save conversation with session memory
        convo = Conversation.objects.create(
            session_id=session_id or None,
            name=name or None,
            email=email or None,
            subject=subject or None,
            user_message=user_message,
            agent_response=response
        )

        # Send email if provided
        if email:
            name_line_user = f"**Name:** {name}\n" if name else ""
            report_heading = f"Here is your report, {name}:" if name else "Here is your report:"

            user_markdown_content = f"""
### Here is your report from Tech With Wayne

{name_line_user}**Email:** {email}
**Subject:** {subject or 'No Subject'}

**{report_heading}**
{user_message}

---

Thanks for reaching out! I’ve taken a look at your website issue and have some ideas to help you get it sorted.

If you’d like to chat about it, you can [book a free consultation here](https://techwithwayne.com/free-consultation/). I’d love to help you move things forward.

---
"""

            admin_markdown_content = f"""
### 🩺 Website Doctor Lead

**Name:** {name or 'N/A'}
**Email:** {email}
**Subject:** {subject or 'No Subject'}

**User Message:**
{user_message}

**AI Diagnosis:**
{response}

---

**Time:** {convo.timestamp.strftime('%Y-%m-%d %H:%M:%S')}
"""

            def build_html_email(content):
                html_body = markdown.markdown(content, extensions=["extra"])
                return f"""
<html>
  <head>
    <style>
      body {{ font-family: sans-serif; font-size: 14px; color: #222; }}
      ol, ul {{ padding-left: 20px; }}
      li {{ margin-bottom: 6px; }}
      pre {{ background-color: #f4f4f4; padding: 10px; border-radius: 4px; font-size: 13px; overflow-x: auto; }}
      code {{ font-family: monospace; color: #000; }}
      .signature {{ margin-top: 30px; font-style: italic; }}
      .cta {{ margin-top: 20px; background: #ff6c00; color: white; padding: 10px; border-radius: 6px; display: inline-block; text-decoration: none; }}
    </style>
  </head>
  <body>
    <img src="https://techwithwayne.com/wp-content/uploads/2025/06/techwithwayne-featured-image-wayne-hatter.jpg" alt="Tech With Wayne Logo" style="max-width: 200px; height: auto;" />
    {html_body}
    <div class="signature">— Wayne from <strong>Tech With Wayne</strong></div>
    <p><a href="mailto:techwithwayne@gmail.com?subject=Free Consultation Request" class="cta">Reply to this email to schedule a free consultation</a></p>
  </body>
</html>
"""

            html_email_user = build_html_email(user_markdown_content)
            plain_text_user = strip_tags(html_email_user)

            html_email_admin = build_html_email(admin_markdown_content)
            plain_text_admin = strip_tags(html_email_admin)

            email_msg_user = EmailMultiAlternatives(
                subject="🩺 Your Website Doctor Review",
                body=plain_text_user,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[email],
            )
            email_msg_user.attach_alternative(html_email_user, "text/html")
            email_msg_user.send()

            email_msg_admin = EmailMultiAlternatives(
                subject="🩺 New Website Doctor Lead",
                body=plain_text_admin,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=["techwithwayne@gmail.com"],
                bcc=["crm-sync@yourcrm.com"]
            )
            email_msg_admin.attach_alternative(html_email_admin, "text/html")
            email_msg_admin.send()

        return JsonResponse({
            "response": response,
            "diagnostic": is_diagnostic
        })

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON."}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)



def test_widget(request):
    return render(request, "test_widget.html")

@xframe_options_exempt
def chatbot_iframe_view(request):
    return render(request, 'agent/widget_frame.html')
