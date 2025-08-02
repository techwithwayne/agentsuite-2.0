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
    
    def __new__(cls):import os
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
    """Simple assistant creation - let Python handle the stage logic"""
    client = get_openai_client()
    
    try:
        assistant = client.beta.assistants.create(
            name="Shirley - WebDoctor AI",
            model="gpt-4o",
            instructions="""
You are Shirley, a friendly website doctor. 

STRICTLY follow the current stage task provided in the system message. Do not deviate from it, even if you think it would be helpful. The Python system controls stages—your job is only to generate the response text as instructed for the current stage.

You MUST respond with valid JSON in this format:
{
    "response": "your conversational message here",
    "next_stage": "stage_will_be_set_by_system",
    "category": "Performance|Design/Layout|Functionality|Access/Errors|Update/Plugin|Security/Hack|Hosting/DNS|null",
    "clarifications": the exact value provided in the system message CLARIFICATIONS ASKED - DO NOT CHANGE IT
}

Be conversational, empathetic, and helpful WITHIN the stage task limits. Ask good diagnostic questions ONLY when instructed. DO NOT mention or offer reports unless the stage task explicitly says to.
Repeat: DO NOT offer reports until instructed in the task for clarifications >= 3. DO NOT CHANGE THE CLARIFICATIONS VALUE; USE EXACTLY THE VALUE GIVEN IN "CLARIFICATIONS ASKED".
            """,
            tools=SHIRLEY_TOOLS,
            metadata={"project": "webdoctor", "version": "3.0"},
            temperature=0.0,
            response_format={"type": "json_object"}
        )
        
        return assistant.id
        
    except Exception as e:
        logger.error(f"Failed to create assistant: {str(e)}")
        raise ValueError(f"Could not create OpenAI assistant: {str(e)}")

def force_stage_logic(stage: str, clarifications: int, user_message: str, assistant_response: str) -> tuple[str, int]:
    """FORCE the correct conversation stage logic in Python"""
    user_msg_lower = user_message.lower()
    response_lower = assistant_response.lower()
    
    logger.info(f"STAGE LOGIC: Current stage={stage}, clarifications={clarifications}")
    
    # FORCED STAGE PROGRESSION RULES - Enforce at least 3 clarifying questions
    if stage == "initial":
        # After initial greeting, ALWAYS go to clarifying
        next_stage = "clarifying"
        next_clarifications = 0
        logger.info("FORCED: initial -> clarifying")
        
    elif stage == "clarifying":
        # Stay in clarifying until we have at least 3 questions asked
        if clarifications < 3:
            next_stage = "clarifying"
            next_clarifications = clarifications + 1
            logger.info(f"FORCED: staying in clarifying, incrementing to {next_clarifications}")
        else:
            # After 3+ clarifications, move to offered_report
            next_stage = "offered_report"
            next_clarifications = clarifications
            logger.info("FORCED: clarifying -> offered_report")
            
    elif stage == "offered_report":
        # Check if user said yes to report
        yes_words = ["yes", "sure", "okay", "ok", "please", "send", "absolutely", "definitely", "yeah"]
        if any(word in user_msg_lower for word in yes_words):
            # User said yes, stay in offered_report to collect details
            next_stage = "offered_report"
            next_clarifications = clarifications
            logger.info("FORCED: user said yes, staying in offered_report")
        else:
            # User said no or something else, stay in offered_report
            next_stage = "offered_report"  
            next_clarifications = clarifications
            logger.info("FORCED: staying in offered_report")
            
    elif stage == "hybrid_closing":
        # Stay in closing
        next_stage = "hybrid_closing"
        next_clarifications = clarifications
        logger.info("FORCED: staying in hybrid_closing")
        
    else:
        # Default fallback
        next_stage = "clarifying"
        next_clarifications = clarifications
        logger.info("FORCED: fallback to clarifying")
    
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
    """Enhanced email diagnostic handler"""
    name = arguments["name"]
    email = arguments["email"]
    issue = arguments["issue"]
    
    try:
        # Create interaction record
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
            logger.info(f"Email sent successfully to {email}")
            
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
    """Enhanced fix recommendations"""
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
    
    logger.info(f"Provided {len(recommendations)} fixes for {category}")
    
    return {
        "fixes": recommendations,
        "category": category,
        "count": len(recommendations)
    }

