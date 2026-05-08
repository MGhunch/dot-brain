"""
Dot Workers - Airtable Utils
Shared data lookups for all workers.
"""

import os
import re
import httpx
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# ===================
# CONFIG
# ===================

AIRTABLE_API_KEY = os.environ.get('AIRTABLE_API_KEY')
AIRTABLE_BASE_ID = os.environ.get('AIRTABLE_BASE_ID', 'app8CI7NAZqhQ4G1Y')

TRAFFIC_TABLE = 'Traffic'
PROJECTS_TABLE = 'Projects'
UPDATES_TABLE = 'Updates'
CLIENTS_TABLE = 'Clients'
TRACKER_TABLE = 'Tracker'
MEETINGS_TABLE = 'Meetings'

TIMEOUT = 10.0
NZ_TZ = ZoneInfo('Pacific/Auckland')


def _headers():
    return {
        'Authorization': f'Bearer {AIRTABLE_API_KEY}',
        'Content-Type': 'application/json'
    }


def _url(table):
    return f'https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{table}'


def _get_current_quarter():
    """Get current quarter string (e.g., 'Jan-Mar', 'Apr-Jun')"""
    month = datetime.now().month
    if month <= 3:
        return 'Jan-Mar'
    elif month <= 6:
        return 'Apr-Jun'
    elif month <= 9:
        return 'Jul-Sep'
    else:
        return 'Oct-Dec'


def _get_current_month():
    """Get current month name (e.g., 'January')"""
    return datetime.now().strftime('%B')


# ===================
# CLIENTS TABLE
# ===================

