"""
Dot Traffic 2.0 - Airtable Operations

Job data now comes from Hub API (single source of truth).
Direct Airtable access only for: Traffic logging, Updates, People, Teams routing.
"""

import os
import httpx
from datetime import datetime

# ===================
# CONFIG
# ===================

AIRTABLE_API_KEY = os.environ.get('AIRTABLE_API_KEY')
AIRTABLE_BASE_ID = os.environ.get('AIRTABLE_BASE_ID', 'app8CI7NAZqhQ4G1Y')

# Hub API for job data (single source of truth)
HUB_API_BASE = os.environ.get('HUB_API_BASE', 'https://dot.hunch.co.nz')

PROJECTS_TABLE = 'Projects'
CLIENTS_TABLE = 'Clients'
TRAFFIC_TABLE = 'Traffic'
UPDATES_TABLE = 'Updates'

TIMEOUT = 10.0


def _headers():
    """Standard Airtable headers"""
    return {
        'Authorization': f'Bearer {AIRTABLE_API_KEY}',
        'Content-Type': 'application/json'
    }


def _url(table):
    """Build Airtable URL for a table"""
    return f'https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{table}'


# ===================
# JOB DATA (via Hub API)
# ===================

def get_active_jobs(client_code):
    """
    Get all active jobs for a client via Hub API.
    Returns list of job dicts with full details for job cards.
    """
    if not client_code:
        return []
    
    try:
        url = f"{HUB_API_BASE}/api/jobs/all?status=active&client={client_code}"
        print(f"[airtable] Fetching active jobs for {client_code} from Hub")
        
        response = httpx.get(url, timeout=TIMEOUT)
        response.raise_for_status()
        
        jobs = response.json()
        print(f"[airtable] Found {len(jobs)} active jobs for {client_code}")
        return jobs
        
    except Exception as e:
        print(f"[airtable] Error getting active jobs from Hub: {e}")
        return []


def get_all_active_jobs():
    """
    Get ALL active jobs across ALL clients via Hub API.
    Returns list of job dicts - typically ~20 jobs total.
    """
    try:
        url = f"{HUB_API_BASE}/api/jobs/all?status=active"
        print(f"[airtable] Fetching all active jobs from Hub")
        
        response = httpx.get(url, timeout=TIMEOUT)
        response.raise_for_status()
        
        jobs = response.json()
        print(f"[airtable] Found {len(jobs)} total active jobs")
        return jobs
        
    except Exception as e:
        print(f"[airtable] Error getting all active jobs from Hub: {e}")
        return []


def get_completed_jobs(client_code=None):
    """
    Get completed jobs via Hub API.
    Optionally filter by client code.
    """
    try:
        url = f"{HUB_API_BASE}/api/jobs/all?status=completed"
        if client_code:
            url += f"&client={client_code}"
        
        print(f"[airtable] Fetching completed jobs from Hub")
        
        response = httpx.get(url, timeout=TIMEOUT)
        response.raise_for_status()
        
        jobs = response.json()
        print(f"[airtable] Found {len(jobs)} completed jobs")
        return jobs
        
    except Exception as e:
        print(f"[airtable] Error getting completed jobs from Hub: {e}")
        return []


def get_job_by_number(job_number):
    """
    Get a specific job by its job number via Hub API.
    Returns job dict or None if not found.
    """
    if not job_number:
        return None
    
    try:
        # Normalize job number format (LAB_055 -> LAB 055)
        job_number = job_number.replace('_', ' ').upper()
        
        # URL encode the space
        encoded = job_number.replace(' ', '%20')
        url = f"{HUB_API_BASE}/api/job/{encoded}"
        
        print(f"[airtable] Fetching job {job_number} from Hub")
        
        response = httpx.get(url, timeout=TIMEOUT)
        
        if response.status_code == 404:
            print(f"[airtable] Job {job_number} not found")
            return None
            
        response.raise_for_status()
        return response.json()
        
    except Exception as e:
        print(f"[airtable] Error getting job from Hub: {e}")
        return None


# ===================
# TRAFFIC TABLE (Deduplication & Logging)
# ===================

def check_duplicate(internet_message_id):
    """
    Check if we've already processed this email.
    Returns the existing record if found, None otherwise.
    """
    if not AIRTABLE_API_KEY or not internet_message_id:
        return None
    
    try:
        params = {
            'filterByFormula': f"{{internetMessageId}}='{internet_message_id}'"
        }
        
        response = httpx.get(
            _url(TRAFFIC_TABLE), 
            headers=_headers(), 
            params=params, 
            timeout=TIMEOUT
        )
        response.raise_for_status()
        
        records = response.json().get('records', [])
        return records[0] if records else None
        
    except Exception as e:
        print(f"[airtable] Error checking duplicate: {e}")
        return None