def handle_measure_speed(arguments: Dict[str, str]) -> Dict[str, Any]:
    """Enhanced speed measurement with caching"""
    url = arguments["url"]
    
    # Check cache first
    cache_key = f"speed_test_{hashlib.md5(url.encode()).hexdigest()}"
    cached_result = cache.get(cache_key)
    if cached_result:
        logger.info(f"Using cached speed data for {url}")
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
        
        logger.info(f"Speed test completed for {url}: {score}/100")
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
    """Enhanced plugin detection with caching"""
    url = arguments["url"]
    
    # Check cache first
    cache_key = f"plugins_{hashlib.md5(url.encode()).hexdigest()}"
    cached_result = cache.get(cache_key)
    if cached_result:
        logger.info(f"Using cached plugin data for {url}")
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
        
        logger.info(f"Found {len(plugins)} plugins on {url}")
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

def get_stage_specific_prompt(stage: str, clarifications: int, category: Optional[str]) -> str:
    """Get stage-specific prompts to force proper behavior"""
    
    if stage == "initial":
        return """Ask what's wrong with their website. Be friendly and move to diagnostic questions.
Example output:
{"response": "Hey there! I'm Shirley, your website's doctor. What seems to be the issue today?", "next_stage": "stage_will_be_set_by_system", "category": null, "clarifications": 0}"""
        
    elif stage == "clarifying":
        base_examples = """
Examples of questions:
- 'When did you first notice this problem?'
- 'Does this happen on all pages or just specific ones?'
- 'What browser are you using?'
- 'Have you made any recent changes to your website?'
- 'Is your site WordPress-based or another platform?'
"""
        if clarifications == 0:
            return f"""Ask ONE specific diagnostic question about their website issue. DO NOT offer any reports yet. DO NOT mention reports at all. DO NOT summarize or categorize yet. Just ask diagnostic questions. Repeat: NO REPORTS UNTIL AFTER EXACTLY 3 QUESTIONS. {base_examples}
STRICTLY FOLLOW THIS. Example output:
{{"response": "I'm sorry to hear about the issue. When did you first notice your site being slow?", "next_stage": "stage_will_be_set_by_system", "category": null, "clarifications": 0}}"""
        elif clarifications == 1:
            return f"""Ask ONE follow-up diagnostic question to better understand their issue. DO NOT offer any reports yet. DO NOT mention reports at all. DO NOT summarize or categorize yet. Repeat: NO REPORTS UNTIL AFTER EXACTLY 3 QUESTIONS. {base_examples}
STRICTLY FOLLOW THIS. Example output:
{{"response": "Thanks for that detail. Does this slowness happen on mobile devices, desktop, or both?", "next_stage": "stage_will_be_set_by_system", "category": null, "clarifications": 1}}"""
        elif clarifications == 2:
            return f"""Ask ONE more diagnostic question to gather more details. DO NOT offer any reports yet. DO NOT mention reports at all. DO NOT summarize or categorize yet. Repeat: NO REPORTS UNTIL AFTER EXACTLY 3 QUESTIONS. {base_examples}
STRICTLY FOLLOW THIS. Example output:
{{"response": "Got it. Have you made any recent changes to your website that might be causing this?", "next_stage": "stage_will_be_set_by_system", "category": null, "clarifications": 2}}"""
        else:  # clarifications >= 3
            return f"""Now summarize the issue based on all gathered information and identify it as a {category or 'website'} problem. Set category to the matching one. Then ask if they would like a free diagnostic report. DO NOT ask for name/email yet.
Example output:
{{"response": "From what you've described, it sounds like a performance issue with slow loading times. Would you like me to send you a free diagnostic report?", "next_stage": "stage_will_be_set_by_system", "category": "Performance", "clarifications": 3}}"""
            
    elif stage == "offered_report":
        return """If the user has not yet agreed to the report, ask if they want a diagnostic report. If they said yes, ask for their name and email to send it. DO NOT send the report yet—use the tool for that.
Example output if not agreed yet:
{"response": "Would you like a free diagnostic report emailed to you?", "next_stage": "stage_will_be_set_by_system", "category": "Performance", "clarifications": 3}
Example output if agreed:
{"response": "Great! To send your report, what's your name and email address?", "next_stage": "stage_will_be_set_by_system", "category": "Performance", "clarifications": 3}"""
        
    elif stage == "hybrid_closing":
        return """Thank them and offer additional help or other services.
Example output:
{"response": "You're welcome! If you need more help, feel free to ask.", "next_stage": "stage_will_be_set_by_system", "category": "Performance", "clarifications": 3}"""
        
    else:
        return "Continue the conversation naturally."