def get_client_sharepoint(client_code):
    """
    Look up SharePoint URL from Clients table by client code.
    Returns SharePoint URL string or None.
    
    The field in Airtable is called 'Sharepoint ID' and contains
    URLs like 'https://hunch.sharepoint.com/sites/OneNZ'
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
            print(f"[airtable] No client found for code: {client_code}")
            return None
        
        sharepoint_url = records[0]['fields'].get('Sharepoint ID', None)
        
        if not sharepoint_url:
            print(f"[airtable] No SharePoint URL configured for: {client_code}")
            
        return sharepoint_url
        
    except Exception as e:
        print(f"[airtable] Error looking up client SharePoint: {e}")
        return None


def get_next_job_number(client_code):
    """
    Get next job number for a client and increment the counter.
    
    Reads 'Next Job #' (e.g., "LAB 056") and increments 'Next #' for next time.
    
    Returns tuple: (job_number, client_record_id, team_id, error)
    - job_number: e.g., "LAB 056"
    - client_record_id: Airtable record ID for the client
    - team_id: Teams ID for this client
    - error: error message or None
    """
    if not AIRTABLE_API_KEY or not client_code:
        return None, None, None, "Missing API key or client code"
    
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
            return None, None, None, f"Client '{client_code}' not found"
        
        record = records[0]
        record_id = record['id']
        fields = record['fields']
        
        # Get the formatted job number (e.g., "LAB 056")
        job_number = fields.get('Next Job #', None)
        if not job_number:
            return None, None, None, f"No 'Next Job #' configured for {client_code}"
        
        # Get current counter to increment
        current_counter = fields.get('Next #', 0)
        team_id = fields.get('Teams ID', None)
        
        # Increment the counter for next time
        response = httpx.patch(
            f"{_url(CLIENTS_TABLE)}/{record_id}",
            headers=_headers(),
            json={'fields': {'Next #': current_counter + 1}},
            timeout=TIMEOUT
        )
        response.raise_for_status()
        
        print(f"[airtable] Reserved job number: {job_number}, incremented to {current_counter + 1}")
        return job_number, record_id, team_id, None
        
    except Exception as e:
        return None, None, None, f"Error reserving job number: {str(e)}"


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


# ===================
# TRAFFIC TABLE
# ===================

def get_email_body(internet_message_id):
    """
    Retrieve email body from Traffic table.
    Brain logs it there when email arrives.
    """
    if not AIRTABLE_API_KEY or not internet_message_id:
        print(f"[airtable] Missing API key or message ID")
        return None
    
    try:
        params = {
            'filterByFormula': f"{{internetMessageId}}='{internet_message_id}'",
            'maxRecords': 1
        }
        
        response = httpx.get(
            _url(TRAFFIC_TABLE), 
            headers=_headers(), 
            params=params, 
            timeout=TIMEOUT
        )
        response.raise_for_status()
        
        records = response.json().get('records', [])
        if not records:
            print(f"[airtable] No traffic record found for {internet_message_id[:50]}...")
            return None
        
        email_body = records[0]['fields'].get('EmailBody', None)
        print(f"[airtable] Found email body: {len(email_body) if email_body else 0} chars")
        return email_body
        
    except Exception as e:
        print(f"[airtable] Error getting email body: {e}")
        return None


# ===================
# PROJECTS TABLE
# ===================

def get_project(job_number):
    """
    Look up a job by job number.
    Returns tuple: (record_id, project_info, error)
    """
    if not AIRTABLE_API_KEY or not job_number:
        return None, None, "Missing API key or job number"
    
    try:
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
            return None, None, f"Job '{job_number}' not found"
        
        record = records[0]
        record_id = record['id']
        fields = record['fields']
        
        # Extract Team ID from Channel URL
        channel_url = fields.get('Channel Url', '')
        team_id = None
        if channel_url:
            import re
            match = re.search(r'groupId=([a-f0-9-]+)', channel_url)
            if match:
                team_id = match.group(1)
        
        project_info = {
            'recordId': record_id,
            'jobNumber': job_number,
            'projectName': fields.get('Project Name', 'Unknown'),
            'stage': fields.get('Stage', 'Unknown'),
            'status': fields.get('Status', 'Unknown'),
            'withClient': fields.get('With Client?', False),
            'currentUpdate': fields.get('Update', ''),
            'channelId': fields.get('Teams Channel ID', None),
            'channelUrl': channel_url or None,
            'filesUrl': fields.get('Files Url', None),
            'teamId': team_id
        }
        
        return record_id, project_info, None
        
    except Exception as e:
        return None, None, f"Error looking up job: {str(e)}"


def create_project(job_number, job_name, description=None,
                   owner=None, stage='Triage', status='Incoming',
                   update_due=None, live_date=None):
    """
    Create a new project record.
    
    Args:
        job_number: e.g., 'LAB 056'
        job_name: e.g., 'Election Campaign'
        description: job description/brief summary
        owner: client contact name
        stage: default 'Triage'
        status: default 'Incoming'
        update_due: ISO date string
        live_date: month string (e.g., 'Feb', 'Tbc')
    
    Returns tuple: (record_id, error)
    
    Note: Client field is a formula (auto-populated from Job Number).
          Budget/costs go to the Tracker table, not here.
    """
    if not AIRTABLE_API_KEY:
        return None, "Missing API key"
    
    if not job_number or not job_name:
        return None, "Missing job number or job name"
    
    try:
        fields = {
            'Job Number': job_number,
            'Project Name': job_name,
            'Stage': stage,
            'Status': status,
        }
        
        # Note: Client field is a formula - don't write to it
        
        # Optional fields
        if description:
            fields['Description'] = description
        if owner:
            fields['Project Owner'] = owner
        if update_due:
            fields['Update Due'] = update_due
        if live_date:
            fields['Live'] = live_date
        
        print(f"[airtable] Creating project: {job_number} - {job_name}")
        print(f"[airtable] Fields: {list(fields.keys())}")
        
        response = httpx.post(
            _url(PROJECTS_TABLE),
            headers=_headers(),
            json={'fields': fields},
            timeout=TIMEOUT
        )
        response.raise_for_status()
        
        new_record = response.json()
        record_id = new_record.get('id')
        
        print(f"[airtable] Created project: {record_id}")
        return record_id, None
        
    except Exception as e:
        return None, f"Error creating project: {str(e)}"


# Map of python kwarg names → Airtable field names
# Add new fields here as needed — unknown kwargs are silently skipped
PROJECT_FIELD_MAP = {
    'update': 'Update',
    'update_due': 'Update Due',
    'status': 'Status',
    'stage': 'Stage',
    'with_client': 'With Client?',
    'round': 'Round',
    'description': 'Description',
    'the_story': 'The Story',
    'live': 'Live',
    'project_owner': 'Project Owner',
    'project_name': 'Project Name',
    'teams_channel_id': 'Teams Channel ID',
    'channel_url': 'Channel Url',
    'files_url': 'Files Url',
    'update_history': 'Update History',
}

# Values to treat as "no real value"
_SKIP_VALUES = {'Unknown', 'unknown', '', None}


def update_project(job_record_id, **kwargs):
    """
    Update a project record.
    Pass any known fields as kwargs — unknown keys are silently skipped.
    Returns tuple: (success, error)
    """
    if not AIRTABLE_API_KEY or not job_record_id:
        return False, "Missing API key or job record ID"

    try:
        fields = {}
        for key, value in kwargs.items():
            airtable_field = PROJECT_FIELD_MAP.get(key)
            if not airtable_field:
                print(f"[airtable] update_project: skipping unknown field '{key}'")
                continue
            # Skip empty/unknown values (but allow False for checkboxes)
            if value in _SKIP_VALUES and value is not False:
                continue
            fields[airtable_field] = value

        if not fields:
            return True, None

        response = httpx.patch(
            f"{_url(PROJECTS_TABLE)}/{job_record_id}",
            headers=_headers(),
            json={'fields': fields},
            timeout=TIMEOUT
        )
        response.raise_for_status()

        return True, None

    except Exception as e:
        return False, f"Error updating project: {str(e)}"


# ===================
# TRACKER TABLE
# ===================

def create_tracker(project_record_id, spend=None, spend_type='Project budget',
                   month=None, quarter=None, notes=None, ballpark=False):
    """
    Create a new tracker record linked to a project.
    
    The Link field links to Projects - most other fields are lookups from that.
    
    Args:
        project_record_id: Airtable record ID of the project
        spend: dollar amount as number (e.g., 5000) or string (e.g., '$5,000')
        spend_type: 'Project budget', 'Extra budget', or 'Project on us'
        month: e.g., 'January' (defaults to current month)
        quarter: e.g., 'Jan-Mar' (defaults to current quarter)
        notes: tracker notes
        ballpark: boolean - True if spend is an estimate (checkbox field)
    
    Returns tuple: (record_id, error)
    """
    if not AIRTABLE_API_KEY or not project_record_id:
        return None, "Missing API key or project record ID"
    
    try:
        # Use defaults if not provided
        if not month:
            month = _get_current_month()
        if not quarter:
            quarter = _get_current_quarter()
        
        fields = {
            'Link': [project_record_id],  # Linked record to Projects
            'Spend type': spend_type,
            'Month': month,
            'Quarter': quarter,
        }
        
        # Handle spend - convert string to number if needed
        if spend:
            if isinstance(spend, str):
                # Strip $ and commas, convert to number
                spend_clean = spend.replace('$', '').replace(',', '').strip()
                try:
                    spend = int(float(spend_clean))
                except ValueError:
                    spend = None
            
            if spend:
                fields['Spend'] = spend  # Send raw number, Airtable formats it
        
        # Ballpark is a checkbox - True if this is an estimate
        if ballpark:
            fields['Ballpark'] = True
        
        if notes:
            fields['Tracker notes'] = notes
        
        print(f"[airtable] Creating tracker record for project: {project_record_id}")
        
        response = httpx.post(
            _url(TRACKER_TABLE),
            headers=_headers(),
            json={'fields': fields},
            timeout=TIMEOUT
        )
        response.raise_for_status()
        
        new_record = response.json()
        record_id = new_record.get('id')
        
        print(f"[airtable] Created tracker: {record_id}")
        return record_id, None
        
    except Exception as e:
        return None, f"Error creating tracker: {str(e)}"


# ===================
# UPDATES TABLE
# ===================

def write_update(job_record_id, update_text, update_due=None):
    """
    Write an update to the Updates table.
    Returns tuple: (record_id, error)
    """
    if not AIRTABLE_API_KEY or not job_record_id:
        return None, "Missing API key or job record ID"
    
    try:
        update_data = {
            'fields': {
                'Project Link': [job_record_id],
                'Update': update_text
            }
        }
        
        if update_due:
            update_data['fields']['Update Due'] = update_due
        
        response = httpx.post(
            _url(UPDATES_TABLE), 
            headers=_headers(), 
            json=update_data, 
            timeout=TIMEOUT
        )
        response.raise_for_status()
        
        new_record = response.json()
        return new_record.get('id'), None
        
    except Exception as e:
        return None, f"Error writing update: {str(e)}"


# ===================
# WIP EMAIL DATA
# ===================

def get_jobs_for_client(client_code):
    """
    Get active jobs for a client (for WIP email).
    
    Returns jobs grouped by section:
    {
        'with_hunch': [...],   # In Progress, not with client
        'with_you': [...],     # With Client? = true
        'on_hold': [...],      # On Hold
        'upcoming': [...]      # Incoming
    }
    
    Excludes: Always on, Completed
    """
    if not AIRTABLE_API_KEY or not client_code:
        return {'with_hunch': [], 'with_you': [], 'on_hold': [], 'upcoming': []}
    
    try:
        filter_formula = f"AND(OR({{Status}}='In Progress', {{Status}}='On Hold', {{Status}}='Incoming'), FIND('{client_code}', {{Job Number}}))"
        
        params = {'filterByFormula': filter_formula}
        all_records = []
        offset = None
        
        while True:
            if offset:
                params['offset'] = offset
            
            response = httpx.get(
                _url(PROJECTS_TABLE),
                headers=_headers(),
                params=params,
                timeout=TIMEOUT
            )
            response.raise_for_status()
            data = response.json()
            all_records.extend(data.get('records', []))
            
            offset = data.get('offset')
            if not offset:
                break
        
        with_hunch = []
        with_you = []
        on_hold = []
        upcoming = []
        
        for record in all_records:
            fields = record.get('fields', {})
            status = fields.get('Status', '')
            
            # Skip Always on
            if status == 'Always on':
                continue
            
            job = {
                'jobNumber': fields.get('Job Number', ''),
                'jobName': fields.get('Project Name', ''),
                'description': fields.get('Description', ''),
                'update': fields.get('Update', ''),
                'status': status,
                'withClient': fields.get('With Client?', False),
            }
            
            # Route to section
            if status == 'On Hold':
                on_hold.append(job)
            elif status == 'Incoming':
                upcoming.append(job)
            elif job['withClient']:
                with_you.append(job)
            else:
                with_hunch.append(job)
        
        # Sort each section by job number
        for section in [with_hunch, with_you, on_hold, upcoming]:
            section.sort(key=lambda x: x.get('jobNumber', ''))
        
        total = len(with_hunch) + len(with_you) + len(on_hold) + len(upcoming)
        print(f"[airtable] WIP jobs for {client_code}: {total} total ({len(with_hunch)} hunch, {len(with_you)} client, {len(on_hold)} hold, {len(upcoming)} upcoming)")
        
        return {
            'with_hunch': with_hunch,
            'with_you': with_you,
            'on_hold': on_hold,
            'upcoming': upcoming
        }
    
    except Exception as e:
        print(f"[airtable] Error fetching WIP jobs: {e}")
        return {'with_hunch': [], 'with_you': [], 'on_hold': [], 'upcoming': []}


# ===================
# DATE HELPERS (NZ)
# ===================

def get_nz_today():
    """Get today's date in NZ timezone."""
    return datetime.now(NZ_TZ).date()


