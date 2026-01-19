"""
Dot Traffic 2.0 - Connect
Route registry, email templates, downstream calls to workers and PA Postman
"""

import os
import httpx

# ===================
# CONFIG
# ===================

PA_POSTMAN_URL = os.environ.get('PA_POSTMAN_URL', '')

TIMEOUT = 30.0

# Logo for email footer
LOGO_URL = "https://raw.githubusercontent.com/MGhunch/dot-hub/main/images/ai2-logo.png"


# ===================
# ROUTE REGISTRY
# ===================

ROUTES = {
    "file": {
        "endpoint": "https://dot-file.up.railway.app/file",
        "status": "testing",  # live | testing | not_built
    },
    "update": {
        "endpoint": "https://dot-update.up.railway.app/process",
        "status": "not_built",
    },
    "triage": {
        "endpoint": "https://dot-triage.up.railway.app/process",
        "status": "not_built",
    },
    "incoming": {
        "endpoint": "https://dot-incoming.up.railway.app/process",
        "status": "not_built",
    },
    "wip": {
        "endpoint": "https://dot-wip.up.railway.app/process",
        "status": "not_built",
    },
    "todo": {
        "endpoint": "https://dot-todo.up.railway.app/process",
        "status": "not_built",
    },
    "tracker": {
        "endpoint": "https://dot-tracker.up.railway.app/process",
        "status": "not_built",
    },
    "work-to-client": {
        "endpoint": "https://dot-update.up.railway.app/process",
        "status": "not_built",
    },
    "feedback": {
        "endpoint": "https://dot-update.up.railway.app/process",
        "status": "not_built",
    },
    "clarify": {
        "endpoint": "PA_POSTMAN",
        "status": "testing",
    },
    "confirm": {
        "endpoint": "PA_POSTMAN",
        "status": "testing",
    },
    "answer": {
        "endpoint": "PA_POSTMAN",
        "status": "testing",
    },
}


# ===================
# HELPER: GET FIRST NAME
# ===================

def _get_first_name(sender_name):
    """Extract first name from full name, default to 'there'"""
    if not sender_name:
        return "there"
    # Take first word, clean it up
    first = sender_name.split()[0] if sender_name else "there"
    # Remove any non-alpha characters
    first = ''.join(c for c in first if c.isalpha())
    return first if first else "there"


def _format_email_trail(sender_name, sender_email, subject, received_datetime, original_content):
    """Format the original email as a trail below Dot's response"""
    if not original_content:
        return ""
    
    # Format the date nicely if we have it
    date_str = ""
    if received_datetime:
        try:
            from datetime import datetime
            if 'T' in received_datetime:
                dt = datetime.fromisoformat(received_datetime.replace('Z', '+00:00'))
                date_str = dt.strftime('%a %d %b %Y at %I:%M %p')
            else:
                date_str = received_datetime
        except:
            date_str = received_datetime
    
    return f"""
<div style="margin-top: 32px; padding-top: 16px; border-top: 1px solid #eee;">
  <p style="font-size: 13px; color: #666; margin: 0 0 12px 0;">
    <strong>From:</strong> {sender_name or 'Unknown'} &lt;{sender_email or ''}&gt;<br>
    <strong>Sent:</strong> {date_str}<br>
    <strong>Subject:</strong> {subject or '(no subject)'}
  </p>
  <div style="font-size: 14px; color: #666;">
    {original_content}
  </div>
</div>
"""


# ===================
# EMAIL WRAPPER & FOOTER
# ===================

