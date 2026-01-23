"""
Dot Traffic 2.0 - Connect
Pure communication layer: emails and Teams posts.

DOT THINKS (traffic.py)
WORKERS WORK (dot-update, dot-file, etc.)
AIRTABLE REMEMBERS (airtable.py)
CONNECT COMMUNICATES (this file)

This module handles:
- Sending emails via PA Postman (answers, clarifications, confirmations, failures)
- Posting to Teams channels via PA Teamsbot
"""

import os
import httpx

# ===================
# CONFIG
# ===================

PA_POSTMAN_URL = os.environ.get('PA_POSTMAN_URL', '')
PA_TEAMSBOT_URL = os.environ.get('PA_TEAMSBOT_URL', '')

TIMEOUT = 30.0

# Logo for email footer (300x150 original, display at 56x28 to maintain 2:1 ratio)
LOGO_URL = "https://raw.githubusercontent.com/MGhunch/dot-hub/main/images/ai2-logo.png"

# Hub base URL
HUB_URL = "https://dot.hunch.co.nz"


# ===================
# HELPER FUNCTIONS
# ===================

def _get_first_name(sender_name):
    """Extract first name from sender name, fallback to 'there'"""
    if not sender_name:
        return "there"
    first = sender_name.split()[0].strip('"\'[]()') if sender_name else "there"
    return first if first else "there"


def _email_wrapper(content):
    """Wrap email content with consistent styling and footer"""
    return f"""<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 15px; line-height: 1.6; color: #333;">
{content}

<table cellpadding="0" cellspacing="0" border="0" width="100%" style="margin-top: 32px; border-top: 1px solid #eee; padding-top: 16px;">
  <tr>
    <td style="vertical-align: middle; padding-right: 12px;" width="60">
      <img src="{LOGO_URL}" alt="hai2" width="56" height="28" style="display: block;">
    </td>
    <td style="vertical-align: middle; font-size: 12px; color: #999;">
      Dot is a robot, but there's humans in the loop.
    </td>
  </tr>
</table>
</div>"""


def _success_box(title, subtitle):
    """Green success detail box with tick"""
    return f"""<table cellpadding="0" cellspacing="0" border="0" width="100%" style="margin-bottom: 20px;">
  <tr>
    <td style="background: #f0fdf4; border-radius: 8px; padding: 16px; border-left: 4px solid #22c55e;">
      <table cellpadding="0" cellspacing="0" border="0" width="100%">
        <tr>
          <td width="28" style="vertical-align: top; padding-right: 12px;">
            <div style="width: 24px; height: 24px; background: #22c55e; border-radius: 50%; text-align: center; line-height: 24px;">
              <span style="color: white; font-size: 14px;">✓</span>
            </div>
          </td>
          <td style="vertical-align: top;">
            <div style="font-weight: 600; color: #333; margin-bottom: 2px;">{title}</div>
            <div style="font-size: 13px; color: #666;">{subtitle}</div>
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
          <td width="28" style="vertical-align: top; padding-right: 12px;">
            <div style="width: 24px; height: 24px; background: #ef4444; border-radius: 50%; text-align: center; line-height: 24px;">
              <span style="color: white; font-size: 14px;">✕</span>
            </div>
          </td>
          <td style="vertical-align: top;">
            <div style="font-weight: 600; color: #333; margin-bottom: 2px;">{title}</div>
            <div style="font-size: 13px; color: #666;">{subtitle}</div>
          </td>
        </tr>
      </table>
    </td>
  </tr>
</table>"""