def get_next_workday():
    """
    Get next working day. Mon-Thu: tomorrow. Fri-Sun: Monday.
    Returns: (date, label)
    """
    today = get_nz_today()
    weekday = today.weekday()  # Mon=0, Sun=6
    
    if weekday == 4:  # Friday
        return today + timedelta(days=3), 'Monday'
    elif weekday == 5:  # Saturday
        return today + timedelta(days=2), 'Monday'
    elif weekday == 6:  # Sunday
        return today + timedelta(days=1), 'Monday'
    else:
        return today + timedelta(days=1), 'Tomorrow'


def get_end_of_week():
    """
    Get end of work week for "coming up" section.
    
    Mon-Wed: returns this Friday
    Thu-Fri: returns NEXT Friday (so we show "Coming up next week")
    Sat-Sun: returns next Friday
    
    Returns: (date, label)
    """
    today = get_nz_today()
    weekday = today.weekday()  # Mon=0, Sun=6
    
    if weekday <= 2:  # Mon-Wed: this Friday
        days_until_friday = 4 - weekday
        return today + timedelta(days=days_until_friday), 'Coming up this week'
    elif weekday <= 4:  # Thu-Fri: next Friday
        days_until_next_friday = 11 - weekday
        return today + timedelta(days=days_until_next_friday), 'Coming up next week'
    else:  # Sat-Sun: next Friday
        days_until_friday = 11 - weekday
        return today + timedelta(days=days_until_friday), 'Coming up next week'