def convert_plain_text_to_json(text: str, stage: str, category: Optional[str], clarifications: int) -> Dict[str, Any]:
    """BULLETPROOF: Convert any plain text response to valid JSON format"""
    logger.warning(f"Converting plain text to JSON: {text[:100]}...")
    
    # Clean the text
    cleaned_text = text.strip()
    
    # Escape quotes in the text for JSON
    escaped_text = cleaned_text.replace('"', '\\"').replace('\n', ' ').replace('\r', ' ')
    
    # FORCE the stage using Python logic instead of trusting the assistant
    next_stage, next_clarifications = force_stage_logic(stage, clarifications, "", escaped_text)
    
    # Detect category from content
    detected_category = category
    if any(phrase in cleaned_text.lower() for phrase in ["slow", "loading", "performance", "speed"]):
        detected_category = "Performance"
    elif any(phrase in cleaned_text.lower() for phrase in ["error", "404", "500", "broken", "not working"]):
        detected_category = "Access/Errors"
    elif any(phrase in cleaned_text.lower() for phrase in ["mobile", "responsive", "layout", "design"]):
        detected_category = "Design/Layout"
    
    # Create valid JSON structure
    json_response = {
        "response": escaped_text,
        "next_stage": next_stage,
        "category": detected_category,
        "clarifications": next_clarifications
    }
    
    logger.info(f"Successfully converted plain text to JSON: {json_response}")
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
    """Validate and sanitize assistant response"""
    required_fields = ['response', 'next_stage', 'category', 'clarifications']
    
    for field in required_fields:
        if field not in parsed_json:
            raise ValueError(f"Missing required field: {field}")
    
    # Validate response field
    if not isinstance(parsed_json['response'], str) or not parsed_json['response'].strip():
        raise ValueError("Response must be a non-empty string")
    
    # Validate next_stage
    valid_stages = ['initial', 'clarifying', 'offered_report', 'hybrid_closing']
    if parsed_json['next_stage'] not in valid_stages:
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
    
    # Override clarifications to match input value
    if parsed_json['clarifications'] != input_clarifications:
        logger.warning(f"Assistant set clarifications={parsed_json['clarifications']}, overriding to input value={input_clarifications}")
        parsed_json['clarifications'] = input_clarifications
    
    return parsed_json