def _email_wrapper(content, sender_name=None, original_email=None):
    """Wrap email content with consistent styling and footer
    
    Args:
        content: The main email body HTML
        sender_name: Sender's name for greeting
        original_email: Dict with original email data for trail (optional)
            - senderName, senderEmail, subject, receivedDateTime, content
    """
    first_name = _get_first_name(sender_name)
    
    # Format email trail if we have original email data
    email_trail = ""
    if original_email and original_email.get('content'):
        email_trail = _format_email_trail(
            sender_name=original_email.get('senderName', ''),
            sender_email=original_email.get('senderEmail', ''),
            subject=original_email.get('subject', ''),
            received_datetime=original_email.get('receivedDateTime', ''),
            original_content=original_email.get('content', '')
        )
    
    return f"""<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 17px; line-height: 1.6; color: #333;">

<p style="margin: 0 0 20px 0;">Hey {first_name},</p>

{content}

<table cellpadding="0" cellspacing="0" border="0" width="100%" style="margin-top: 32px; border-top: 1px solid #eee; padding-top: 16px;">
  <tr>
    <td style="vertical-align: middle; padding-right: 12px;" width="60">
      <img src="{LOGO_URL}" alt="hai2" width="54" height="34" style="display: block;">
    </td>
    <td style="vertical-align: middle; font-size: 13px; color: #999;">
      Dot is a robot, but there's humans in the loop.
    </td>
  </tr>
</table>

{email_trail}

</div>"""


def _success_box(title, subtitle):
    """Green success detail box with tick"""
    return f"""<table cellpadding="0" cellspacing="0" border="0" width="100%" style="margin-bottom: 20px;">
  <tr>
    <td style="background: #f0fdf4; border-radius: 8px; padding: 16px; border-left: 4px solid #22c55e;">
      <table cellpadding="0" cellspacing="0" border="0" width="100%">
        <tr>
          <td width="32" style="vertical-align: top; padding-right: 12px;">
            <div style="width: 26px; height: 26px; background: #22c55e; border-radius: 50%; text-align: center; line-height: 26px;">
              <span style="color: white; font-size: 15px;">✓</span>
            </div>
          </td>
          <td style="vertical-align: top;">
            <div style="font-weight: 600; color: #333; margin-bottom: 2px; font-size: 17px;">{title}</div>
            <div style="font-size: 15px; color: #666;">{subtitle}</div>
          </td>
        </tr>
      </table>
    </td>
  </tr>
</table>"""


def _failure_box(title, subtitle):
    """Red failure detail box with X"""
    return f"""<table cellpadding="0" cellspacing="0" border="0" width="100%" style="margin-bottom: 20px;">
  <tr>
    <td style="background: #fef2f2; border-radius: 8px; padding: 16px; border-left: 4px solid #ef4444;">
      <table cellpadding="0" cellspacing="0" border="0" width="100%">
        <tr>
          <td width="32" style="vertical-align: top; padding-right: 12px;">
            <div style="width: 26px; height: 26px; background: #ef4444; border-radius: 50%; text-align: center; line-height: 26px;">
              <span style="color: white; font-size: 15px;">✕</span>
            </div>
          </td>
          <td style="vertical-align: top;">
            <div style="font-weight: 600; color: #333; margin-bottom: 2px; font-size: 17px;">{title}</div>
            <div style="font-size: 15px; color: #666;">{subtitle}</div>
          </td>
        </tr>
      </table>
    </td>
  </tr>
</table>"""


def _info_box(content):
    """Grey info box for answers/data"""
    return f"""<table cellpadding="0" cellspacing="0" border="0" width="100%" style="margin-bottom: 20px;">
  <tr>
    <td style="background: #f5f5f5; border-radius: 8px; padding: 16px; border-left: 4px solid #ED1C24;">
      <div style="font-size: 17px; color: #333; line-height: 1.6;">{content}</div>
    </td>
  </tr>
</table>"""


# ===================
# EMAIL TEMPLATES (for clarify/confirm)
# ===================

EMAIL_TEMPLATES = {
    # We have one or more possible jobs - show cards
    "confirm": """
<p style="margin: 0 0 20px 0;">I'm not totally sure which job you mean. Do any of these look right?</p>
{job_cards}
<p style="margin: 0 0 24px 0;">Click a card to open it in Hub, or just reply with the job number and I'll get on with it.</p>
<p style="margin: 0;">Dot</p>
""",
    
    # Can't identify client or intent at all
    "no_idea": """
<p style="margin: 0 0 20px 0;">Throw me a bone here – I've got totally no idea what you're asking for.</p>
<p style="margin: 0 0 24px 0;">Come back to me with a job number, or a client – and I'll see what I can do.</p>
<p style="margin: 0;">Dot</p>
""",
    
    # Job number provided but doesn't exist
    "job_not_found": """
<p style="margin: 0 0 20px 0;">I couldn't find job <strong>{job_number}</strong> in the system.</p>
<p style="margin: 0 0 24px 0;">Please check the job number and try again, or reply <strong>TRIAGE</strong> if this is a new job.</p>
<p style="margin: 0;">Dot</p>
""",
}