def check_pending_clarify(conversation_id):
    """
    Check if this conversation has a pending clarify request.
    Returns the pending record if found, None otherwise.
    """
    if not AIRTABLE_API_KEY or not conversation_id:
        return None
    
    try:
        filter_formula = f"AND({{conversationId}}='{conversation_id}', {{Status}}='pending')"
        params = {'filterByFormula': filter_formula}
        
        response = httpx.get(
            _url(TRAFFIC_TABLE), 
            headers=_headers(), 
            params=params, 
            timeout=TIMEOUT
        )
        response.raise_for_status()
        
        records = response.json().get('records', [])
        return records[0] if records else None
        
    except Exception as e:
        print(f"[airtable] Error checking pending clarify: {e}")
        return None


def log_traffic(internet_message_id, conversation_id, route, status, job_number, client_code, sender_email, subject):
    """
    Log email to Traffic table.
    Returns the created record ID or None.
    """
    if not AIRTABLE_API_KEY:
        return None
    
    try:
        record_data = {
            'fields': {
                'internetMessageId': internet_message_id or '',
                'conversationId': conversation_id or '',
                'Route': route,
                'Status': status,
                'JobNumber': job_number or '',
                'clientCode': client_code or '',
                'SenderEmail': sender_email or '',
                'Subject': subject or '',
                'CreatedAt': datetime.utcnow().isoformat()
            }
        }
        
        response = httpx.post(
            _url(TRAFFIC_TABLE), 
            headers=_headers(), 
            json=record_data, 
            timeout=TIMEOUT
        )
        
        if response.status_code != 200:
            print(f"[airtable] Traffic log rejected: {response.status_code} - {response.text}")
            return None
        
        return response.json().get('id')
        
    except Exception as e:
        print(f"[airtable] Error logging to Traffic: {e}")
        return None


def update_traffic_record(record_id, updates):
    """
    Update an existing Traffic table record.
    updates: dict of field names to values
    """
    if not AIRTABLE_API_KEY or not record_id:
        return False
    
    try:
        response = httpx.patch(
            f"{_url(TRAFFIC_TABLE)}/{record_id}",
            headers=_headers(),
            json={'fields': updates},
            timeout=TIMEOUT
        )
        response.raise_for_status()
        return True
        
    except Exception as e:
        print(f"[airtable] Error updating Traffic record: {e}")
        return False


# ===================
# PROJECTS TABLE (Write operations only)
# ===================

def get_project(job_number):
    """
    Look up project by job number for routing info (Teams channel, etc).
    This is kept as direct Airtable for routing-specific fields.
    """
    if not AIRTABLE_API_KEY or not job_number:
        return None
    
    try:
        params = {
            'filterByFormula': f"{{Job Number}}='{job_number}'"
        }
        
        response = httpx.get(
            _url(PROJECTS_TABLE), 
            headers=_headers(), 
            params=params, 
            timeout=TIMEOUT
        )
        response.raise_for_status()
        
        records = response.json().get('records', [])
        if not records:
            return None
        
        record = records[0]
        fields = record['fields']
        
        # Client name might be a linked field (list)
        client_name = fields.get('Client', '')
        if isinstance(client_name, list):
            client_name = client_name[0] if client_name else ''
        
        # Extract client code from job number
        client_code = job_number.split()[0] if job_number else None
        
        # Get Team ID from Clients table
        team_id = get_team_id(client_code) if client_code else None
        
        return {
            'recordId': record['id'],
            'jobNumber': fields.get('Job Number', job_number),
            'jobName': fields.get('Project Name', ''),
            'clientName': client_name,
            'clientCode': client_code,
            'stage': fields.get('Stage', ''),
            'status': fields.get('Status', ''),
            'round': fields.get('Round', 0) or 0,
            'withClient': fields.get('With Client?', False),
            'teamsChannelId': fields.get('Teams Channel ID', None),
            'teamId': team_id
        }
        
    except Exception as e:
        print(f"[airtable] Error looking up project: {e}")
        return None