def get_agent_response(history, stage, category, clarifications, lang='en', request=None):
    """FORCED STAGE LOGIC main agent response function"""
    start_time = time.time()

    try:
        # Adjust stage for first user message after greeting
        if stage == "initial" and history and history[-1]["role"] == "user":
            stage = "clarifying"
            clarifications = 0
            logger.info("Adjusted stage to clarifying for first user message")

        assistant_id = get_assistant_id()
        client = get_openai_client()

        # Get the latest user message for stage logic
        user_message = ""
        if history:
            user_message = history[-1].get("content", "")

        # Create thread with timeout
        thread = client.beta.threads.create()

        # STAGE-SPECIFIC SYSTEM MESSAGE
        stage_prompt = get_stage_specific_prompt(stage, clarifications, category)
        
        system_message = f"""You MUST respond with VALID JSON ONLY. 

        CURRENT STAGE: {stage}
        CLARIFICATIONS ASKED: {clarifications}
        
        YOUR TASK FOR THIS STAGE: {stage_prompt}
        
        REQUIRED FORMAT:
        {{"response": "your message", "next_stage": "will_be_overridden", "category": "category_or_null", "clarifications": {clarifications}}}
        
        NO PLAIN TEXT ALLOWED. JSON ONLY. STRICTLY OUTPUT JSON ONLY. Follow the example format exactly."""
        
        # Add history first
        for msg in history[-10:]:  # Limit history to last 10 messages
            if not msg.get("content", "").strip():
                continue

            client.beta.threads.messages.create(
                thread_id=thread.id,
                role=msg.get("role", "user"),
                content=msg["content"][:2000]  # Limit message length
            )

        # Add system message last
        client.beta.threads.messages.create(
            thread_id=thread.id,
            role="user", 
            content=system_message
        )

        # Create run with enforced JSON format
        run = client.beta.threads.runs.create(
            thread_id=thread.id,
            assistant_id=assistant_id,
            tool_choice="auto",
            response_format={"type": "json_object"}  # Force JSON
        )

        # Poll run with timeout protection
        max_polls = 60  # 60 * 2 seconds = 2 minutes max
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

        # Check for timeout
        if poll_count >= max_polls:
            logger.error("Assistant run timed out")
            return create_fallback_response("I'm taking longer than usual to respond. Please try again.", stage, category, clarifications)

        if run.status == 'failed':
            logger.error(f"Assistant run failed: {run.last_error}")
            return create_fallback_response("I'm having technical difficulties. Please try again in a moment.", stage, category, clarifications)

        messages = client.beta.threads.messages.list(thread_id=thread.id)

        if not messages.data:
            logger.error("No assistant messages returned")
            return create_fallback_response("I didn't receive a proper response. Please try again.", stage, category, clarifications)

        # BULLETPROOF JSON PARSING WITH ULTIMATE FALLBACK
        try:
            message_obj = messages.data[0]
            if not message_obj.content:
                raise ValueError("No content in assistant message")
            
            content_obj = message_obj.content[0]
            if not hasattr(content_obj, 'text') or not content_obj.text:
                raise ValueError("No text content in assistant message")
            
            raw_text = content_obj.text.value.strip()
            if not raw_text:
                raise ValueError("Empty assistant message content")

            logger.debug(f"Raw assistant response: {raw_text[:200]}...")

            # BULLETPROOF PARSING STRATEGIES
            assistant_msg = None
            parsing_errors = []
            
            # Strategy 1: Direct JSON parsing
            try:
                assistant_msg = json.loads(raw_text)
                logger.info("JSON parsed successfully with direct parsing")
            except json.JSONDecodeError as e:
                parsing_errors.append(f"Direct parsing: {str(e)}")
            
            # Strategy 2: Extract JSON from formatted text
            if assistant_msg is None:
                try:
                    assistant_msg = extract_json_from_text(raw_text)
                    logger.info("JSON parsed successfully with extraction")
                except json.JSONDecodeError as e:
                    parsing_errors.append(f"Extraction parsing: {str(e)}")
            
            # Strategy 3: Try to find and parse the first valid JSON object
            if assistant_msg is None:
                try:
                    import re
                    json_match = re.search(r'\{.*\}', raw_text, re.DOTALL)
                    if json_match:
                        assistant_msg = json.loads(json_match.group(0))
                        logger.info("JSON parsed successfully with pattern matching")
                    else:
                        raise json.JSONDecodeError("No JSON pattern found", doc=raw_text, pos=0)
                except json.JSONDecodeError as e:
                    parsing_errors.append(f"Pattern parsing: {str(e)}")
            
            # ULTIMATE FALLBACK: Convert plain text to JSON
            if assistant_msg is None:
                logger.error(f"All JSON parsing strategies failed: {parsing_errors}")
                logger.error(f"Raw response was: {raw_text}")
                logger.warning("USING ULTIMATE FALLBACK: Converting plain text to JSON")
                
                assistant_msg = convert_plain_text_to_json(raw_text, stage, category, clarifications)
                logger.info("Successfully converted plain text to JSON using fallback")

            # Validate the parsed JSON structure
            assistant_msg = validate_assistant_response(assistant_msg, clarifications)

            # FORCE THE CORRECT STAGE LOGIC IN PYTHON (override assistant's stage)
            forced_stage, forced_clarifications = force_stage_logic(stage, clarifications, user_message, assistant_msg["response"])
            assistant_msg["next_stage"] = forced_stage
            assistant_msg["clarifications"] = forced_clarifications

            # Enhanced safety check for early report mentions - enforce up to 3
            logger.info("Entering safety check: stage={}, clarifications={}, response={}".format(stage, clarifications, assistant_msg["response"]))
            if stage in ["initial", "clarifying"] and clarifications < 3:
                forbidden_phrases = ["diagnostic report", "send you", "free report", "email you", "report"]
                if any(phrase in assistant_msg["response"].lower() for phrase in forbidden_phrases):
                    logger.warning("Assistant mentioned report too early—overriding response")
                    if clarifications == 0:
                        assistant_msg["response"] = "I'm sorry to hear about the issue. When did you first notice your site being slow?"
                    elif clarifications == 1:
                        assistant_msg["response"] = "Thanks for that detail. Does this slowness happen on mobile devices, desktop, or both?"
                    elif clarifications == 2:
                        assistant_msg["response"] = "Got it. Have you made any recent changes to your website that might be causing this?"
                    assistant_msg["category"] = None
                    assistant_msg["clarifications"] = clarifications  # Preserve current count
                    logger.info("Overriding response to: {}".format(assistant_msg["response"]))

        except (ValueError, KeyError, IndexError, AttributeError) as e:
            logger.error(f"Message processing failed: {str(e)}")
            return create_fallback_response("I had trouble processing my response. Please try again.", stage, category, clarifications)

        response_text = assistant_msg.get("response", "")
        if not response_text.strip():
            logger.error("Empty response from assistant")
            return create_fallback_response("I couldn't generate a proper response. Please try again.", stage, category, clarifications)

        typing_delay = max(3, min(8, len(response_text) // 25))

        processing_time = time.time() - start_time
        logger.info(f"Generated response in {processing_time:.2f}s - Stage: {stage} -> {assistant_msg.get('next_stage', stage)}")

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
        logger.error(f"Agent response failed after {processing_time:.2f}s: {str(e)}")
        return create_fallback_response("I'm experiencing technical difficulties. Please try again.", stage, category, clarifications)


def create_fallback_response(message, stage, category, clarifications):
    """Create fallback response for errors"""
    return {
        "response": message,
        "next_stage": stage,
        "category": category,
        "clarifications": clarifications,
        "typing_delay": 4,
        "processing_time": 0
    }