def _format_job_cards(possible_jobs):
    """Format list of possible jobs as HTML cards with Hub links"""
    if not possible_jobs:
        return "<p><em>No active jobs found</em></p>"
    
    # Hub base URL
    HUB_URL = "https://dot-hub.up.railway.app"
    
    cards = []
    for job in possible_jobs[:5]:  # Max 5 jobs
        job_number = job.get('jobNumber', '')
        job_name = job.get('jobName', '')
        stage = job.get('stage', '')
        status = job.get('status', '')
        update_due = job.get('updateDue', 'TBC')
        with_client = job.get('withClient', False)
        
        # Build Hub link
        hub_link = f"{HUB_URL}/?job={job_number.replace(' ', '')}&action=edit"
        
        # Status badge
        status_text = "With client" if with_client else stage
        
        # Card HTML - inline styles for email compatibility
        card = f"""
<table cellpadding="0" cellspacing="0" border="0" width="100%" style="margin-bottom:12px;">
  <tr>
    <td style="background:#f5f5f5; border-radius:8px; padding:16px; border-left:4px solid #ED1C24;">
      <a href="{hub_link}" style="text-decoration:none; color:inherit; display:block;">
        <table cellpadding="0" cellspacing="0" border="0" width="100%">
          <tr>
            <td style="font-size:17px; font-weight:600; color:#1a1a1a; padding-bottom:4px;">
              {job_number} | {job_name}
            </td>
          </tr>
          <tr>
            <td style="font-size:14px; color:#666;">
              {status_text} | Due {update_due}
            </td>
          </tr>
        </table>
      </a>
    </td>
  </tr>
</table>
"""
        cards.append(card)
    
    return "\n".join(cards)


def build_email(clarify_type, routing_data):
    """
    Build email HTML from template and routing data.
    
    Args:
        clarify_type: One of: confirm_job, unknown_job, no_idea, job_not_found
        routing_data: Dict with routing info from Claude
    
    Returns:
        HTML string for email body
    """
    # Map old clarify types to new simplified ones
    type_mapping = {
        'confirm_job': 'confirm',
        'unknown_job': 'confirm',
        'pick_job': 'confirm',
        'no_idea': 'no_idea',
        'job_not_found': 'job_not_found',
    }
    template_type = type_mapping.get(clarify_type, clarify_type)
    template = EMAIL_TEMPLATES.get(template_type, EMAIL_TEMPLATES['no_idea'])
    
    # Get sender name
    sender_name = routing_data.get('senderName', '')
    
    # Build job cards if needed
    job_cards = ""
    if template_type == "confirm":
        possible_jobs = routing_data.get('possibleJobs', [])
        # If we have a single suggested job, wrap it in a list
        if not possible_jobs and routing_data.get('suggestedJob'):
            possible_jobs = [routing_data.get('suggestedJob')]
        # If we have jobNumber but no possibleJobs, create a minimal job object
        if not possible_jobs and routing_data.get('jobNumber'):
            possible_jobs = [{
                'jobNumber': routing_data.get('jobNumber', ''),
                'jobName': routing_data.get('jobName', ''),
                'stage': routing_data.get('currentStage', ''),
                'status': routing_data.get('currentStatus', ''),
                'updateDue': 'TBC',
                'withClient': routing_data.get('withClient', False),
            }]
        job_cards = _format_job_cards(possible_jobs)
    
    # Get job number for job_not_found template
    job_number = routing_data.get('jobNumber', '')
    
    # Format template
    content = template.format(
        job_number=job_number,
        job_cards=job_cards
    )
    
    # Build original email data for trail
    original_email = None
    if routing_data.get('emailContent'):
        original_email = {
            'senderName': routing_data.get('senderName', ''),
            'senderEmail': routing_data.get('senderEmail', ''),
            'subject': routing_data.get('subjectLine', ''),
            'receivedDateTime': routing_data.get('receivedDateTime', ''),
            'content': routing_data.get('emailContent', '')
        }
    
    # Wrap with styling and footer
    return _email_wrapper(content, sender_name, original_email)