def parse_meeting_datetime(dt_str):
    """
    Parse meeting datetime from Airtable API (UTC) and convert to NZ time.
    Returns: (date, time_str) or (None, '')
    """
    if not dt_str:
        return None, ''
    
    # ISO format from API: "2026-02-02T00:00:00.000Z"
    iso_match = re.match(r'(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})', dt_str)
    if iso_match:
        y, mo, d = int(iso_match.group(1)), int(iso_match.group(2)), int(iso_match.group(3))
        h, mi = int(iso_match.group(4)), int(iso_match.group(5))
        utc_dt = datetime(y, mo, d, h, mi, tzinfo=ZoneInfo('UTC'))
        nz_dt = utc_dt.astimezone(NZ_TZ)
        period = 'am' if nz_dt.hour < 12 else 'pm'
        display_h = nz_dt.hour % 12 or 12
        return nz_dt.date(), f"{display_h}:{nz_dt.minute:02d}{period}"
    
    return None, ''


def parse_airtable_date(date_str):
    """
    Parse Airtable date field into date object.
    Handles: ISO "2026-01-31", D/M/YYYY "31/1/2026"
    """
    if not date_str or str(date_str).upper() == 'TBC':
        return None
    
    date_str = str(date_str).strip()
    
    # ISO format (YYYY-MM-DD)
    iso_match = re.search(r'^(\d{4})-(\d{2})-(\d{2})', date_str)
    if iso_match:
        try:
            return datetime.strptime(iso_match.group(0), '%Y-%m-%d').date()
        except ValueError:
            return None
    
    # D/M/YYYY format
    dmy_match = re.search(r'(\d{1,2})/(\d{1,2})/(\d{4})', date_str)
    if dmy_match:
        day, month, year = int(dmy_match.group(1)), int(dmy_match.group(2)), int(dmy_match.group(3))
        try:
            return datetime(year, month, day).date()
        except ValueError:
            return None
    
    return None


