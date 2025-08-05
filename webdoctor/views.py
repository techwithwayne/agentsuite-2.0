# webdoctor/views.py - SESSION-BASED Views with Unicode fix and conversation reset
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.views.decorators.http import require_http_methods
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db import transaction
from django.core.cache import cache
from webdoctor.models import UserInteraction, AgentResponse, DiagnosticReport
from webdoctor.ai_agent import get_agent_response
import json
import re
import logging
import time
from functools import wraps

logger = logging.getLogger('webdoctor')

def get_client_ip(request):
    """Get client IP address"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

def rate_limit(max_requests=10, window=60):
    """Simple rate limiting decorator"""
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            ip = get_client_ip(request)
            cache_key = f"rate_limit_{ip}_{view_func.__name__}"
            
            current_requests = cache.get(cache_key, 0)
            if current_requests >= max_requests:
                logger.warning(f"Rate limit exceeded for {ip}")
                return JsonResponse({
                    'error': 'Too many requests. Please wait a moment before trying again.'
                }, status=429)
            
            cache.set(cache_key, current_requests + 1, timeout=window)
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator

@ensure_csrf_cookie
def webdoctor_home(request):
    """Enhanced home view with CSRF cookie"""
    logger.info(f"Home page accessed from {get_client_ip(request)}")
    return render(request, 'webdoctor/chat_widget.html')

@ensure_csrf_cookie
def chat_widget(request):
    """Chat widget view with CSRF cookie"""
    return render(request, 'webdoctor/chat_widget.html')

def get_or_initialize_conversation(session, force_reset=False):
    """
    Get or initialize conversation state - COMPLETELY SESSION-BASED
    NO DATABASE CHECKS OR DEPENDENCIES
    
    Args:
        session: Django session object
        force_reset: If True, always create a new conversation
    """
    conversation_data = session.get("conversation")
    
    # Check if we need to initialize or reset
    needs_reset = (
        force_reset or
        not conversation_data or
        not isinstance(conversation_data, dict) or
        not conversation_data.get("history") or
        not isinstance(conversation_data.get("history"), list)
    )
    
    if needs_reset:
        logger.info("SESSION-ONLY: Initializing new conversation state (no database check)")
        conversation_data = {
            "history": [],
            "stage": "initial", 
            "category": None,
            "clarifications": 0,
            "start_time": timezone.now().isoformat(),
            "last_updated": timezone.now().isoformat(),
            "session_based": True,  # Flag to indicate this is session-only
            "reset_count": conversation_data.get("reset_count", 0) + 1 if conversation_data else 1
        }
        session["conversation"] = conversation_data
        session.modified = True
        logger.info(f"SESSION-RESET: New conversation #{conversation_data['reset_count']} initialized")
    
    return conversation_data

def update_conversation_state(session, new_stage, new_category, new_clarifications):
    """Safely update conversation state - SESSION-ONLY"""
    conversation_data = session.get("conversation", {})
    
    # Update the conversation state (session-based only)
    old_stage = conversation_data.get("stage", "unknown")
    conversation_data["stage"] = new_stage
    conversation_data["category"] = new_category
    conversation_data["clarifications"] = new_clarifications
    conversation_data["last_updated"] = timezone.now().isoformat()
    conversation_data["session_based"] = True
    
    # Mark session as modified and save
    session["conversation"] = conversation_data
    session.modified = True
    
    # ✅ Fix Unicode logging issue - use ASCII arrows
    logger.info(f"SESSION-ONLY UPDATE: {old_stage} -> {new_stage}, clarifications={new_clarifications} (NO DATABASE)")

@csrf_exempt
@rate_limit(max_requests=30, window=60)  # 30 requests per minute
@require_http_methods(["POST"])
def handle_message(request):
    """
    SESSION-BASED message handler with FORCE RESET capability
    """
    start_time = time.time()
    client_ip = get_client_ip(request)

    try:
        # Parse and validate JSON
        try:
            raw_body = request.body.decode("utf-8").strip()
            if not raw_body:
                logger.warning(f"Empty request body from {client_ip}")
                return JsonResponse({'error': 'Empty request body'}, status=400)
            data = json.loads(raw_body)
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            logger.warning(f"Invalid JSON from {client_ip}: {str(e)}")
            return JsonResponse({'error': 'Invalid JSON payload'}, status=400)

        # Extract and validate input
        message = data.get('message', '').strip()
        lang = data.get('lang', 'en')
        force_reset = data.get('force_reset', False)

        # ✅ HANDLE SPECIAL FORCE RESET MESSAGE
        if message == '__FORCE_RESET__' or force_reset:
            logger.info(f"FORCE RESET triggered from {client_ip}")
            
            # Clear session completely
            if 'conversation' in request.session:
                del request.session['conversation']
            request.session.modified = True
            
            # Initialize fresh conversation
            conversation_data = get_or_initialize_conversation(request.session, force_reset=True)
            
            return JsonResponse({
                "response": "Conversation reset successfully",
                "stage": "initial",
                "success": True,
                "reset": True,
                "debug": {
                    "action": "force_reset",
                    "new_state": conversation_data
                }
            })

        if not message:
            return JsonResponse({'error': 'Message cannot be empty'}, status=400)
        if len(message) > 500:
            return JsonResponse({'error': 'Message too long (max 500 characters)'}, status=400)

        # Basic content filtering
        prohibited_patterns = [
            r'<script.*?>.*?</script>',
            r'javascript:',
            r'eval\s*\(',
            r'onclick\s*='
        ]

        message_lower = message.lower()
        for pattern in prohibited_patterns:
            if re.search(pattern, message_lower, re.IGNORECASE):
                logger.warning(f"Prohibited content from {client_ip}: {pattern}")
                return JsonResponse({'error': 'Invalid message content'}, status=400)

        # ✅ DETECT CONVERSATION RESTART PATTERNS
        restart_indicators = [
            'my site', 'my website', 'website is', 'site is', 'having trouble',
            'problem with', 'issue with', 'help with', 'slow', 'broken', 'down',
            'not working', 'error', 'loading'
        ]
        
        # Get existing conversation
        conversation_data = get_or_initialize_conversation(request.session)
        
        # If we have a long conversation and user seems to be starting over
        if (len(conversation_data.get("history", [])) > 6 and 
            any(indicator in message_lower for indicator in restart_indicators)):
            
            logger.info(f"CONVERSATION RESTART detected from {client_ip}: '{message}'")
            conversation_data = get_or_initialize_conversation(request.session, force_reset=True)

        # Log current session state for debugging
        logger.info(f"SESSION STATE: stage={conversation_data['stage']}, clarifications={conversation_data['clarifications']}, history_length={len(conversation_data['history'])}")

        # Add user message to session history
        user_message = {
            "role": "user",
            "content": message,
            "timestamp": timezone.now().isoformat()
        }
        conversation_data["history"].append(user_message)

        # Special handling for very first message (greeting) - SESSION-BASED
        if len(conversation_data["history"]) == 1:
            logger.info("SESSION: First user message - ensuring initial stage")
            conversation_data["stage"] = "initial"
            conversation_data["clarifications"] = 0

        # Get AI response - COMPLETELY SESSION-BASED (NO DATABASE LOOKUPS)
        try:
            logger.info(f"SESSION-BASED AI CALL: stage={conversation_data['stage']}, clarifications={conversation_data['clarifications']}")
            
            ai_response = get_agent_response(
                history=conversation_data["history"],
                stage=conversation_data["stage"],
                category=conversation_data["category"],
                clarifications=conversation_data["clarifications"],
                lang=lang,
                request=request
            )
            
            # Validate AI response structure
            required_fields = ['response', 'next_stage', 'category', 'clarifications']
            for field in required_fields:
                if field not in ai_response:
                    logger.error(f"Missing field {field} in AI response")
                    ai_response[field] = None
            
            # Ensure response is not empty
            if not ai_response.get("response", "").strip():
                raise ValueError("Empty AI response")
                
            # Log the AI response for debugging
            logger.info(f"SESSION AI RESPONSE: {conversation_data['stage']} -> {ai_response.get('next_stage')}, clarifications={conversation_data['clarifications']} -> {ai_response.get('clarifications')}")

        except Exception as ai_error:
            logger.error(f"SESSION-BASED AI response failed for {client_ip}: {str(ai_error)}")
            ai_response = {
                "response": "I'm having trouble processing your request right now. Please try again in a moment.",
                "next_stage": conversation_data["stage"],
                "category": conversation_data["category"],
                "clarifications": conversation_data["clarifications"],
                "typing_delay": 4,
                "processing_time": 0
            }

        # Add assistant message to session history
        assistant_message = {
            "role": "assistant",
            "content": ai_response["response"],
            "timestamp": timezone.now().isoformat()
        }
        conversation_data["history"].append(assistant_message)

        # Update session conversation state (NO DATABASE)
        update_conversation_state(
            request.session,
            ai_response.get("next_stage", conversation_data["stage"]),
            ai_response.get("category", conversation_data["category"]),
            ai_response.get("clarifications", conversation_data["clarifications"])
        )

        # Store unique responses for analytics (optional - this doesn't affect conversation flow)
        try:
            # This is just for analytics and doesn't affect the conversation logic
            AgentResponse.get_or_create_response(ai_response["response"])
        except Exception as db_error:
            logger.error(f"Analytics save failed (non-critical): {str(db_error)}")
            # Continue anyway - this doesn't affect conversation flow

        # Log successful interaction
        processing_time = time.time() - start_time
        logger.info(f"SESSION-BASED message processed for {client_ip} in {processing_time:.2f}s - Final state: stage={ai_response.get('next_stage')}, clarifications={ai_response.get('clarifications')}")

        return JsonResponse({
            "response": ai_response["response"],
            "typing_delay": ai_response.get("typing_delay", 4),
            "stage": ai_response.get("next_stage", "initial"),
            "processing_time": processing_time,
            "success": True,
            # Debug info
            "debug": {
                "stage_transition": f"{conversation_data['stage']} -> {ai_response.get('next_stage')}",
                "clarifications": ai_response.get('clarifications'),
                "history_length": len(conversation_data["history"]),
                "session_based": True
            }
        })

    except ValidationError as ve:
        logger.warning(f"Validation error from {client_ip}: {str(ve)}")
        return JsonResponse({'error': 'Invalid input data'}, status=400)
    except Exception as e:
        processing_time = time.time() - start_time
        logger.error(f"Unexpected error from {client_ip} after {processing_time:.2f}s: {str(e)}")
        return JsonResponse({
            'error': 'An unexpected error occurred. Please try again.',
            'success': False
        }, status=500)

# ✅ IMPROVED RESET ENDPOINT - AVAILABLE IN PRODUCTION
@csrf_exempt
@require_http_methods(["POST"])
def reset_conversation(request):
    """Reset conversation state - SESSION-ONLY (Available in production)"""
    client_ip = get_client_ip(request)
    
    try:
        # Clear session conversation data
        if 'conversation' in request.session:
            old_conversation = request.session['conversation']
            del request.session['conversation']
            request.session.modified = True
            logger.info(f"CONVERSATION RESET: Session cleared for {client_ip}")
        else:
            logger.info(f"CONVERSATION RESET: No existing session for {client_ip}")
        
        # Initialize fresh conversation state
        get_or_initialize_conversation(request.session, force_reset=True)
        
        return JsonResponse({
            'message': 'Conversation reset successfully',
            'database_independent': True,
            'success': True
        })
        
    except Exception as e:
        logger.error(f"Conversation reset failed for {client_ip}: {str(e)}")
        return JsonResponse({
            'error': 'Failed to reset conversation',
            'success': False
        }, status=500)

# REST OF THE VIEWS REMAIN THE SAME...
@csrf_exempt
@rate_limit(max_requests=5, window=300)  # 5 form submissions per 5 minutes
@require_http_methods(["POST"])
def submit_form(request): 
    """
    Enhanced form submission - THIS IS THE ONLY DATABASE INTERACTION
    Only called when actually sending the final diagnostic report
    """
    client_ip = get_client_ip(request)

    logger.info(f"DATABASE INTERACTION: Final report submission from {client_ip}")

    try:
        # Parse JSON with empty check and decoding
        try:
            raw_body = request.body.decode("utf-8").strip()
            if not raw_body:
                logger.warning(f"Empty form body from {client_ip}")
                return JsonResponse({'error': 'Empty request body'}, status=400)
            data = json.loads(raw_body)
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            logger.warning(f"Invalid form JSON from {client_ip}: {str(e)}")
            return JsonResponse({'error': 'Invalid JSON payload'}, status=400)

        # Extract and validate form data
        name = data.get('name', '').strip()
        email = data.get('email', '').strip()
        issue = data.get('issue', '').strip()

        # Comprehensive validation
        errors = []

        if not name or len(name) < 2:
            errors.append("Name must be at least 2 characters long")
        elif len(name) > 100:
            errors.append("Name is too long (max 100 characters)")

        if not email:
            errors.append("Email address is required")
        elif not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
            errors.append("Please enter a valid email address")

        if not issue or len(issue) < 10:
            errors.append("Please provide more details about your issue (min 10 characters)")
        elif len(issue) > 1000:
            errors.append("Issue description is too long (max 1000 characters)")

        if errors:
            logger.warning(f"Form validation failed from {client_ip}: {errors}")
            return JsonResponse({'error': '; '.join(errors)}, status=400)

        # Check for duplicate recent submissions (database check only for final submission)
        try:
            recent_submission = UserInteraction.objects.filter(
                email=email,
                created_at__gte=timezone.now() - timezone.timedelta(minutes=5)
            ).first()

            if recent_submission:
                logger.warning(f"Duplicate submission from {email}")
                return JsonResponse({
                    'error': 'You recently submitted a request. Please wait a few minutes before submitting again.'
                }, status=400)
        except Exception as db_check_error:
            logger.error(f"Database check failed: {str(db_check_error)}")
            # Continue anyway - don't fail for database check issues

        # Create interaction with transaction - FINAL DATABASE WRITE
        try:
            with transaction.atomic():
                logger.info(f"DATABASE WRITE: Creating interaction record for {email}")
                
                interaction = UserInteraction.objects.create(
                    name=name,
                    email=email,
                    issue_description=issue,
                    ip_address=client_ip,
                    user_agent=request.META.get('HTTP_USER_AGENT', '')[:500]
                )

                # Generate comprehensive report
                report_content = f"""
