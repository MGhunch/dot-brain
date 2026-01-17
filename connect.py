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


# ===================
# ROUTE REGISTRY
# ===================

ROUTES = {
    "file": {
        "endpoint": "https://dot-file.up.railway.app/process",
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
}


# ===================
# EMAIL TEMPLATES
# ===================

EMAIL_TEMPLATES = {
    # Medium confidence - we have a good guess
    "confirm_job": """
<p>Hi {sender_name},</p>
<p>I think this is for:</p>
<p><strong>{job_number} - {job_name}</strong></p>
<p>Reply <strong>YES</strong> to confirm, or give me the correct job number.</p>
<p>Dot</p>
""",
    
    # Known client, but can't determine which job
    "unknown_job": """
<p>Hi {sender_name},</p>
<p>I can see we're talking about <strong>{client_name}</strong> but it's not clear which job.</p>
<p>Any of these?</p>
{job_list}
<p>Reply with the job number, or reply <strong>TRIAGE</strong> if this is a new job.</p>
<p>Dot</p>
""",
    
    # Can't identify client or intent at all
    "no_idea": """
<p>Hi {sender_name},</p>
<p>Throw me a bone here – I've got totally no idea what you're asking for.</p>
<p>Come back to me with a job number, or a client – and I'll see what I can do.</p>
<p>Dot</p>
""",
    
    # Job number provided but doesn't exist
    "job_not_found": """
<p>Hi {sender_name},</p>
<p>I couldn't find job <strong>{job_number}</strong> in the system.</p>
<p>Please check the job number and try again, or reply <strong>TRIAGE</strong> if this is a new job.</p>
<p>Dot</p>
""",
}


def _format_job_list(possible_jobs):
    """Format list of possible jobs as HTML"""
    if not possible_jobs:
        return "<p><em>No active jobs found</em></p>"
    
    lines = []
    for job in possible_jobs[:5]:  # Max 5 jobs
        lines.append(f"<strong>{job['jobNumber']}</strong> - {job['jobName']}")
    
    return "<p>" + "<br>".join(lines) + "</p>"


def build_email(clarify_type, routing_data):
    """
    Build email HTML from template and routing data.
    
    Args:
        clarify_type: One of: confirm_job, unknown_job, no_idea, job_not_found
        routing_data: Dict with routing info from Claude
    
    Returns:
        HTML string for email body
    """
    template = EMAIL_TEMPLATES.get(clarify_type, EMAIL_TEMPLATES['no_idea'])
    
    # Get sender name (default to "there")
    sender_name = routing_data.get('senderName', '') or 'there'
    
    # Build job list if needed
    job_list = ""
    if clarify_type == "unknown_job":
        possible_jobs = routing_data.get('possibleJobs', [])
        job_list = _format_job_list(possible_jobs)
    
    # Get suggested job info for confirm
    suggested_job = routing_data.get('suggestedJob', {})
    job_number = suggested_job.get('jobNumber', routing_data.get('jobNumber', ''))
    job_name = suggested_job.get('jobName', '')
    
    # Format template
    html = template.format(
        sender_name=sender_name,
        client_name=routing_data.get('clientName', 'your client'),
        job_number=job_number,
        job_name=job_name,
        job_list=job_list
    )
    
    return html.strip()


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
        print(f"[connect] Testing route '{route}' → {endpoint}")
    
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