# ===================
# DOWNSTREAM CALLS
# ===================

def call_worker(route, payload):
    """
    Call a downstream worker with the universal payload.
    
    Args:
        route: The route name (file, update, triage, etc.)
        payload: The universal payload dict
    
    Returns:
        dict with result info
    """
    route_config = ROUTES.get(route)
    
    if not route_config:
        return {
            'success': False,
            'error': f'Unknown route: {route}',
            'status': 'unknown'
        }
    
    status = route_config['status']
    endpoint = route_config['endpoint']
    
    # If not built, just return what we would have sent
    if status == 'not_built':
        return {
            'success': True,
            'status': 'not_built',
            'would_send_to': endpoint,
            'payload': payload,
            'message': f'Route "{route}" not built yet. Logged payload.'
        }
    
    # If testing, log but also try to call
    if status == 'testing':
        print(f"[connect] Testing route '{route}' -> {endpoint}")
    
    # Handle PA Postman (email sending)
    if endpoint == 'PA_POSTMAN':
        return call_postman(route, payload)
    
    # Call the worker
    try:
        response = httpx.post(
            endpoint,
            json=payload,
            timeout=TIMEOUT,
            headers={'Content-Type': 'application/json'}
        )
        
        return {
            'success': response.status_code == 200,
            'status': status,
            'endpoint': endpoint,
            'response_code': response.status_code,
            'response': response.json() if response.status_code == 200 else response.text
        }
        
    except Exception as e:
        print(f"[connect] Error calling {endpoint}: {e}")
        return {
            'success': False,
            'status': status,
            'endpoint': endpoint,
            'error': str(e)
        }


def call_postman(route, payload):
    """
    Call PA Postman to send an email (for clarify/confirm routes).
    
    Args:
        route: Either 'clarify' or 'confirm'
        payload: The universal payload dict
    
    Returns:
        dict with result info
    """
    # Build the postman payload - matches PA schema: to, subject, body
    postman_payload = {
        'to': payload.get('senderEmail', ''),
        'subject': f"Re: {payload.get('subjectLine', '')}",
        'body': payload.get('emailHtml', '')
    }
    
    if not PA_POSTMAN_URL:
        return {
            'success': False,
            'status': 'testing',
            'error': 'PA_POSTMAN_URL not configured',
            'would_send': postman_payload
        }
    
    try:
        response = httpx.post(
            PA_POSTMAN_URL,
            json=postman_payload,
            timeout=TIMEOUT,
            headers={'Content-Type': 'application/json'}
        )
        
        return {
            'success': response.status_code == 200 or response.status_code == 202,
            'status': 'live',
            'endpoint': 'PA_POSTMAN',
            'response_code': response.status_code
        }
        
    except Exception as e:
        print(f"[connect] Error calling PA Postman: {e}")
        return {
            'success': False,
            'status': 'testing',
            'endpoint': 'PA_POSTMAN',
            'error': str(e),
            'would_send': postman_payload
        }


# ===================
# CONFIRMATION EMAILS
# ===================

ROUTE_FRIENDLY_TEXT = {
    'file': 'Files filed',
    'update': 'Job updated',
    'triage': 'Job triaged',
    'incoming': 'Incoming job logged',
    'feedback': 'Feedback logged',
    'work-to-client': 'Work sent to client logged',
}

ROUTE_SUBTITLE = {
    'file': 'Filed to {destination}',
    'update': 'Status updated',
    'triage': 'New job created',
    'incoming': 'Added to pipeline',
    'feedback': 'Feedback recorded',
    'work-to-client': 'Delivery logged',
}

# Routes that don't need confirmation (they already send emails)
NO_CONFIRM_ROUTES = ['clarify', 'confirm', 'wip', 'todo', 'tracker', 'answer']