# ===================
# TO DO DATA
# ===================

def get_todo_jobs():
    """
    Get jobs due for TO DO email.
    
    Returns: {
        'today': [...],      # Overdue + due today
        'tomorrow': [...],   # Due tomorrow (or Monday if Friday)
        'week': [...],       # Rest of week (after tomorrow, up to end date)
        'week_label': '...'  # "Coming up this week" or "Coming up next week"
    }
    
    Excludes jobs where With Client? = True
    """
    if not AIRTABLE_API_KEY:
        print("[airtable] Missing API key")
        return {'today': [], 'tomorrow': [], 'week': [], 'week_label': ''}
    
    try:
        today = get_nz_today()
        next_day, _ = get_next_workday()
        end_of_week, week_label = get_end_of_week()
        
        # Fetch active jobs with Update Due set
        params = {
            'filterByFormula': "AND(OR({Status}='In Progress', {Status}='Incoming'), {Update Due}!='')"
        }
        
        response = httpx.get(
            _url(PROJECTS_TABLE),
            headers=_headers(),
            params=params,
            timeout=TIMEOUT
        )
        response.raise_for_status()
        
        today_jobs = []
        tomorrow_jobs = []
        week_jobs = []
        
        for record in response.json().get('records', []):
            fields = record.get('fields', {})
            
            # Skip if with client
            if fields.get('With Client?', False):
                continue
            
            # Parse update due date
            update_due = parse_airtable_date(fields.get('Update Due', ''))
            if not update_due:
                continue
            
            job = {
                'jobNumber': fields.get('Job Number', ''),
                'jobName': fields.get('Project Name', ''),
                'description': fields.get('Description', ''),
                'updateDue': update_due.isoformat(),
                'channelUrl': fields.get('Channel Url', ''),
                'projectOwner': fields.get('Project Owner', ''),
            }
            
            # Categorize by due date
            if update_due <= today:
                job['status'] = 'Overdue' if update_due < today else 'Due today'
                today_jobs.append(job)
            elif update_due == next_day:
                job['status'] = 'Due tomorrow'
                tomorrow_jobs.append(job)
            elif update_due <= end_of_week:
                job['status'] = update_due.strftime('%a')  # "Fri", "Mon", etc.
                week_jobs.append(job)
        
        # Sort by due date
        today_jobs.sort(key=lambda x: x.get('updateDue', ''))
        tomorrow_jobs.sort(key=lambda x: x.get('updateDue', ''))
        week_jobs.sort(key=lambda x: x.get('updateDue', ''))
        
        print(f"[airtable] TO DO jobs: {len(today_jobs)} today, {len(tomorrow_jobs)} tomorrow, {len(week_jobs)} week")
        return {'today': today_jobs, 'tomorrow': tomorrow_jobs, 'week': week_jobs, 'week_label': week_label}
    
    except Exception as e:
        print(f"[airtable] Error fetching todo jobs: {e}")
        return {'today': [], 'tomorrow': [], 'week': [], 'week_label': ''}