Website Diagnostic Report for {name}

Issue Summary:
{issue}

Preliminary Analysis:
Based on your description, our AI diagnostic system has identified this as a priority issue requiring immediate attention.

Recommended Action Plan:

IMMEDIATE STEPS (Next 24 hours):
- Run a comprehensive site audit using tools like GTmetrix or Google PageSpeed Insights
- Check if your website is accessible from different locations and devices
- Verify that all critical functions (contact forms, checkout, etc.) are working
- Review your hosting provider's status page for any ongoing issues

PERFORMANCE OPTIMIZATION (This week):
- Optimize images: Compress large images and consider WebP format
- Review installed plugins: Deactivate any unused plugins
- Clear any caching if you have caching plugins installed
- Update WordPress core, themes, and plugins if needed

TECHNICAL REVIEW (Next 2 weeks):
- Monitor website loading speeds across different pages
- Check for broken links and fix any 404 errors
- Review website security and ensure SSL certificate is working
- Set up basic monitoring to track future issues

LONG-TERM IMPROVEMENTS:
- Consider upgrading hosting plan if performance issues persist
- Implement a content delivery network (CDN) for faster global loading
- Set up automated backups and monitoring alerts
- Schedule regular maintenance and updates

Next Steps:
1. Start with the immediate steps listed above
2. Monitor your website's performance over the next 48-72 hours
3. Document any improvements or ongoing issues
4. Consider professional consultation if problems persist

