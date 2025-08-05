import os
import json
import re
import requests
import time
import hashlib
import logging
from functools import lru_cache
from typing import Dict, Any, Optional
from django.conf import settings
from django.core.mail import send_mail
from django.core.cache import cache
from django.utils import timezone
from openai import OpenAI
from webdoctor.models import UserInteraction, DiagnosticReport

logger = logging.getLogger('webdoctor')

class OpenAIClientManager:
    """Singleton OpenAI client manager"""
    _instance = None
    _client = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def get_client(self):
        if self._client is None:
            api_key = os.getenv("OPENAI_API_KEY", getattr(settings, "OPENAI_API_KEY", None))
            if not api_key:
                raise ValueError("No OpenAI API key found")
            
            self._client = OpenAI(
                api_key=api_key,
                timeout=30.0,
                max_retries=3
            )
            logger.info("OpenAI client initialized successfully")
        
        return self._client

# Global client manager instance
client_manager = OpenAIClientManager()

def get_openai_client():
    """Get cached OpenAI client"""
    return client_manager.get_client()

# ENHANCED TOOL DEFINITIONS WITH VALIDATION
send_email_diagnostic_tool = {
    "type": "function",
    "function": {
        "name": "send_email_diagnostic",
        "description": "Send a diagnostic report to the user by email after validation.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string", 
                    "description": "User's name for the email greeting",
                    "minLength": 1,
                    "maxLength": 100
                },
                "email": {
                    "type": "string", 
                    "description": "User's email address to send the report to",
                    "pattern": r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
                },
                "issue": {
                    "type": "string", 
                    "description": "Summary of the user's website issue",
                    "minLength": 10,
                    "maxLength": 1000
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
                        "Performance", "Design/Layout", "Functionality", 
                        "Access/Errors", "Update/Plugin", "Security/Hack", "Hosting/DNS"
                    ],
                    "description": "The diagnosed category of the user's issue"
                }
            },
            "required": ["category"]
        }
    }
}

measure_speed_tool = {
    "type": "function",
    "function": {
        "name": "measure_speed",
        "description": "Check a website's performance using Google's PageSpeed API.",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string", 
                    "description": "The full URL of the website to test, including https://",
                    "pattern": r"^https?:\/\/.+"
                }
            },
            "required": ["url"]
        }
    }
}

get_plugin_list_tool = {
    "type": "function",
    "function": {
        "name": "get_plugin_list",
        "description": "Scan a WordPress website's HTML for plugin hints.",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string", 
                    "description": "The public URL of the WordPress site to scan",
                    "pattern": r"^https?:\/\/.+"
                }
            },
            "required": ["url"]
        }
    }
}

SHIRLEY_TOOLS = [
    send_email_diagnostic_tool, 
    recommend_fixes_tool, 
    measure_speed_tool, 
    get_plugin_list_tool
]

# ENHANCED ASSISTANT MANAGEMENT
@lru_cache(maxsize=1)
def get_assistant_id():
    """Cached assistant ID retrieval"""
    assistant_id = os.getenv("OPENAI_ASSISTANT_ID", getattr(settings, "OPENAI_ASSISTANT_ID", None))
    
    if not assistant_id:
        logger.info("Creating new Shirley assistant...")
        assistant_id = create_shirley_assistant()
        logger.info(f"Created assistant: {assistant_id}")
    
    return assistant_id

def create_shirley_assistant():
    """Create assistant with SESSION-ONLY instructions (NO DATABASE DEPENDENCIES)"""
    client = get_openai_client()
    
    try:
        assistant = client.beta.assistants.create(
            name="Shirley - WebDoctor AI",
            model="gpt-4o",
            instructions="""
You are Shirley, a friendly website doctor. 

CRITICAL: You are a SESSION-BASED assistant. You have NO memory of previous conversations or database records. Each conversation is completely independent and starts fresh.

MANDATORY CONVERSATION FLOW:
1. INITIAL: Ask what's wrong with their website
2. CLARIFYING: Ask exactly 2-3 specific diagnostic questions (minimum 2, maximum 3)
3. REPORT OFFERING: Only after 2+ questions, offer the diagnostic report
4. COMPLETION: Collect details and send report

SESSION-ONLY RULES:
- You do NOT have access to any previous conversations or database records
- You do NOT know anything about this user's history
- You MUST ask clarifying questions regardless of what you think you might know
- Each conversation starts completely fresh - treat every user as brand new

RESPONSE FORMAT - You MUST respond with valid JSON ONLY:
{
    "response": "your conversational message here",
    "next_stage": "clarifying|offered_report|hybrid_closing",
    "category": "Performance|Design/Layout|Functionality|Access/Errors|Update/Plugin|Security/Hack|Hosting/DNS|null",
    "clarifications": 0
}

CLARIFYING QUESTIONS (ALWAYS ASK 2-3):
- "When did you first notice this problem?"
- "Does this happen on all pages or just specific ones?" 
- "What browser are you using?"
- "Have you made any recent changes to your website?"
- "Is your site WordPress-based or another platform?"
- "Are you getting any specific error messages?"
- "How long has your website been experiencing this issue?"

STAGE PROGRESSION RULES:
- initial -> clarifying (start asking questions)
- clarifying -> clarifying (continue until 2+ questions asked)
- clarifying -> offered_report (only after sufficient questions)
- offered_report -> hybrid_closing (after sending report)

NEVER SKIP THE CLARIFYING STAGE. NEVER ASSUME YOU KNOW ENOUGH.
ALWAYS ASK AT LEAST 2 QUESTIONS BEFORE OFFERING REPORTS.
            """,
            tools=SHIRLEY_TOOLS,
            metadata={"project": "webdoctor", "version": "4.0", "database_independent": "true"},
            temperature=0.3,
            response_format={"type": "json_object"}
        )
        
        return assistant.id
        
    except Exception as e:
        logger.error(f"Failed to create assistant: {str(e)}")
        raise ValueError(f"Could not create OpenAI assistant: {str(e)}")