def update_project_record(job_number, updates):
    """
    Update a project's fields by job number.
    Used for direct field updates.
    
    Args:
        job_number: e.g., 'LAB 055'
        updates: dict of Airtable field names to values
    
    Returns:
        dict with 'success': True/False and 'updated': list of field names
    """
    if not AIRTABLE_API_KEY or not job_number:
        return {'success': False, 'error': 'Missing API key or job number'}
    
    try:
        # Find the project record
        params = {
            'filterByFormula': f"{{Job Number}}='{job_number}'",
            'maxRecords': 1
        }
        
        response = httpx.get(
            _url(PROJECTS_TABLE),
            headers=_headers(),
            params=params,
            timeout=TIMEOUT
        )
        response.raise_for_status()
        
        records = response.json().get('records', [])
        if not records:
            return {'success': False, 'error': f'Job {job_number} not found'}
        
        record_id = records[0]['id']
        
        # Update the record
        response = httpx.patch(
            f"{_url(PROJECTS_TABLE)}/{record_id}",
            headers=_headers(),
            json={'fields': updates},
            timeout=TIMEOUT
        )
        response.raise_for_status()
        
        print(f"[airtable] Updated project {job_number}: {list(updates.keys())}")
        return {'success': True, 'updated': list(updates.keys())}
        
    except Exception as e:
        print(f"[airtable] Error updating project record: {e}")
        return {'success': False, 'error': str(e)}


def create_update_record(job_number, update_text, update_due=None):
    """
    Create a new record in the Updates table.
    
    Args:
        job_number: e.g., 'LAB 055' - used to link to project
        update_text: The update message
        update_due: Optional due date (ISO format)
    
    Returns:
        dict with 'success': True/False and 'record_id' if successful
    """
    if not AIRTABLE_API_KEY or not job_number or not update_text:
        return {'success': False, 'error': 'Missing required fields'}
    
    try:
        # First, find the project record ID to link to
        params = {
            'filterByFormula': f"{{Job Number}}='{job_number}'",
            'maxRecords': 1
        }
        
        response = httpx.get(
            _url(PROJECTS_TABLE),
            headers=_headers(),
            params=params,
            timeout=TIMEOUT
        )
        response.raise_for_status()
        
        records = response.json().get('records', [])
        if not records:
            return {'success': False, 'error': f'Project {job_number} not found'}
        
        project_record_id = records[0]['id']
        
        # Build the Updates record
        update_fields = {
            'Update': update_text,
            'Project Link': [project_record_id]  # Linked record field
        }
        
        if update_due:
            update_fields['Update due'] = update_due
        
        # Create the record
        response = httpx.post(
            _url(UPDATES_TABLE),
            headers=_headers(),
            json={'fields': update_fields},
            timeout=TIMEOUT
        )
        response.raise_for_status()
        
        new_record = response.json()
        print(f"[airtable] Created update record for {job_number}: {new_record.get('id')}")
        
        return {'success': True, 'record_id': new_record.get('id')}
        
    except Exception as e:
        print(f"[airtable] Error creating update record: {e}")
        return {'success': False, 'error': str(e)}


# ===================
# CLIENTS TABLE
# ===================

def get_team_id(client_code):
    """
    Look up Team ID from Clients table by client code.
    Returns Team ID string or None.
    """
    if not AIRTABLE_API_KEY or not client_code:
        return None
    
    try:
        params = {
            'filterByFormula': f"{{Client code}}='{client_code}'"
        }
        
        response = httpx.get(
            _url(CLIENTS_TABLE), 
            headers=_headers(), 
            params=params, 
            timeout=TIMEOUT
        )
        response.raise_for_status()
        
        records = response.json().get('records', [])
        if not records:
            return None
        
        return records[0]['fields'].get('Teams ID', None)
        
    except Exception as e:
        print(f"[airtable] Error looking up Team ID: {e}")
        return None


def get_client_name(client_code):
    """
    Look up client name from Clients table by client code.
    Returns client name string or None.
    """
    if not AIRTABLE_API_KEY or not client_code:
        return None
    
    try:
        params = {
            'filterByFormula': f"{{Client code}}='{client_code}'"
        }
        
        response = httpx.get(
            _url(CLIENTS_TABLE), 
            headers=_headers(), 
            params=params, 
            timeout=TIMEOUT
        )
        response.raise_for_status()
        
        records = response.json().get('records', [])
        if not records:
            return None
        
        return records[0]['fields'].get('Clients', None)
        
    except Exception as e:
        print(f"[airtable] Error looking up client name: {e}")
        return None