Need Expert Help?
Our team at TechWithWayne specializes in website optimization, troubleshooting, and digital solutions.

📧 Contact: support@techwithwayne.com
🌐 Website: https://apps.techwithwayne.com
📞 Consultation: Available for complex issues requiring hands-on expertise

This personalized report was generated by Shirley AI on {timezone.now().strftime('%B %d, %Y at %H:%M UTC')}.
Report ID: #{interaction.id}

Best regards,
Shirley - Your Website Doctor
TechWithWayne Digital Solutions

---
This report is confidential and intended only for {name} at {email}.
                """.strip()

                # Create report record - FINAL DATABASE WRITE
                report = DiagnosticReport.objects.create(
                    user_interaction=interaction,
                    user_email=email,
                    issue_details=issue,
                    report_content=report_content
                )

                # Send email with enhanced error handling
                try:
                    send_mail(
                        subject=f'Website Diagnostic Report for {name} - TechWithWayne',
                        message=report_content,
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=[email],
                        fail_silently=False,
                    )

                    # Mark as sent
                    report.mark_email_sent()

                    logger.info(f"DATABASE SUCCESS: Report sent to {email} from {client_ip}")

                    return JsonResponse({
                        'message': f'Perfect! Your diagnostic report has been sent to {email}. Check your inbox (and spam folder) in the next few minutes.',
                        'success': True,
                        'report_id': interaction.id
                    })

                except Exception as email_error:
                    logger.error(f"Email failed for {email}: {str(email_error)}")
                    return JsonResponse({
                        'error': 'I created your report but had trouble sending the email. Please verify your email address is correct and try again.',
                        'success': False
                    }, status=500)

        except Exception as db_error:
            logger.error(f"Database operation failed for {email}: {str(db_error)}")
            return JsonResponse({
                'error': 'There was a problem saving your information. Please try again in a moment.',
                'success': False
            }, status=500)

    except Exception as e:
        logger.error(f"Form submission failed from {client_ip}: {str(e)}")
        return JsonResponse({
            'error': 'There was a problem processing your request. Please try again in a moment.',
            'success': False
        }, status=500)

# ADDITIONAL UTILITY VIEWS FOR DIRECT API ACCESS

@csrf_exempt
@require_http_methods(["POST"])
def send_email_diagnostic(request):
    """Direct API endpoint for sending diagnostic emails - DATABASE INTERACTION ONLY"""
    return submit_form(request)  # Reuse the enhanced form handler

@csrf_exempt 
@rate_limit(max_requests=20, window=60)
@require_http_methods(["POST"])
def recommend_fixes(request):
    """Enhanced API endpoint for getting fix recommendations - NO DATABASE"""
    try:
        # Decode + check for empty body
        raw_body = request.body.decode("utf-8").strip()
        if not raw_body:
            logger.warning("Empty request body in recommend_fixes()")
            return JsonResponse({'error': 'Empty request body'}, status=400)

        data = json.loads(raw_body)
        category = data.get('category', '').strip()

        if not category:
            return JsonResponse({'error': 'Category is required'}, status=400)

        from webdoctor.ai_agent import handle_recommend_fixes
        result = handle_recommend_fixes({"category": category})

        return JsonResponse(result)

    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        logger.warning(f"JSON decode error in recommend_fixes: {str(e)}")
        return JsonResponse({'error': 'Invalid JSON payload'}, status=400)
    except Exception as e:
        logger.error(f"Recommend fixes failed: {str(e)}")
        return JsonResponse({'error': 'Failed to get recommendations'}, status=500)

@csrf_exempt
@rate_limit(max_requests=10, window=300)  # Limit speed tests
@require_http_methods(["POST"])
def measure_speed(request):
    """Enhanced API endpoint for measuring website speed - NO DATABASE"""
    try:
        # Decode + check for empty body
        raw_body = request.body.decode("utf-8").strip()
        if not raw_body:
            logger.warning("Empty JSON payload in measure_speed()")
            return JsonResponse({'error': 'Empty request body'}, status=400)

        data = json.loads(raw_body)
        url = data.get('url', '').strip()

        if not url:
            return JsonResponse({'error': 'URL is required'}, status=400)

        # Basic URL validation
        if not re.match(r'^https?:\/\/.+', url):
            return JsonResponse({'error': 'Please provide a valid URL starting with http:// or https://'}, status=400)

        from webdoctor.ai_agent import handle_measure_speed
        result = handle_measure_speed({"url": url})

        return JsonResponse(result)

    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        logger.warning(f"JSON decode error in measure_speed: {str(e)}")
        return JsonResponse({'error': 'Invalid JSON payload'}, status=400)
    except Exception as e:
        logger.error(f"Speed measurement failed: {str(e)}")
        return JsonResponse({'error': 'Speed test failed'}, status=500)

@csrf_exempt
@rate_limit(max_requests=15, window=300)  # Limit plugin scans
@require_http_methods(["POST"])
def get_plugin_list(request):
    """Enhanced API endpoint for scanning WordPress plugins - NO DATABASE"""
    try:
        # Decode + check for empty body
        raw_body = request.body.decode("utf-8").strip()
        if not raw_body:
            logger.warning("Empty request body in get_plugin_list()")
            return JsonResponse({'error': 'Empty request body'}, status=400)

        data = json.loads(raw_body)
        url = data.get('url', '').strip()

        if not url:
            return JsonResponse({'error': 'URL is required'}, status=400)

        # Basic URL validation
        if not re.match(r'^https?:\/\/.+', url):
            return JsonResponse({'error': 'Please provide a valid URL starting with http:// or https://'}, status=400)

        from webdoctor.ai_agent import handle_get_plugin_list
        result = handle_get_plugin_list({"url": url})

        return JsonResponse(result)

    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        logger.warning(f"JSON decode error in get_plugin_list: {str(e)}")
        return JsonResponse({'error': 'Invalid JSON payload'}, status=400)
    except Exception as e:
        logger.error(f"Plugin scan failed: {str(e)}")
        return JsonResponse({'error': 'Plugin scan failed'}, status=500)

# Debug endpoint for session state (remove in production)
@csrf_exempt
@require_http_methods(["GET"])
def debug_conversation(request):
    """Debug endpoint to check session-based conversation state"""
    if not settings.DEBUG:
        return JsonResponse({'error': 'Debug endpoint not available in production'}, status=404)
    
    conversation_data = request.session.get("conversation", {})
    
    return JsonResponse({
        'session_key': request.session.session_key,
        'conversation_state': conversation_data,
        'session_age': request.session.get_expiry_age() if hasattr(request.session, 'get_expiry_age') else 'unknown',
        'database_independent': True,
        'session_based_only': conversation_data.get('session_based', False)
    }, indent=2)