def force_stage_logic(stage: str, clarifications: int, user_message: str, assistant_response: str) -> tuple[str, int]:
    """
    ENFORCED session-based stage progression - NO DATABASE DEPENDENCIES
    This function ensures proper conversation flow using ONLY session state
    """
    user_msg_lower = user_message.lower()
    response_lower = assistant_response.lower()
    
    logger.info(f"SESSION-BASED STAGE LOGIC: stage={stage}, clarifications={clarifications}")
    
    # RULE 1: From initial, ALWAYS go to clarifying after first user response
    if stage == "initial":
        next_stage = "clarifying"
        next_clarifications = 1  # Set to 1 since we're asking first question
        logger.info("SESSION-FORCED: initial -> clarifying (user responded to greeting)")
        
    # RULE 2: Stay in clarifying until we have asked at least 2 questions
    elif stage == "clarifying":
        if clarifications < 2:
            # Continue asking questions
            next_stage = "clarifying"
            next_clarifications = clarifications + 1
            logger.info(f"SESSION-FORCED: staying in clarifying, question #{next_clarifications}")
        else:
            # After 2+ questions, can offer report
            next_stage = "offered_report"
            next_clarifications = clarifications
            logger.info("SESSION-FORCED: clarifying -> offered_report (sufficient questions asked)")
            
    # RULE 3: Handle report offering stage - ✅ FIXED PROGRESSION
    elif stage == "offered_report":
        # Check if user said yes to report
        yes_words = ["yes", "sure", "okay", "ok", "please", "send", "absolutely", "definitely", "yeah"]
        if any(word in user_msg_lower for word in yes_words):
            # ✅ MOVE TO COMPLETION STAGE when user agrees
            next_stage = "hybrid_closing"  # Changed from staying in offered_report
            next_clarifications = clarifications
            logger.info("SESSION-FORCED: user agreed to report -> hybrid_closing (collecting details)")
        else:
            # Stay in offering stage if user hasn't agreed yet
            next_stage = "offered_report"
            next_clarifications = clarifications
            logger.info("SESSION-FORCED: staying in offered_report (user hasn't agreed yet)")
            
    # RULE 4: Handle closing stage - ✅ STAYS IN CLOSING FOR FORM COLLECTION
    elif stage == "hybrid_closing":
        next_stage = "hybrid_closing"
        next_clarifications = clarifications
        logger.info("SESSION-FORCED: staying in hybrid_closing (collecting form details)")
        
    else:
        # Fallback - go to clarifying (not initial to avoid repeated greetings)
        next_stage = "clarifying"
        next_clarifications = 1
        logger.info("SESSION-FORCED: fallback to clarifying")
    
    logger.info(f"SESSION-BASED OUTPUT: {stage} -> {next_stage}, session clarifications: {clarifications} -> {next_clarifications}")
    return next_stage, next_clarifications