def get_meetings():
    """
    Get meetings for today and next workday.
    
    Returns: {
        'today': [...],
        'tomorrow': [...]
    }
    """
    if not AIRTABLE_API_KEY:
        print("[airtable] Missing API key")
        return {'today': [], 'tomorrow': []}
    
    try:
        today_date = get_nz_today()
        next_day, _ = get_next_workday()
        
        response = httpx.get(
            _url(MEETINGS_TABLE),
            headers=_headers(),
            timeout=TIMEOUT
        )
        response.raise_for_status()
        
        today_meetings = []
        tomorrow_meetings = []
        
        for record in response.json().get('records', []):
            fields = record.get('fields', {})
            
            start_str = fields.get('Start', '')
            end_str = fields.get('End', '')
            meeting_date, start_time = parse_meeting_datetime(start_str)
            _, end_time = parse_meeting_datetime(end_str)
            
            if not meeting_date:
                continue
            
            meeting = {
                'id': record.get('id'),
                'title': fields.get('Title', ''),
                'startTime': start_time,
                'endTime': end_time,
                'location': fields.get('Location', ''),
                'whose': fields.get('Whose meeting', '') or 'Michael',
            }
            
            if meeting_date == today_date:
                today_meetings.append(meeting)
            elif meeting_date == next_day:
                tomorrow_meetings.append(meeting)
        
        # Sort by start time
        today_meetings.sort(key=lambda x: x.get('startTime', ''))
        tomorrow_meetings.sort(key=lambda x: x.get('startTime', ''))
        
        print(f"[airtable] Meetings: {len(today_meetings)} today, {len(tomorrow_meetings)} tomorrow")
        return {'today': today_meetings, 'tomorrow': tomorrow_meetings}
    
    except Exception as e:
        print(f"[airtable] Error fetching meetings: {e}")
        return {'today': [], 'tomorrow': []}


# ===================
# SPEND CHART HELPERS
# ===================