def send_confirmation(to_email, route, sender_name=None, client_name=None, job_number=None, job_name=None,
                      subject_line=None, files_url=None, destination=None, original_email=None):
    """
    Send a confirmation email after successful worker action.
    
    Args:
        to_email: Recipient email
        route: The route that was executed
        sender_name: Sender's name for greeting
        client_name: Client name (optional)
        job_number: Job number (optional)
        job_name: Job name (optional)
        subject_line: Original email subject for Re: line
        files_url: SharePoint folder URL (optional)
        destination: Where files were filed (optional)
        original_email: Dict with original email for trail (optional)
    
    Returns:
        dict with result info
    """
    if route in NO_CONFIRM_ROUTES:
        return {'success': True, 'skipped': True, 'reason': 'Route sends its own email'}
    
    friendly_text = ROUTE_FRIENDLY_TEXT.get(route, 'Request completed')
    
    # Build title line: "ONE 066 | Email Design System" or just "ONE 066"
    if job_number and job_name:
        box_title = f"{job_number} | {job_name}"
    elif job_number:
        box_title = job_number
    elif client_name:
        box_title = client_name
    else:
        box_title = "Done"
    
    # Build subtitle
    subtitle_template = ROUTE_SUBTITLE.get(route, 'Completed')
    box_subtitle = subtitle_template.format(destination=destination or 'job folder')
    
    # Build files link if available
    files_link = ''
    if files_url:
        files_link = f'<p style="margin: 0 0 24px 0;"><a href="{files_url}" style="color: #ED1C24; text-decoration: none; font-weight: 600; font-size: 17px;">See the files →</a></p>'
    
    # Build email content (without greeting - wrapper adds it)
    content = f"""<p style="margin: 0 0 20px 0;">All sorted. {friendly_text}.</p>

{_success_box(box_title, box_subtitle)}

{files_link}
<p style="margin: 0;">Dot</p>"""
    
    body_html = _email_wrapper(content, sender_name, original_email)
    
    subject = f"Re: {subject_line}" if subject_line else "Dot - Done"
    
    postman_payload = {
        'to': to_email,
        'subject': subject,
        'body': body_html
    }
    
    print(f"[connect] Sending confirmation: {friendly_text} -> {to_email}")
    
    if not PA_POSTMAN_URL:
        return {
            'success': False,
            'status': 'testing',
            'error': 'PA_POSTMAN_URL not configured',
            'would_send': postman_payload
        }
    
    try:
        response = httpx.post(
            PA_POSTMAN_URL,
            json=postman_payload,
            timeout=TIMEOUT,
            headers={'Content-Type': 'application/json'}
        )
        
        return {
            'success': response.status_code == 200 or response.status_code == 202,
            'status': 'live',
            'endpoint': 'PA_POSTMAN',
            'response_code': response.status_code
        }
        
    except Exception as e:
        print(f"[connect] Error sending confirmation: {e}")
        return {
            'success': False,
            'status': 'testing',
            'endpoint': 'PA_POSTMAN',
            'error': str(e),
            'would_send': postman_payload
        }


# ===================
# ANSWER EMAILS (Q&A responses)
# ===================