def validate_tool_arguments(function_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Validate tool arguments"""
    if function_name == "send_email_diagnostic":
        name = arguments.get("name", "").strip()
        email = arguments.get("email", "").strip()
        issue = arguments.get("issue", "").strip()
        
        if not name or len(name) > 100:
            raise ValueError("Invalid name")
        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
            raise ValueError("Invalid email format")
        if not issue or len(issue) < 10 or len(issue) > 1000:
            raise ValueError("Invalid issue description")
            
        return {"name": name, "email": email, "issue": issue}
    
    elif function_name in ["measure_speed", "get_plugin_list"]:
        url = arguments.get("url", "").strip()
        if not re.match(r'^https?:\/\/.+', url):
            raise ValueError("Invalid URL format")
        return {"url": url}
    
    elif function_name == "recommend_fixes":
        category = arguments.get("category", "").strip()
        valid_categories = [
            "Performance", "Design/Layout", "Functionality", 
            "Access/Errors", "Update/Plugin", "Security/Hack", "Hosting/DNS"
        ]
        if category not in valid_categories:
            raise ValueError("Invalid category")
        return {"category": category}
    
    return arguments

def handle_tool_call(tool_call) -> Dict[str, Any]:
    """Enhanced tool call handler with validation and hardened JSON parsing"""
    function_name = tool_call.function.name

    try:
        # Safely extract and validate arguments
        raw_args = tool_call.function.arguments.strip() if tool_call.function.arguments else ""
        if not raw_args:
            raise json.JSONDecodeError("Empty tool_call.function.arguments", doc="", pos=0)

        arguments = json.loads(raw_args)
        validated_args = validate_tool_arguments(function_name, arguments)

        logger.info(f"Executing tool: {function_name}")

        # Route to the correct tool function
        if function_name == "send_email_diagnostic":
            return handle_send_email_diagnostic(validated_args)
        elif function_name == "recommend_fixes":
            return handle_recommend_fixes(validated_args)
        elif function_name == "measure_speed":
            return handle_measure_speed(validated_args)
        elif function_name == "get_plugin_list":
            return handle_get_plugin_list(validated_args)
        else:
            logger.error(f"Unknown function: {function_name}")
            return {"error": f"Unknown function: {function_name}"}

    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error in {function_name}: {str(e)}")
        return {"error": "Invalid function arguments"}
    except ValueError as e:
        logger.error(f"Validation error in {function_name}: {str(e)}")
        return {"error": str(e)}
    except Exception as e:
        logger.error(f"Unexpected error in {function_name}: {str(e)}")
        return {"error": "Tool execution failed"}

def handle_send_email_diagnostic(arguments: Dict[str, str]) -> Dict[str, Any]:
    """
    ONLY DATABASE INTERACTION: This is the ONLY function that should touch the database
    and only when actually sending the final diagnostic report
    """
    name = arguments["name"]
    email = arguments["email"]
    issue = arguments["issue"]
    
    logger.info(f"DATABASE INTERACTION: Creating user interaction record for {email}")
    
    try:
        # Create interaction record - THIS IS THE ONLY DATABASE WRITE DURING CONVERSATION
        interaction = UserInteraction.objects.create(
            name=name,
            email=email,
            issue_description=issue
        )
        
        # Generate comprehensive report
        report_content = f"""
Website Diagnostic Report for {name}

Issue Summary: {issue}

Preliminary Analysis:
Our AI diagnostic system has identified this as a priority issue requiring attention.

Recommended Action Plan:
- Immediate: Run a comprehensive site audit
- Performance: Check hosting resources and optimize loading speeds  
- Security: Ensure all plugins and themes are updated
- Content: Review and optimize images and database
- Monitoring: Set up ongoing performance tracking

Next Steps:
1. Implement the quick fixes listed above
2. Monitor your site's performance over the next 48 hours
3. Consider a professional consultation for complex issues

Need Expert Help?
Our team at TechWithWayne specializes in website optimization and troubleshooting.
Visit: https://apps.techwithwayne.com
Email: support@techwithwayne.com

This report was generated by Shirley AI on {timezone.now().strftime('%Y-%m-%d at %H:%M UTC')}.

Best regards,
Shirley - Your Website Doctor
TechWithWayne Digital Solutions
        """.strip()
        
        # Save report
        report = DiagnosticReport.objects.create(
            user_interaction=interaction,
            user_email=email,
            issue_details=issue,
            report_content=report_content
        )
        
        # Send email with error handling
        try:
            send_mail(
                subject=f'Website Diagnostic Report for {name}',
                message=report_content,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[email],
                fail_silently=False,
            )
            
            report.mark_email_sent()
            logger.info(f"DATABASE INTERACTION: Email sent successfully to {email}")
            
            return {
                "message": "Great! Your diagnostic report has been sent to your email. Check your inbox (and spam folder) in the next few minutes.",
                "success": True
            }
            
        except Exception as email_error:
            logger.error(f"Email failed to {email}: {str(email_error)}")
            return {
                "error": "I created your report but had trouble sending the email. Please check your email address and try again.",
                "success": False
            }
            
    except Exception as e:
        logger.error(f"Database error for {email}: {str(e)}")
        return {
            "error": "I'm having trouble processing your request right now. Please try again in a moment.",
            "success": False
        }

def handle_recommend_fixes(arguments: Dict[str, str]) -> Dict[str, Any]:
    """Enhanced fix recommendations - NO DATABASE DEPENDENCY"""
    category = arguments["category"]
    
    fixes_database = {
        "Performance": [
            "Optimize images: Use WebP format and implement lazy loading",
            "Minify CSS, JavaScript, and HTML files",
            "Enable browser caching with proper cache headers",
            "Implement a Content Delivery Network (CDN) like Cloudflare",
            "Upgrade hosting plan or optimize server configuration",
            "Remove unused plugins and themes",
            "Optimize database queries and clean up database"
        ],
        "Design/Layout": [
            "Test responsive design on all device sizes",
            "Fix broken images and update alt text",
            "Improve typography hierarchy and readability",
            "Ensure sufficient color contrast for accessibility",
            "Optimize layout for mobile-first experience", 
            "Test cross-browser compatibility",
            "Update outdated design elements"
        ],
        "Functionality": [
            "Debug JavaScript errors in browser console",
            "Test all forms and contact methods",
            "Verify payment processing functionality",
            "Check search functionality and filters",
            "Test user registration and login flows",
            "Validate all interactive elements",
            "Update deprecated code and libraries"
        ],
        "Access/Errors": [
            "Fix 404 errors and implement proper redirects",
            "Verify SSL certificate installation and renewal", 
            "Check DNS settings and propagation",
            "Monitor server logs for recurring errors",
            "Test website accessibility compliance",
            "Implement proper error pages",
            "Check hosting server status and uptime"
        ],
        "Update/Plugin": [
            "Update WordPress core to latest version",
            "Update all plugins and themes safely",
            "Create full website backup before updates",
            "Test updates in staging environment first",
            "Remove unused and vulnerable plugins",
            "Check plugin compatibility matrix",
            "Implement automated update monitoring"
        ],
        "Security/Hack": [
            "Install comprehensive security plugin (Wordfence/Sucuri)",
            "Change all passwords and enable 2FA",
            "Scan for malware and clean infected files",
            "Review and secure file permissions",
            "Monitor for suspicious login attempts",
            "Implement firewall rules",
            "Schedule regular security audits"
        ],
        "Hosting/DNS": [
            "Contact hosting provider for server status",
            "Verify DNS records and propagation",
            "Check domain registration and renewal dates",
            "Optimize hosting plan for current traffic",
            "Configure proper email routing",
            "Set up monitoring and alerts",
            "Consider hosting upgrade if needed"
        ]
    }
    
    recommendations = fixes_database.get(category, [
        "Contact a web developer for specialized assistance",
        "Run a comprehensive website audit",
        "Check with your hosting provider for guidance"
    ])
    
    logger.info(f"Provided {len(recommendations)} fixes for {category} (NO DATABASE)")
    
    return {
        "fixes": recommendations,
        "category": category,
        "count": len(recommendations)
    }

def handle_measure_speed(arguments: Dict[str, str]) -> Dict[str, Any]:
    """Enhanced speed measurement with caching - NO DATABASE DEPENDENCY"""
    url = arguments["url"]
    
    # Check cache first
    cache_key = f"speed_test_{hashlib.md5(url.encode()).hexdigest()}"
    cached_result = cache.get(cache_key)
    if cached_result:
        logger.info(f"Using cached speed data for {url} (NO DATABASE)")
        return cached_result
    
    try:
        # Enhanced API call with timeout
        api_url = f"https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
        params = {
            'url': url,
            'category': 'performance',
            'strategy': 'mobile'  # Mobile-first testing
        }
        
        response = requests.get(api_url, params=params, timeout=30)
        response.raise_for_status()
        
        result = response.json()
        lighthouse = result.get('lighthouseResult', {})
        
        # Extract comprehensive metrics
        metrics = {
            'performance_score': round(
                lighthouse.get('categories', {}).get('performance', {}).get('score', 0) * 100, 1
            ),
            'fcp': lighthouse.get('audits', {}).get('first-contentful-paint', {}).get('displayValue', 'N/A'),
            'lcp': lighthouse.get('audits', {}).get('largest-contentful-paint', {}).get('displayValue', 'N/A'),
            'cls': lighthouse.get('audits', {}).get('cumulative-layout-shift', {}).get('displayValue', 'N/A'),
            'tbt': lighthouse.get('audits', {}).get('total-blocking-time', {}).get('displayValue', 'N/A'),
            'fid': lighthouse.get('audits', {}).get('max-potential-fid', {}).get('displayValue', 'N/A'),
            'tested_url': url,
            'test_timestamp': timezone.now().isoformat()
        }
        
        # Add performance assessment
        score = metrics['performance_score']
        if score >= 90:
            assessment = "Excellent performance! Your site is fast."
        elif score >= 70:
            assessment = "Good performance with room for improvement."
        elif score >= 50:
            assessment = "Moderate performance. Consider optimization."
        else:
            assessment = "Poor performance. Immediate optimization needed."
        
        metrics['assessment'] = assessment
        
        # Cache result for 1 hour
        cache.set(cache_key, metrics, timeout=3600)
        
        logger.info(f"Speed test completed for {url}: {score}/100 (NO DATABASE)")
        return metrics
        
    except requests.exceptions.Timeout:
        logger.error(f"Speed test timeout for {url}")
        return {"error": "Speed test timed out. The website might be very slow or unreachable."}
    except requests.exceptions.RequestException as e:
        logger.error(f"Speed test request failed for {url}: {str(e)}")
        return {"error": "Unable to test website speed. Please check the URL and try again."}
    except Exception as e:
        logger.error(f"Speed test failed for {url}: {str(e)}")
        return {"error": "Speed test failed due to technical issues."}

def handle_get_plugin_list(arguments: Dict[str, str]) -> Dict[str, Any]:
    """Enhanced plugin detection with caching - NO DATABASE DEPENDENCY"""
    url = arguments["url"]
    
    # Check cache first
    cache_key = f"plugins_{hashlib.md5(url.encode()).hexdigest()}"
    cached_result = cache.get(cache_key)
    if cached_result:
        logger.info(f"Using cached plugin data for {url} (NO DATABASE)")
        return cached_result
    
    try:
        # Enhanced request with headers
        headers = {
            'User-Agent': 'Mozilla/5.0 (compatible; WebDoctor/1.0; +https://techwithwayne.com)'
        }
        
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        html = response.text
        
        # Enhanced plugin detection
        plugin_patterns = [
            r'/wp-content/plugins/([^/]+)/',
            r'wp-content/plugins/([^/\'"]+)',
            r'plugins/([^/\'"]+)'
        ]
        
        plugin_slugs = set()
        for pattern in plugin_patterns:
            matches = re.findall(pattern, html, re.IGNORECASE)
            plugin_slugs.update(matches)
        
        # Enhanced plugin name mapping
        slug_to_info = {
            'elementor': {'name': 'Elementor', 'type': 'Page Builder'},
            'woocommerce': {'name': 'WooCommerce', 'type': 'E-commerce'},
            'wordpress-seo': {'name': 'Yoast SEO', 'type': 'SEO'},
            'contact-form-7': {'name': 'Contact Form 7', 'type': 'Forms'},
            'jetpack': {'name': 'Jetpack', 'type': 'Security & Performance'},
            'akismet': {'name': 'Akismet', 'type': 'Spam Protection'},
            'wp-super-cache': {'name': 'WP Super Cache', 'type': 'Caching'},
            'all-in-one-seo-pack': {'name': 'All in One SEO', 'type': 'SEO'},
            'gravityforms': {'name': 'Gravity Forms', 'type': 'Forms'},
            'wpforms-lite': {'name': 'WPForms', 'type': 'Forms'},
            'google-analytics-for-wordpress': {'name': 'MonsterInsights', 'type': 'Analytics'},
            'updraftplus': {'name': 'UpdraftPlus', 'type': 'Backup'},
            'wordfence': {'name': 'Wordfence Security', 'type': 'Security'},
            'really-simple-ssl': {'name': 'Really Simple SSL', 'type': 'Security'},
            'duplicate-post': {'name': 'Duplicate Post', 'type': 'Content Management'},
        }
        
        # Build plugin list with metadata
        plugins = []
        for slug in plugin_slugs:
            if slug in slug_to_info:
                plugins.append({
                    'name': slug_to_info[slug]['name'],
                    'type': slug_to_info[slug]['type'],
                    'slug': slug
                })
            else:
                # Clean up slug for display
                display_name = slug.replace('-', ' ').replace('_', ' ').title()
                plugins.append({
                    'name': display_name,
                    'type': 'Unknown',
                    'slug': slug
                })
        
        # Sort plugins by type and name
        plugins.sort(key=lambda x: (x['type'], x['name']))
        
        result = {
            'plugins': plugins,
            'plugin_count': len(plugins),
            'scanned_url': url,
            'scan_timestamp': timezone.now().isoformat()
        }
        
        # Cache result for 6 hours
        cache.set(cache_key, result, timeout=21600)
        
        logger.info(f"Found {len(plugins)} plugins on {url} (NO DATABASE)")
        return result
        
    except requests.exceptions.Timeout:
        logger.error(f"Plugin scan timeout for {url}")
        return {"error": "Plugin scan timed out. The website might be slow to respond."}
    except requests.exceptions.RequestException as e:
        logger.error(f"Plugin scan request failed for {url}: {str(e)}")
        return {"error": "Unable to scan website. Please check the URL and try again."}
    except Exception as e:
        logger.error(f"Plugin scan failed for {url}: {str(e)}")
        return {"error": "Plugin scan failed due to technical issues."}

# In your ai_agent.py file, find the get_stage_specific_prompt function
# and update the "offered_report" section:

def get_stage_specific_prompt(stage: str, clarifications: int, category: Optional[str]) -> str:
    """Get stage-specific prompts - SESSION-BASED ONLY"""
    
    if stage == "initial":
        return f"""This user just described their website issue. DO NOT give another greeting.
Move directly to asking your FIRST clarifying question.
SESSIONS CLARIFICATIONS COUNT: {clarifications}
Ask a specific diagnostic question like: "When did you first notice this problem?" or "Does this happen on all pages?"
Respond: {{"response": "your diagnostic question", "next_stage": "clarifying", "category": null, "clarifications": 1}}"""
        
    elif stage == "clarifying":
        if clarifications == 0:
            return f"""Ask your FIRST diagnostic question. DO NOT greet again.
Examples: "When did you first notice this problem?" or "Does this happen on all pages?"
Respond: {{"response": "your question", "next_stage": "clarifying", "category": null, "clarifications": 1}}"""
        elif clarifications == 1:
            return f"""Ask your SECOND diagnostic question.
Examples: "What browser are you using?" or "Have you made recent changes?"
Respond: {{"response": "your question", "next_stage": "clarifying", "category": null, "clarifications": 2}}"""
        else:  # clarifications >= 2
            return f"""You've asked {clarifications} questions. Now summarize and offer a diagnostic report.
Example: "Based on what you've told me, this sounds like a performance issue. Would you like a free diagnostic report?"
Respond: {{"response": "summary + report offer", "next_stage": "offered_report", "category": "Performance", "clarifications": {clarifications}}}"""
            
    elif stage == "offered_report":
        return f"""The user hasn't agreed to the report yet. Ask if they want it.
Example: "Would you like me to send you a free diagnostic report?"
Keep it brief and focused on getting their agreement.
Respond: {{"response": "report offer", "next_stage": "offered_report", "category": "appropriate_category", "clarifications": {clarifications}}}"""
        
    elif stage == "hybrid_closing":
        return f"""The user has AGREED to receive the report. Now handle the form process.
        
Give a brief, encouraging message about the form:
- "Perfect! Please fill out the form that just appeared so I can send your report."
- "Great! Just fill in your details in the form below and I'll get that report right over to you."
- "Excellent! The form is ready - once you fill it out, I'll send your personalized diagnostic report."

Keep it brief, positive, and focused on the form that will appear.
Respond: {{"response": "brief form encouragement", "next_stage": "hybrid_closing", "category": "appropriate_category", "clarifications": {clarifications}}}"""
        
    else:
        return "Continue conversation naturally based on session state only."

def convert_plain_text_to_json(text: str, stage: str, category: Optional[str], clarifications: int) -> Dict[str, Any]:
    """Convert plain text response to valid JSON format - SESSION-BASED"""
    logger.warning(f"Converting plain text to JSON (SESSION-BASED): {text[:100]}...")
    
    # Clean the text
    cleaned_text = text.strip().replace('"', '\\"').replace('\n', ' ').replace('\r', ' ')
    
    # Force proper stage progression based on SESSION STATE ONLY
    next_stage, next_clarifications = force_stage_logic(stage, clarifications, "", cleaned_text)
    
    # Detect category from content if not set
    detected_category = category
    if not detected_category:
        if any(phrase in cleaned_text.lower() for phrase in ["slow", "loading", "performance", "speed"]):
            detected_category = "Performance"
        elif any(phrase in cleaned_text.lower() for phrase in ["error", "404", "500", "broken", "not working"]):
            detected_category = "Access/Errors"
        elif any(phrase in cleaned_text.lower() for phrase in ["mobile", "responsive", "layout", "design"]):
            detected_category = "Design/Layout"
    
    json_response = {
        "response": cleaned_text,
        "next_stage": next_stage,
        "category": detected_category,
        "clarifications": next_clarifications
    }
    
    logger.info(f"SESSION-BASED JSON conversion: {json_response}")
    return json_response

def extract_json_from_text(text: str) -> Dict[str, Any]:
    """Extract JSON from text that might contain markdown or other formatting"""
    if not text:
        raise json.JSONDecodeError("Empty text", doc="", pos=0)
    
    # Remove common markdown formatting
    text = text.strip()
    
    # Remove markdown code blocks if present
    if text.startswith('```json'):
        text = text[7:]
    if text.startswith('```'):
        text = text[3:]
    if text.endswith('```'):
        text = text[:-3]
    
    text = text.strip()
    
    # Try to find JSON object boundaries
    start_idx = text.find('{')
    if start_idx == -1:
        raise json.JSONDecodeError("No JSON object found", doc=text, pos=0)
    
    # Find the matching closing brace
    brace_count = 0
    end_idx = -1
    
    for i, char in enumerate(text[start_idx:], start_idx):
        if char == '{':
            brace_count += 1
        elif char == '}':
            brace_count -= 1
            if brace_count == 0:
                end_idx = i + 1
                break
    
    if end_idx == -1:
        raise json.JSONDecodeError("Incomplete JSON object", doc=text, pos=start_idx)
    
    json_text = text[start_idx:end_idx]
    return json.loads(json_text)

def validate_assistant_response(parsed_json: Dict[str, Any], input_clarifications: int) -> Dict[str, Any]:
    """Validate and sanitize assistant response - SESSION-BASED"""
    required_fields = ['response', 'next_stage', 'category', 'clarifications']
    
    for field in required_fields:
        if field not in parsed_json:
            raise ValueError(f"Missing required field: {field}")
    
    # Validate response field
    if not isinstance(parsed_json['response'], str) or not parsed_json['response'].strip():
        raise ValueError("Response must be a non-empty string")
    
    # Fix invalid stage values
    valid_stages = ['initial', 'clarifying', 'offered_report', 'hybrid_closing']
    if parsed_json['next_stage'] not in valid_stages:
        if 'stage_will_be_set_by_system' in str(parsed_json['next_stage']):
            logger.warning("Fixed 'stage_will_be_set_by_system' error - using session-based logic")
            parsed_json['next_stage'] = 'clarifying'
        else:
            logger.warning(f"Invalid stage: {parsed_json['next_stage']}, defaulting to 'clarifying'")
            parsed_json['next_stage'] = 'clarifying'
    
    # Validate category
    valid_categories = [
        'Performance', 'Design/Layout', 'Functionality', 
        'Access/Errors', 'Update/Plugin', 'Security/Hack', 'Hosting/DNS', None
    ]
    if parsed_json['category'] not in valid_categories:
        logger.warning(f"Invalid category: {parsed_json['category']}, setting to None")
        parsed_json['category'] = None
    
    # Keep clarifications consistent with session state
    parsed_json['clarifications'] = input_clarifications
    
    return parsed_json

def get_agent_response(history, stage, category, clarifications, lang='en', request=None):
    """
    Main agent response function - COMPLETELY SESSION-BASED
    NO DATABASE DEPENDENCIES during conversation flow
    """
    start_time = time.time()
    processing_time = 0  # ✅ Initialize to prevent UnboundLocalError
    assistant_msg = {}  # ✅ Initialize to prevent UnboundLocalError

    try:
        assistant_id = get_assistant_id()
        client = get_openai_client()

        # Get the latest user message for stage logic
        user_message = ""
        if history:
            user_message = history[-1].get("content", "")

        logger.info(f"SESSION-BASED PROCESSING: stage={stage}, clarifications={clarifications}, history_length={len(history)}")

        # Create thread
        thread = client.beta.threads.create()

        # Build session-based system message
        stage_prompt = get_stage_specific_prompt(stage, clarifications, category)
        
        system_message = f"""SESSION-BASED CONVERSATION (NO DATABASE HISTORY)

CURRENT SESSION STATE:
- Stage: {stage}
- Session Clarifications: {clarifications}
- Session History Length: {len(history)}

This is a fresh session. You have NO access to previous conversations or database records.
Every conversation starts completely new. You MUST ask clarifying questions regardless.

TASK: {stage_prompt}

CRITICAL: Respond ONLY with valid JSON:
{{"response": "your message", "next_stage": "proper_stage", "category": "category_or_null", "clarifications": {clarifications}}}

NEVER use "stage_will_be_set_by_system"."""
        
        # Add conversation history (session-based only)
        for msg in history[-8:]:  # Limit to last 8 messages in this session
            if not msg.get("content", "").strip():
                continue
            client.beta.threads.messages.create(
                thread_id=thread.id,
                role=msg.get("role", "user"),
                content=msg["content"][:1500]  # Limit length
            )

        # Add system message
        client.beta.threads.messages.create(
            thread_id=thread.id,
            role="user", 
            content=system_message
        )

        # Create run
        run = client.beta.threads.runs.create(
            thread_id=thread.id,
            assistant_id=assistant_id,
            tool_choice="auto",
            response_format={"type": "json_object"}
        )

        # Poll run with timeout
        max_polls = 50
        poll_count = 0

        while run.status in ['queued', 'in_progress', 'requires_action'] and poll_count < max_polls:
            time.sleep(2)
            poll_count += 1

            run = client.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)

            if run.status == 'requires_action':
                tool_outputs = []
                for tool_call in run.required_action.submit_tool_outputs.tool_calls:
                    output = handle_tool_call(tool_call)
                    tool_outputs.append({
                        "tool_call_id": tool_call.id,
                        "output": json.dumps(output)
                    })
                run = client.beta.threads.runs.submit_tool_outputs(
                    thread_id=thread.id,
                    run_id=run.id,
                    tool_outputs=tool_outputs
                )

        # Handle timeout
        if poll_count >= max_polls:
            logger.error("Assistant run timed out")
            return create_fallback_response("I'm taking longer than usual. Please try again.", stage, category, clarifications)

        if run.status == 'failed':
            logger.error(f"Assistant run failed: {run.last_error}")
            return create_fallback_response("I'm having technical difficulties. Please try again.", stage, category, clarifications)

        # Get response
        messages = client.beta.threads.messages.list(thread_id=thread.id)
        if not messages.data:
            logger.error("No assistant messages returned")
            return create_fallback_response("I didn't get a proper response. Please try again.", stage, category, clarifications)

        # Parse response with multiple fallback strategies
        try:
            message_obj = messages.data[0]
            if not message_obj.content or not message_obj.content[0].text:
                raise ValueError("No content in assistant message")
            
            raw_text = message_obj.content[0].text.value.strip()
            logger.debug(f"Raw session-based response: {raw_text[:200]}...")

            assistant_msg = None
            
            # Try direct JSON parsing
            try:
                assistant_msg = json.loads(raw_text)
                logger.info("Session-based JSON parsed successfully")
            except json.JSONDecodeError:
                pass
            
            # Try extracting JSON from formatted text
            if assistant_msg is None:
                try:
                    assistant_msg = extract_json_from_text(raw_text)
                    logger.info("Session-based JSON extracted successfully")
                except json.JSONDecodeError:
                    pass
            
            # Final fallback: convert plain text
            if assistant_msg is None:
                logger.warning("Session-based JSON parsing failed, using fallback conversion")
                assistant_msg = convert_plain_text_to_json(raw_text, stage, category, clarifications)

            # Validate response structure
            assistant_msg = validate_assistant_response(assistant_msg, clarifications)

            # ENFORCE session-based stage logic (override AI decisions)
            forced_stage, forced_clarifications = force_stage_logic(stage, clarifications, user_message, assistant_msg["response"])
            assistant_msg["next_stage"] = forced_stage
            assistant_msg["clarifications"] = forced_clarifications

            # Session-based safety check: prevent early report offering
            if stage in ["initial", "clarifying"] and clarifications < 2:
                forbidden_phrases = ["diagnostic report", "send you", "free report", "email you", "would you like a report"]
                if any(phrase in assistant_msg["response"].lower() for phrase in forbidden_phrases):
                    logger.warning("SESSION SAFETY: Assistant mentioned report too early - overriding")
                    
                    # Provide appropriate clarifying question based on session count
                    if clarifications == 0:
                        assistant_msg["response"] = "I understand you're having an issue. When did you first notice this problem?"
                    elif clarifications == 1:
                        assistant_msg["response"] = "Thanks for that information. Does this issue happen on all pages, or just specific ones?"
                    
                    assistant_msg["category"] = None
                    assistant_msg["next_stage"] = "clarifying"

        except Exception as e:
            logger.error(f"Session-based response processing failed: {str(e)}")
            return create_fallback_response("I had trouble processing my response. Please try again.", stage, category, clarifications)

        response_text = assistant_msg.get("response", "").strip()
        if not response_text:
            logger.error("Empty response from assistant")
            return create_fallback_response("I couldn't generate a proper response. Please try again.", stage, category, clarifications)

        typing_delay = max(3, min(8, len(response_text) // 25))
        processing_time = time.time() - start_time
        
        logger.info(f"SESSION-BASED Response: {processing_time:.2f}s - {stage} -> {assistant_msg.get('next_stage')} (session clarifications: {clarifications} -> {assistant_msg.get('clarifications')})")

        return {
            "response": response_text,
            "next_stage": assistant_msg.get("next_stage", stage),
            "category": assistant_msg.get("category") if assistant_msg.get("category") != "None" else None,
            "clarifications": assistant_msg.get("clarifications", clarifications),
            "typing_delay": typing_delay,
            "processing_time": processing_time
        }

    except Exception as e:
        processing_time = time.time() - start_time
        logger.error(f"Session-based agent response failed after {processing_time:.2f}s: {str(e)}")
        return create_fallback_response("I'm experiencing technical difficulties. Please try again.", stage, category, clarifications)

def create_fallback_response(message, stage, category, clarifications):
    """Create fallback response for errors - SESSION-BASED"""
    return {
        "response": message,
        "next_stage": stage,
        "category": category,
        "clarifications": clarifications,
        "typing_delay": 4,
        "processing_time": 0
    }