def _format_job_cards(possible_jobs):
    """Format list of possible jobs as HTML cards with Hub links"""
    if not possible_jobs:
        return "<p><em>No active jobs found</em></p>"
    
    cards = []
    for job in possible_jobs[:5]:  # Max 5 jobs
        job_number = job.get('jobNumber', '')
        job_name = job.get('jobName', '')
        stage = job.get('stage', '')
        update_due = job.get('updateDue', 'TBC')
        with_client = job.get('withClient', False)
        
        # Build Hub link
        hub_link = f"{HUB_URL}/?job={job_number.replace(' ', '')}&action=edit"
        
        # Status badge
        status_text = "With client" if with_client else stage
        
        card = f"""
<table cellpadding="0" cellspacing="0" border="0" width="100%" style="margin-bottom:12px;">
  <tr>
    <td style="background:#f5f5f5; border-radius:8px; padding:16px; border-left:4px solid #ED1C24;">
      <a href="{hub_link}" style="text-decoration:none; color:inherit; display:block;">
        <table cellpadding="0" cellspacing="0" border="0" width="100%">
          <tr>
            <td style="font-size:16px; font-weight:600; color:#1a1a1a; padding-bottom:4px;">
              {job_number} | {job_name}
            </td>
          </tr>
          <tr>
            <td style="font-size:13px; color:#666;">
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


def _send_email(to_email, subject, body_html, original_email=None):
    """
    Send an email via PA Postman.
    
    Args:
        to_email: Recipient email address
        subject: Email subject line
        body_html: HTML body content
        original_email: Optional dict with original email for trail:
            {
                'senderName': 'Michael',
                'senderEmail': 'michael@hunch.co.nz',
                'subject': 'Original subject',
                'receivedDateTime': '2026-01-24T08:00:00Z',
                'content': 'Original email body text'
            }
    
    Returns dict with success status.
    """
    postman_payload = {
        'to': to_email,
        'subject': subject,
        'body': body_html
    }
    
    # Include original email for trail if provided (formatted for PA Postman)
    if original_email:
        postman_payload['replyTo'] = {
            'from': original_email.get('senderName', ''),
            'fromEmail': original_email.get('senderEmail', ''),
            'sent': original_email.get('receivedDateTime', ''),
            'subject': original_email.get('subject', ''),
            'body': original_email.get('content', '')
        }
    
    if not PA_POSTMAN_URL:
        print(f"[connect] PA_POSTMAN_URL not configured")
        return {
            'success': False,
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
        
        success = response.status_code in [200, 202]
        print(f"[connect] Email sent: {success} (status {response.status_code})")
        
        return {
            'success': success,
            'response_code': response.status_code
        }
        
    except Exception as e:
        print(f"[connect] Error sending email: {e}")
        return {
            'success': False,
            'error': str(e),
            'would_send': postman_payload
        }


# ===================
# TEAMS POSTING
# ===================

def post_to_teams(team_id, channel_id, message, subject=None, job_number=None, context=None):
    """
    Post a message to a Teams channel via PA Teamsbot.
    
    Args:
        team_id: The Teams team ID (from Clients table)
        channel_id: The Teams channel ID (from Projects table)
        message: The message to post (summary of what happened)
        subject: Optional subject line
        job_number: Optional job number for logging
        context: Optional context from original email (Teams doesn't have the email trail)
    
    Returns:
        dict with success status
    """
    if not team_id or not channel_id:
        print(f"[connect] Teams post skipped - missing IDs (team: {team_id}, channel: {channel_id})")
        return {
            'success': False,
            'error': 'Missing teamId or channelId',
            'skipped': True
        }
    
    if not subject and job_number:
        subject = f"Update: {job_number}"
    
    # Build full message with context if provided
    full_message = message
    if context:
        # Truncate context if very long
        context_text = context[:500] + '...' if len(context) > 500 else context
        full_message = f"{message}\n\n---\n**Context:**\n>{context_text}"
    
    teams_payload = {
        'teamId': team_id,
        'channelId': channel_id,
        'subject': subject or '',
        'message': full_message,
        'jobNumber': job_number or ''
    }
    
    print(f"[connect] Posting to Teams: {job_number or 'update'}")
    
    if not PA_TEAMSBOT_URL:
        print(f"[connect] PA_TEAMSBOT_URL not configured")
        return {
            'success': False,
            'error': 'PA_TEAMSBOT_URL not configured',
            'would_send': teams_payload
        }
    
    try:
        response = httpx.post(
            PA_TEAMSBOT_URL,
            json=teams_payload,
            timeout=TIMEOUT,
            headers={'Content-Type': 'application/json'}
        )
        
        success = response.status_code in [200, 202]
        print(f"[connect] Teams post: {success} (status {response.status_code})")
        
        return {
            'success': success,
            'response_code': response.status_code
        }
        
    except Exception as e:
        print(f"[connect] Error posting to Teams: {e}")
        return {
            'success': False,
            'error': str(e),
            'would_send': teams_payload
        }


# ===================
# EMAIL: ANSWERS (from Traffic directly)
# ===================

def send_answer(to_email, message, sender_name=None, subject_line=None, original_email=None):
    """
    Send an answer email - Dot's response to a question.
    Called directly by Traffic for simple Q&A.
    """
    first_name = _get_first_name(sender_name)
    
    content = f"""<p style="margin: 0 0 20px 0;">Hey {first_name},</p>
<p style="margin: 0 0 20px 0;">{message}</p>
<p style="margin: 0;">Dot</p>"""
    
    body_html = _email_wrapper(content)
    subject = f"Re: {subject_line}" if subject_line else "Dot"
    
    print(f"[connect] Sending answer -> {to_email}")
    return _send_email(to_email, subject, body_html, original_email)


# ===================
# EMAIL: REDIRECTS (from Traffic directly)
# ===================

def send_redirect(to_email, sender_name=None, subject_line=None, client_code=None, 
                  client_name=None, redirect_to='wip', message=None, original_email=None):
    """
    Send a redirect email - pointing user to WIP or Tracker.
    Called directly by Traffic.
    """
    first_name = _get_first_name(sender_name)
    redirect_to_lower = (redirect_to or 'wip').lower()
    
    # Build the Hub link
    client_param = f"?client={client_code}" if client_code else ""
    view_param = f"&view={redirect_to_lower}" if client_param else f"?view={redirect_to_lower}"
    hub_link = f"{HUB_URL}/{client_param}{view_param}"
    
    display_name = client_name or client_code or ""
    
    if redirect_to_lower == 'tracker':
        default_message = "Gosh, that's getting into more detail than I'm good at. You should find everything you need in the Tracker."
        link_text = f"Open Tracker for {display_name} →" if display_name else "Open Tracker →"
    else:
        default_message = "That's getting into the detail more than I'm good at. You should find everything you need in the WIP."
        link_text = f"Open {display_name} WIP →" if display_name else "Open WIP →"
    
    display_message = message if message else default_message
    
    content = f"""<p style="margin: 0 0 20px 0;">Hey {first_name},</p>
<p style="margin: 0 0 20px 0;">{display_message}</p>
<p style="margin: 0 0 24px 0;"><a href="{hub_link}" style="color: #ED1C24; text-decoration: none; font-weight: 500;">{link_text}</a></p>
<p style="margin: 0;">Dot</p>"""
    
    body_html = _email_wrapper(content)
    subject = f"Re: {subject_line}" if subject_line else "Dot"
    
    print(f"[connect] Sending redirect ({redirect_to_lower}) -> {to_email}")
    return _send_email(to_email, subject, body_html, original_email)


# ===================
# EMAIL: CLARIFY (from Traffic directly)
# ===================

def send_clarify(to_email, clarify_type, sender_name=None, subject_line=None,
                 job_number=None, possible_jobs=None, original_email=None):
    """
    Send a clarification email - asking for more info.
    Called directly by Traffic.
    
    clarify_types:
    - 'confirm' - show job cards, ask which one
    - 'no_idea' - couldn't understand at all
    - 'job_not_found' - job number doesn't exist
    """
    first_name = _get_first_name(sender_name)
    
    if clarify_type == 'confirm':
        job_cards = _format_job_cards(possible_jobs or [])
        content = f"""<p style="margin: 0 0 20px 0;">Hey {first_name},</p>
<p style="margin: 0 0 20px 0;">I'm not totally sure which job you mean. Do any of these look right?</p>
{job_cards}
<p style="margin: 0 0 24px 0;">Just reply with a job number and I'll get on with it.</p>
<p style="margin: 0;">Dot</p>"""
    
    elif clarify_type == 'job_not_found':
        content = f"""<p style="margin: 0 0 20px 0;">Hey {first_name},</p>
<p style="margin: 0 0 20px 0;">Sorry, I can't find job <strong>{job_number}</strong> right now.</p>
<p style="margin: 0 0 24px 0;">Please check the job number and try again, or reply "Incoming" if it's a new job.</p>
<p style="margin: 0;">Dot</p>"""
    
    else:  # no_idea
        content = f"""<p style="margin: 0 0 20px 0;">Hey {first_name},</p>
<p style="margin: 0 0 20px 0;">Throw me a bone, I have no idea what you're after.</p>
<p style="margin: 0 0 24px 0;">Let me know which client or project... bonus points for a job number.</p>
<p style="margin: 0;">Dot</p>"""
    
    body_html = _email_wrapper(content)
    subject = f"Re: {subject_line}" if subject_line else "Dot"
    
    print(f"[connect] Sending clarify ({clarify_type}) -> {to_email}")
    return _send_email(to_email, subject, body_html, original_email)


# ===================
# EMAIL: CONFIRMATION (from Workers after success)
# ===================

def send_confirmation(to_email, route, sender_name=None, subject_line=None,
                      job_number=None, job_name=None, client_name=None, files_url=None,
                      original_email=None):
    """
    Send a confirmation email after successful worker action.
    Called by Workers after completing their task.
    """
    first_name = _get_first_name(sender_name)
    
    # Friendly text based on route
    friendly_text = {
        'file': 'Files filed',
        'update': 'Job updated',
        'triage': 'Job triaged',
        'new-job': 'New job logged',
        'feedback': 'Feedback logged',
        'work-to-client': 'Work sent to client logged',
    }.get(route, 'Request completed')
    
    # Build title line
    if job_number and job_name:
        box_title = f"{job_number} | {job_name}"
    elif job_number:
        box_title = job_number
    elif client_name:
        box_title = client_name
    else:
        box_title = "Done"
    
    # Build subtitle
    subtitle = {
        'file': 'Filed to job folder',
        'update': 'Status updated',
        'triage': 'New job created',
        'new-job': 'Added to pipeline',
        'feedback': 'Feedback recorded',
        'work-to-client': 'Delivery logged',
    }.get(route, 'Completed')
    
    # Files link if available
    files_link = ''
    if files_url:
        files_link = f'<p style="margin: 0 0 24px 0;"><a href="{files_url}" style="color: #ED1C24; text-decoration: none; font-weight: 500;">See the files →</a></p>'
    
    content = f"""<p style="margin: 0 0 20px 0;">Hey {first_name},</p>
<p style="margin: 0 0 20px 0;">All sorted. {friendly_text}.</p>

{_success_box(box_title, subtitle)}

{files_link}
<p style="margin: 0;">Dot</p>"""
    
    body_html = _email_wrapper(content)
    subject = f"Re: {subject_line}" if subject_line else "Dot - Done"
    
    print(f"[connect] Sending confirmation: {friendly_text} -> {to_email}")
    return _send_email(to_email, subject, body_html, original_email)


# ===================
# EMAIL: FAILURE (from Workers or app.py on error)
# ===================

def send_failure(to_email, route, error_message, sender_name=None, subject_line=None,
                 job_number=None, job_name=None, client_name=None, original_email=None):
    """
    Send a failure notification email when something goes wrong.
    Called by Workers or app.py when an error occurs.
    """
    first_name = _get_first_name(sender_name)
    
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
    box_subtitle = {
        'file': "Couldn't file attachments",
        'update': "Couldn't update job",
        'triage': "Couldn't create job",
        'new-job': "Couldn't log new job",
        'feedback': "Couldn't log feedback",
        'work-to-client': "Couldn't log delivery",
    }.get(route, "Something went wrong")
    
    content = f"""<p style="margin: 0 0 20px 0;">Hey {first_name},</p>
<p style="margin: 0 0 20px 0;">Sorry, I got in a muddle over that one.</p>

{_failure_box(box_title, box_subtitle)}

<p style="margin: 0 0 8px 0; font-size: 13px; color: #666;">Here's what I told myself in Dot Language:</p>
<pre style="background: #f5f5f5; padding: 12px; border-radius: 6px; font-size: 12px; overflow-x: auto; color: #666; margin: 0 0 24px 0; font-family: 'SF Mono', Monaco, 'Courier New', monospace;">{error_message}</pre>

<p style="margin: 0;">Dot</p>"""
    
    body_html = _email_wrapper(content)
    subject = f"Did not compute: {subject_line}" if subject_line else "Did not compute"
    
    print(f"[connect] Sending failure notification: {route} failed -> {to_email}")
    return _send_email(to_email, subject, body_html, original_email)


# ===================
# EMAIL: NOT BUILT (route not implemented yet)
# ===================

def send_not_built(to_email, route, sender_name=None, subject_line=None, original_email=None):
    """
    Send a "not built yet" email when user tries an action that isn't ready.
    """
    first_name = _get_first_name(sender_name)
    
    route_messages = {
        'triage': "Triage isn't ready yet. Watch this space.",
        'todo': f"To-do lists coming soon. Check the WIP in the Hub for now. <a href=\"{HUB_URL}/?view=wip\" style=\"color: #ED1C24;\">Open WIP →</a>",
        'new-job': "Not set up for new jobs yet. Better to email a human.",
    }
    
    message = route_messages.get(route, f"Sorry, we're still working on <strong>{route}</strong>. Hoping to have it up and running soon.")
    
    content = f"""<p style="margin: 0 0 20px 0;">Hey {first_name},</p>
<p style="margin: 0 0 20px 0;">{message}</p>
<p style="margin: 0;">Dot</p>"""
    
    body_html = _email_wrapper(content)
    subject = f"Re: {subject_line}" if subject_line else "Dot - Coming Soon"
    
    print(f"[connect] Sending not_built notification: {route} -> {to_email}")
    return _send_email(to_email, subject, body_html, original_email)