def send_answer(to_email, message, sender_name=None, subject_line=None, client_code=None, client_name=None, original_email=None):
    """
    Send an answer email for Q&A type queries.
    
    Args:
        to_email: Recipient email
        message: The answer message from Claude
        sender_name: Sender's name for greeting
        subject_line: Original email subject for Re: line
        client_code: Client code if relevant
        client_name: Client name if relevant
        original_email: Dict with original email for trail (optional)
    
    Returns:
        dict with result info
    """
    # Build context line if we have client info
    context_line = ''
    if client_name:
        context_line = f'<p style="margin: 0 0 16px 0; font-size: 14px; color: #666;">{client_name}</p>'
    
    # Build email content
    content = f"""{context_line}
{_info_box(message)}

<p style="margin: 0;">Dot</p>"""
    
    body_html = _email_wrapper(content, sender_name, original_email)
    
    subject = f"Re: {subject_line}" if subject_line else "Dot"
    
    postman_payload = {
        'to': to_email,
        'subject': subject,
        'body': body_html
    }
    
    print(f"[connect] Sending answer -> {to_email}")
    
    if not PA_POSTMAN_URL:
        return {
            'success': False,
            'status': 'testing',
            'error': 'PA_POSTMAN_URL not configured',
            'would_send': postman_payload
        }
    
    try:
        response = httpx.post(
            PA_POSTMAN_URL,
            json=postman_payload,
            timeout=TIMEOUT,
            headers={'Content-Type': 'application/json'}
        )
        
        return {
            'success': response.status_code == 200 or response.status_code == 202,
            'status': 'live',
            'endpoint': 'PA_POSTMAN',
            'response_code': response.status_code
        }
        
    except Exception as e:
        print(f"[connect] Error sending answer: {e}")
        return {
            'success': False,
            'status': 'testing',
            'endpoint': 'PA_POSTMAN',
            'error': str(e),
            'would_send': postman_payload
        }


# ===================
# FAILURE EMAILS
# ===================

def send_failure(to_email, route, error_message, sender_name=None, subject_line=None, job_number=None,
                 job_name=None, client_name=None, original_email=None):
    """
    Send a failure notification email when a worker fails.
    
    Args:
        to_email: Recipient email
        route: The route that failed
        error_message: The error message from the worker
        sender_name: Sender's name for greeting
        subject_line: Original email subject
        job_number: Job number (optional)
        job_name: Job name (optional)
        client_name: Client name (optional)
        original_email: Dict with original email for trail (optional)
    
    Returns:
        dict with result info
    """
    if route in NO_CONFIRM_ROUTES:
        return {'success': True, 'skipped': True, 'reason': 'Route sends its own email'}
    
    # Build title line
    if job_number and job_name:
        box_title = f"{job_number} | {job_name}"
    elif job_number:
        box_title = job_number
    elif client_name:
        box_title = client_name
    else:
        box_title = "Error"
    
    # Build subtitle based on route
    route_action = {
        'file': "Couldn't file attachments",
        'update': "Couldn't update job",
        'triage': "Couldn't create job",
        'incoming': "Couldn't log incoming",
        'feedback': "Couldn't log feedback",
        'work-to-client': "Couldn't log delivery",
    }
    box_subtitle = route_action.get(route, "Something went wrong")
    
    # Build email content
    content = f"""<p style="margin: 0 0 20px 0;">Sorry, I got in a muddle over that one.</p>

{_failure_box(box_title, box_subtitle)}

<p style="margin: 0 0 8px 0; font-size: 14px; color: #666;">Here's what I told myself in Dot Language:</p>
<pre style="background: #f5f5f5; padding: 12px; border-radius: 6px; font-size: 13px; overflow-x: auto; color: #666; margin: 0 0 24px 0; font-family: 'SF Mono', Monaco, 'Courier New', monospace;">{error_message}</pre>

<p style="margin: 0;">Dot</p>"""
    
    body_html = _email_wrapper(content, sender_name, original_email)
    
    subject = f"Did not compute: {subject_line}" if subject_line else "Did not compute"
    
    postman_payload = {
        'to': to_email,
        'subject': subject,
        'body': body_html
    }
    
    print(f"[connect] Sending failure notification: {route} failed -> {to_email}")
    
    if not PA_POSTMAN_URL:
        return {
            'success': False,
            'status': 'testing',
            'error': 'PA_POSTMAN_URL not configured',
            'would_send': postman_payload
        }
    
    try:
        response = httpx.post(
            PA_POSTMAN_URL,
            json=postman_payload,
            timeout=TIMEOUT,
            headers={'Content-Type': 'application/json'}
        )
        
        return {
            'success': response.status_code == 200 or response.status_code == 202,
            'status': 'live',
            'endpoint': 'PA_POSTMAN',
            'response_code': response.status_code
        }
        
    except Exception as e:
        print(f"[connect] Error sending failure notification: {e}")
        return {
            'success': False,
            'status': 'testing',
            'endpoint': 'PA_POSTMAN',
            'error': str(e),
            'would_send': postman_payload
        }