def get_client_for_chart(client_code):
    """
    Fetch the client metadata needed to build a YTD spend chart.

    Returns dict with: code, name, year_end (month name string),
    monthly_committed (currency as float). Returns None if not found.
    """
    if not AIRTABLE_API_KEY or not client_code:
        return None

    try:
        params = {
            'filterByFormula': f"{{Client code}}='{client_code}'",
            'maxRecords': 1,
        }
        response = httpx.get(
            _url(CLIENTS_TABLE),
            headers=_headers(),
            params=params,
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        records = response.json().get('records', [])
        if not records:
            return None

        fields = records[0].get('fields', {})
        return {
            'code': fields.get('Client code', client_code),
            'name': fields.get('Clients', client_code),
            'year_end': fields.get('Year end'),
            'monthly_committed': float(fields.get('Monthly Committed') or 0),
        }
    except Exception as e:
        print(f"[airtable] Error fetching client {client_code}: {e}")
        return None


def get_all_clients_for_chart():
    """
    Fetch ALL clients from the Clients table with the metadata needed
    to build a Hunch-wide YTD chart.

    Returns list of dicts with: code, name, year_end (month name string),
    monthly_committed (currency as float). Used by the Hunch (whole-of-
    business) handler to roll up spend across all active clients.
    """
    if not AIRTABLE_API_KEY:
        return []

    try:
        all_records = []
        params = {'pageSize': 100}
        offset = None
        while True:
            if offset:
                params['offset'] = offset
            response = httpx.get(
                _url(CLIENTS_TABLE),
                headers=_headers(),
                params=params,
                timeout=TIMEOUT,
            )
            response.raise_for_status()
            data = response.json()
            all_records.extend(data.get('records', []))
            offset = data.get('offset')
            if not offset:
                break

        out = []
        for record in all_records:
            fields = record.get('fields', {})
            code = fields.get('Client code')
            if not code:
                continue
            out.append({
                'code': code,
                'name': fields.get('Clients', code),
                'year_end': fields.get('Year end'),
                'monthly_committed': float(fields.get('Monthly Committed') or 0),
            })

        print(f"[airtable] Fetched {len(out)} clients for Hunch chart")
        return out

    except Exception as e:
        print(f"[airtable] Error fetching all clients: {e}")
        return []


def get_tracker_for_client(client_code):
    """
    Fetch all Tracker records for one client.

    Returns list of dicts with: spend (float), month (string), createdTime
    (ISO 8601 string). Filters server-side on the {Client Code} formula
    field, paginates with offset, and only keeps Project budget entries
    (matches the Hub's tracker.py spend rule — Extra budget and Project
    on us don't count toward committed-spend tracking).
    """
    if not AIRTABLE_API_KEY or not client_code:
        return []

    try:
        # Server-side filter on Tracker's Client Code formula field.
        # Also restrict to Project budget so we match Hub tracker semantics.
        formula = (
            f"AND("
            f"{{Client Code}}='{client_code}',"
            f"{{Spend type}}='Project budget'"
            f")"
        )
        params = {'filterByFormula': formula, 'pageSize': 100}
        all_records = []
        offset = None

        while True:
            if offset:
                params['offset'] = offset
            response = httpx.get(
                _url(TRACKER_TABLE),
                headers=_headers(),
                params=params,
                timeout=TIMEOUT,
            )
            response.raise_for_status()
            data = response.json()
            all_records.extend(data.get('records', []))
            offset = data.get('offset')
            if not offset:
                break

        out = []
        for record in all_records:
            fields = record.get('fields', {})
            spend = fields.get('Spend')
            if spend is None:
                continue
            # Spend can be a number or a string (Airtable currency formatting)
            if isinstance(spend, str):
                try:
                    spend = float(spend.replace('$', '').replace(',', '').strip())
                except ValueError:
                    continue
            out.append({
                'spend': float(spend),
                'month': fields.get('Month'),
                'createdTime': record.get('createdTime'),
            })

        print(f"[airtable] Tracker records for {client_code}: {len(out)} (Project budget only)")
        return out

    except Exception as e:
        print(f"[airtable] Error fetching tracker for {client_code}: {e}")
        return []


def get_budget_history_for_client(client_code):
    """
    Fetch all Budget History records for one client.

    Returns list of dicts with: client (string), effective_from (ISO date
    string 'YYYY-MM-DD'), monthly_committed (float), sorted by
    effective_from ascending.

    Budget History is the source of truth for committed spend per period.
    A renegotiation creates a new row with Effective From = first day the
    new amount applies. The Clients table's Monthly Committed is just the
    most recent value (and may lag — treat Budget History as canonical).
    """
    if not AIRTABLE_API_KEY or not client_code:
        return []

    try:
        # Budget History uses 'Client' (not 'Client code') as the key field —
        # see schema. It's a multilineText field, so an exact-match formula:
        params = {
            'filterByFormula': f"{{Client}}='{client_code}'",
            'pageSize': 100,
        }
        all_records = []
        offset = None

        while True:
            if offset:
                params['offset'] = offset
            response = httpx.get(
                _url('Budget History'),
                headers=_headers(),
                params=params,
                timeout=TIMEOUT,
            )
            response.raise_for_status()
            data = response.json()
            all_records.extend(data.get('records', []))
            offset = data.get('offset')
            if not offset:
                break

        out = []
        for record in all_records:
            fields = record.get('fields', {})
            eff = fields.get('Effective From')
            committed = fields.get('Monthly Committed')
            if not eff or committed is None:
                continue
            out.append({
                'client': fields.get('Client', client_code),
                'effective_from': eff,  # ISO date string 'YYYY-MM-DD'
                'monthly_committed': float(committed),
            })

        out.sort(key=lambda r: r['effective_from'])
        print(f"[airtable] Budget History for {client_code}: {len(out)} records")
        return out

    except Exception as e:
        print(f"[airtable] Error fetching Budget History for {client_code}: {e}")
        return []
