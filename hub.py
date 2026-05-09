"""
Dot Hub Brain - Simple Claude + Horoscope Tool
Fast path for Hub requests. Jobs in context, one tool for horoscopes.

SIMPLE CLAUDE:
- Has all jobs in context (summary format for speed)
- One tool: get_horoscope (for fun)
- Answers job questions directly
- Redirects spend/people gracefully
- Fast (~2-3 seconds for most requests)
- Maintains conversation history for context

IMPORTANT: Claude returns job NUMBERS, not full objects.
Frontend matches job numbers to full objects from state.allJobs.
"""

import os
import json
import httpx
from anthropic import Anthropic

# ===================
# CONFIG
# ===================

ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY')
ANTHROPIC_MODEL = 'claude-sonnet-4-6'

# Horoscope service URL (internal call within Brain)
HOROSCOPE_SERVICE_URL = os.environ.get('HOROSCOPE_SERVICE_URL', 'https://dot-workers.up.railway.app')

# Todo worker URL (capture endpoint)
TODO_WORKER_URL = os.environ.get('TODO_WORKER_URL', 'https://dot-workers.up.railway.app')

# Hub URL (for update_todo — calls Hub's /api/todos endpoints)
HUB_API_URL = os.environ.get('HUB_API_URL', 'https://dot.hunch.co.nz')

# Load prompt
PROMPT_PATH = os.path.join(os.path.dirname(__file__), 'prompt_hub.txt')
with open(PROMPT_PATH, 'r') as f:
    HUB_PROMPT = f.read()

# Anthropic client
anthropic_client = Anthropic(
    api_key=ANTHROPIC_API_KEY,
    http_client=httpx.Client(timeout=30.0, follow_redirects=True)
)

# HTTP client for internal calls
http_client = httpx.Client(timeout=10.0)


# ===================
# TOOLS
# ===================

HOROSCOPE_TOOL = {
    "name": "get_horoscope",
    "description": "Get a horoscope for a star sign. Use when someone asks for their horoscope.",
    "input_schema": {
        "type": "object",
        "properties": {
            "sign": {
                "type": "string",
                "description": "The star sign (e.g., 'leo', 'aries', 'pisces')",
                "enum": ["aries", "taurus", "gemini", "cancer", "leo", "virgo", 
                        "libra", "scorpio", "sagittarius", "capricorn", "aquarius", "pisces"]
            }
        },
        "required": ["sign"]
    }
}




SPEND_CHART_TOOL = {
    "name": "get_spend_chart",
    "description": (
        "Generate a YTD monthly-spend bar chart for one Hunch client, with "
        "their monthly committed spend shown as a dotted line. Use this when "
        "the user asks how a client is tracking on spend, asks for a YTD "
        "chart, asks 'show me [client] spend', asks if they're under or over "
        "on a client, or anything else where they want to visualise monthly "
        "billing against commitment. Returns a chart and a one-line summary."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "client_code": {
                "type": "string",
                "description": (
                    "Three-letter client code: TOW (Tower), SKY (Sky), "
                    "ONE (One NZ – Marketing), ONS (One NZ – Simplification), "
                    "ONB (One NZ – Business), FIS (Fisher Funds). "
                    "If the user names a client without specifying which "
                    "One NZ, ask them which one."
                ),
            }
        },
        "required": ["client_code"],
    },
}




HUNCH_SPEND_CHART_TOOL = {
    "name": "get_hunch_spend_chart",
    "description": (
        "Generate a rolling 12-month spend chart for the WHOLE AGENCY "
        "(Hunch). Aggregates spend across all active clients with their "
        "total monthly committed line stepped over time. Use this when the "
        "user asks 'show me Hunch YTD', 'how is Hunch tracking', 'whole of "
        "business YTD', 'all clients combined', or anything where the unit "
        "is the agency rather than one client. No client_code needed — this "
        "tool sums everything itself."
    ),
    "input_schema": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}




CAPTURE_TODO_TOOL = {
    "name": "capture_todo",
    "description": (
        "Capture a to-do dump from the user. Use whenever the user is dumping "
        "a task they want remembered — phrases like 'remind me to...', 'add "
        "to my todo', 'todo:', 'don't forget...', 'don't let me forget...', "
        "or a bare command-form task ('Email Keith re strat pack', 'Book All "
        "Blacks tickets'). Pass the user's full dump straight through — the "
        "worker classifier rewrites the title, picks bucket/client/urgent/"
        "confidence, and may split multiple tasks. Returns the saved record(s)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "dump": {
                "type": "string",
                "description": (
                    "The user's raw todo dump, exactly as they said it. "
                    "Don't rewrite or trim — the classifier handles that."
                ),
            }
        },
        "required": ["dump"],
    },
}




UPDATE_TODO_TOOL = {
    "name": "update_todo",
    "description": (
        "Correct a recently-captured todo. Use when the user replies to a "
        "capture confirmation with a correction like 'not Tower, Labour', "
        "'that's personal not client work', 'make it urgent', or 'should be "
        "\"strategy\" not \"strat\"'. Looks up the most recent matching todo "
        "by title (case-insensitive) and patches the requested fields. Pass "
        "title from the previous turn's confirmation; pass only the new_* "
        "fields the user is correcting."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": (
                    "The current title of the todo to correct. Read it from "
                    "your previous confirmation message — it's quoted there."
                ),
            },
            "new_title": {
                "type": "string",
                "description": "Optional. Replacement title.",
            },
            "new_client_code": {
                "type": "string",
                "description": (
                    "Optional. New 3-letter client code (ONE/ONS/ONB/SKY/TOW/"
                    "FIS/LAB/HUN). Pass empty string to clear the client link."
                ),
            },
            "new_bucket": {
                "type": "string",
                "description": "Optional. CLIENTS or OTHER.",
                "enum": ["CLIENTS", "OTHER"],
            },
            "new_urgent": {
                "type": "boolean",
                "description": "Optional. true to mark urgent, false to unmark.",
            },
        },
        "required": ["title"],
    },
}


# Worker URL — same Railway service as the others
SPEND_CHART_SERVICE_URL = os.environ.get(
    'SPEND_CHART_SERVICE_URL',
    'https://dot-workers.up.railway.app'
)


def call_spend_chart_service(client_code: str) -> dict:
    """Call the spend chart worker. Returns the worker's JSON response,
    or {"error": "..."} if anything went wrong.
    """
    try:
        response = httpx.post(
            f"{SPEND_CHART_SERVICE_URL}/charts/spend",
            json={"client_code": client_code},
            timeout=30.0,
        )
        if response.status_code == 200:
            return response.json()
        try:
            err = response.json().get("error", f"status {response.status_code}")
        except Exception:
            err = f"status {response.status_code}"
        return {"error": err}
    except Exception as e:
        print(f"[hub] Spend chart service error: {e}")
        return {"error": str(e)}





def call_hunch_spend_chart_service() -> dict:
    """Call the Hunch (whole-of-business) spend chart worker."""
    try:
        response = httpx.post(
            f"{SPEND_CHART_SERVICE_URL}/charts/spend/hunch",
            json={},
            timeout=45.0,  # slightly longer — fetches all clients
        )
        if response.status_code == 200:
            return response.json()
        try:
            err = response.json().get("error", f"status {response.status_code}")
        except Exception:
            err = f"status {response.status_code}"
        return {"error": err}
    except Exception as e:
        print(f"[hub] Hunch spend chart service error: {e}")
        return {"error": str(e)}


def call_horoscope_service(sign: str) -> dict:
    """
    Call the horoscope service to get a reading.
    """
    try:
        response = http_client.post(
            f"{HOROSCOPE_SERVICE_URL}/horoscope",
            json={"sign": sign.lower()}
        )
        if response.status_code == 200:
            return response.json()
        else:
            return {"error": f"Service returned {response.status_code}"}
    except Exception as e:
        print(f"[hub] Horoscope service error: {e}")
        return {"error": str(e)}


def call_capture_todo_service(dump: str) -> dict:
    """
    POST a raw dump to the worker /todo endpoint.
    The worker classifies (with its own tool-loop) and writes records.
    Returns the worker's JSON: {success, saved: [...], count, failed?}.
    """
    try:
        response = httpx.post(
            f"{TODO_WORKER_URL}/todo",
            json={"dump": dump},
            timeout=30.0,  # the classifier may run a tool-loop
        )
        if response.status_code == 200:
            return response.json()
        try:
            err = response.json().get("error", f"status {response.status_code}")
        except Exception:
            err = f"status {response.status_code}"
        return {"success": False, "error": err}
    except Exception as e:
        print(f"[hub] Todo capture service error: {e}")
        return {"success": False, "error": str(e)}


# Cached client record IDs for the Client linked field on Todo records.
# Same source as services/todo in dot-workers — kept here because the
# update path goes via Hub's /api/todos and Hub takes a code OR name and
# resolves itself. We only need codes here for validation.
TODO_CLIENT_CODES = ('ONE', 'ONS', 'ONB', 'SKY', 'TOW', 'FIS', 'LAB', 'HUN')


def call_update_todo_service(title: str,
                             new_title: str = None,
                             new_client_code: str = None,
                             new_bucket: str = None,
                             new_urgent: bool = None) -> dict:
    """
    Look up the most recent todo whose title matches `title` (case-insensitive,
    exact match), then PATCH it via Hub's /api/todos/<id> with whichever
    new_* fields were provided.

    Returns: {success, updated: {...} | None, error?}
    """
    # 1. Find the todo
    try:
        list_response = httpx.get(
            f"{HUB_API_URL}/api/todos",
            timeout=10.0,
        )
        if list_response.status_code != 200:
            return {"success": False, "error": f"List failed: {list_response.status_code}"}
        all_todos = list_response.json()
    except Exception as e:
        print(f"[hub] update_todo list error: {e}")
        return {"success": False, "error": f"List failed: {e}"}

    needle = (title or '').strip().lower()
    if not needle:
        return {"success": False, "error": "No title provided"}

    # API already returns newest first — first exact match wins.
    match = None
    for todo in all_todos:
        if (todo.get('title') or '').strip().lower() == needle:
            match = todo
            break

    if not match:
        return {
            "success": False,
            "error": f"No todo found with title '{title}'."
        }

    # 2. Build PATCH payload — only the fields the caller specified
    patch = {}
    if new_title is not None and new_title.strip():
        patch['title'] = new_title.strip()
    if new_client_code is not None:
        # Empty string = clear the link; otherwise validate the code
        if new_client_code == '':
            patch['client'] = ''
        else:
            code = new_client_code.strip().upper()
            if code not in TODO_CLIENT_CODES:
                return {"success": False, "error": f"Unknown client code '{new_client_code}'"}
            patch['client'] = code
    if new_bucket is not None:
        bucket = new_bucket.strip().upper()
        if bucket not in ('CLIENTS', 'OTHER'):
            return {"success": False, "error": f"Bucket must be CLIENTS or OTHER, got '{new_bucket}'"}
        patch['bucket'] = bucket
    if new_urgent is not None:
        patch['urgent'] = bool(new_urgent)

    if not patch:
        return {"success": False, "error": "No fields to update"}

    # 3. PATCH it
    try:
        record_id = match.get('id')
        patch_response = httpx.patch(
            f"{HUB_API_URL}/api/todos/{record_id}",
            json=patch,
            timeout=10.0,
        )
        if patch_response.status_code != 200:
            try:
                err = patch_response.json().get('error', f"status {patch_response.status_code}")
            except Exception:
                err = f"status {patch_response.status_code}"
            return {"success": False, "error": err}
        return {
            "success": True,
            "updated": patch_response.json(),
            "changed_fields": list(patch.keys()),
        }
    except Exception as e:
        print(f"[hub] update_todo patch error: {e}")
        return {"success": False, "error": str(e)}


def handle_tool_call(tool_name: str, tool_input: dict):
    """
    Handle a tool call from Claude.

    Returns:
        (tool_result: str, attachment: dict | None)

    The tool_result is a JSON string fed back to Claude on the second
    API call. The attachment, if any, is attached to the final response
    we return to the Hub — Claude never sees it.
    """
    if tool_name == "get_horoscope":
        sign = tool_input.get("sign", "").lower()
        result = call_horoscope_service(sign)
        if "error" in result:
            return json.dumps({"error": result["error"]}), None
        return json.dumps({
            "message": result.get("message", "The stars are silent today.")
        }), None

    if tool_name == "get_spend_chart":
        client_code = tool_input.get("client_code", "").strip().upper()
        result = call_spend_chart_service(client_code)
        if "error" in result or not result.get("success"):
            err = result.get("error", "Spend chart service failed.")
            return json.dumps({"error": err}), None

        # Hand Claude the summary only. The image rides as an attachment.
        attachment = {
            "type": "chart",
            "imageBase64": result["image_base64"],
            "clientCode": result.get("client_code"),
            "clientName": result.get("client_name"),
            "fyLabel": result.get("fy_label"),
        }
        tool_result = json.dumps({
            "summary": result.get("summary", ""),
            "client_code": result.get("client_code"),
            "client_name": result.get("client_name"),
            "fy_label": result.get("fy_label"),
            "variance": result.get("variance"),
            "chart_rendered": True,
        })
        return tool_result, attachment

    if tool_name == "get_hunch_spend_chart":
        result = call_hunch_spend_chart_service()
        if "error" in result or not result.get("success"):
            err = result.get("error", "Hunch spend chart service failed.")
            return json.dumps({"error": err}), None

        attachment = {
            "type": "chart",
            "imageBase64": result["image_base64"],
            "clientCode": result.get("client_code"),
            "clientName": result.get("client_name"),
            "fyLabel": result.get("fy_label"),
        }
        tool_result = json.dumps({
            "summary": result.get("summary", ""),
            "client_code": result.get("client_code"),
            "client_name": result.get("client_name"),
            "fy_label": result.get("fy_label"),
            "variance": result.get("variance"),
            "chart_rendered": True,
        })
        return tool_result, attachment

    if tool_name == "capture_todo":
        dump = (tool_input.get("dump") or "").strip()
        if not dump:
            return json.dumps({"success": False, "error": "Empty dump"}), None
        result = call_capture_todo_service(dump)
        # Pass the worker's response straight back to Claude — the prompt
        # tells Claude how to summarise the saved record(s) for the user.
        return json.dumps(result), None

    if tool_name == "update_todo":
        title = (tool_input.get("title") or "").strip()
        if not title:
            return json.dumps({"success": False, "error": "No title provided"}), None
        result = call_update_todo_service(
            title=title,
            new_title=tool_input.get("new_title"),
            new_client_code=tool_input.get("new_client_code"),
            new_bucket=tool_input.get("new_bucket"),
            new_urgent=tool_input.get("new_urgent"),
        )
        return json.dumps(result), None

    return json.dumps({"error": f"Unknown tool: {tool_name}"}), None


# ===================
# HELPERS
# ===================

def _strip_markdown_json(content):
    """Strip markdown code blocks and preamble text from Claude's JSON response"""
    content = content.strip()
    
    # Handle markdown code blocks
    if content.startswith('```'):
        content = content.split('\n', 1)[1] if '\n' in content else content[3:]
    if content.endswith('```'):
        content = content.rsplit('```', 1)[0]
    
    # Find JSON object if there's preamble text
    # Look for first { and last }
    first_brace = content.find('{')
    last_brace = content.rfind('}')
    
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        content = content[first_brace:last_brace + 1]
    
    return content.strip()


def _format_jobs_for_context(jobs):
    """
    Format jobs list for Claude's context.
    Compact format to minimize tokens while giving Claude what it needs.
    """
    if not jobs:
        return "No active jobs."
    
    lines = []
    for job in jobs:
        # Core identifiers
        parts = [
            job.get('jobNumber', '???'),
            job.get('jobName', 'Untitled'),
            job.get('clientCode', '?'),
        ]
        
        # Status info
        stage = job.get('stage', '')
        status = job.get('status', '')
        if stage:
            parts.append(stage)
        if status and status != 'In Progress':
            parts.append(status)
        
        # With client flag
        if job.get('withClient'):
            parts.append('WITH CLIENT')
        
        # Dates
        if job.get('updateDue'):
            parts.append(f"Due:{job.get('updateDue')}")
        if job.get('liveDate'):
            parts.append(f"Live:{job.get('liveDate')}")
        
        # Days since update
        days_since = job.get('daysSinceUpdate', '')
        if days_since and days_since != '-':
            parts.append(f"({days_since})")
        
        # Latest update (truncated)
        update = job.get('update', '')
        if update:
            update_short = update[:60] + '...' if len(update) > 60 else update
            parts.append(f'"{update_short}"')
        
        lines.append(' | '.join(parts))
    
    return f"{len(jobs)} active jobs:\n" + "\n".join(lines)


def _format_meetings_for_context(meetings):
    """
    Format meetings for Claude's context.
    Compact format matching jobs style.
    """
    if not meetings:
        return "No upcoming meetings."
    
    lines = []
    for m in meetings:
        day_label = m.get('day', '').upper()  # "TODAY", "TOMORROW", "THURSDAY"
        parts = [
            m.get('startTime', ''), '–', m.get('endTime', ''),
            m.get('title', ''),
        ]
        if m.get('location'):
            parts.append(m.get('location'))
        if m.get('whose'):
            parts.append(f"Organiser:{m.get('whose')}")
        if m.get('attendees'):
            parts.append(f"Attendees:{m.get('attendees')}")
        lines.append(f"{day_label}: {' | '.join(p for p in parts if p)}")
    
    return f"{len(meetings)} meeting(s):\n" + "\n".join(lines)


# ===================
# MAIN HANDLER
# ===================

def handle_hub_request(data):
    """
    Handle a Hub chat request with Simple Claude + Horoscope tool.
    Jobs in context (summary format), one tool for horoscopes.
    Maintains conversation history for multi-turn context.
    
    Args:
        data: dict with content, jobs, senderName, sessionId, history
    
    Returns:
        dict with type, message, jobs (as job numbers), redirectTo, etc.
    """
    content = data.get('content', '')
    jobs = data.get('jobs', [])
    sender_name = data.get('senderName', 'there')
    history = data.get('history', [])  # Conversation history from frontend
    access_level = data.get('accessLevel', 'Client WIP')  # Default to most restricted
    
    # Fetch meetings only for Full access users
    if access_level == 'Full':
        from airtable import get_meetings
        meetings = get_meetings()
    else:
        meetings = []
    
    print(f"[hub] === SIMPLE CLAUDE + TOOLS ===")
    print(f"[hub] Question: {content}")
    print(f"[hub] Jobs in context: {len(jobs)}")
    print(f"[hub] Meetings in context: {len(meetings)}")
    print(f"[hub] History messages: {len(history)}")
    
    # Build context with jobs and meetings (summary only - NOT full JSON)
    jobs_context = _format_jobs_for_context(jobs)
    meetings_context = _format_meetings_for_context(meetings)
    
    # Current message with fresh job data
    current_message = f"""User: {sender_name}
Access Level: {access_level}
Question: {content}

=== ACTIVE JOBS ===
{jobs_context}

=== MEETINGS ===
{meetings_context}
"""
    
    # Build messages array: history + current message
    messages = []
    
    # Add conversation history (without job context - keeps tokens down)
    for msg in history:
        role = msg.get('role', 'user')
        msg_content = msg.get('content', '')
        if role in ['user', 'assistant'] and msg_content:
            messages.append({'role': role, 'content': msg_content})
    
    # Add current message with fresh job context
    messages.append({'role': 'user', 'content': current_message})
    
    try:
        pending_attachment = None  # holds spend-chart PNG if a chart tool fires
        mutated_types = []         # types of data the tools mutated ('todo', 'jobs', etc.)
        # First API call - may return tool use or direct response
        response = anthropic_client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=1500,
            temperature=0.1,
            system=HUB_PROMPT,
            messages=messages,
            tools=[HOROSCOPE_TOOL, SPEND_CHART_TOOL, HUNCH_SPEND_CHART_TOOL, CAPTURE_TODO_TOOL, UPDATE_TODO_TOOL]
        )
        
        # Check if Claude wants to use a tool
        if response.stop_reason == "tool_use":
            # Find the tool use block
            tool_use_block = None
            for block in response.content:
                if block.type == "tool_use":
                    tool_use_block = block
                    break
            
            if tool_use_block:
                print(f"[hub] Tool call: {tool_use_block.name}")
                print(f"[hub] Tool input: {tool_use_block.input}")

                # Note which kind of data this tool touches so the frontend
                # can refresh the right view after the response.
                if tool_use_block.name in ('capture_todo', 'update_todo'):
                    if 'todo' not in mutated_types:
                        mutated_types.append('todo')

                # Execute the tool — may return an attachment for the Hub
                tool_result, pending_attachment = handle_tool_call(
                    tool_use_block.name,
                    tool_use_block.input
                )
                
                # Add assistant's tool request and tool result to messages
                messages.append({
                    "role": "assistant",
                    "content": response.content
                })
                messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": tool_use_block.id,
                        "content": tool_result
                    }]
                })
                
                # Second API call to get final response
                response = anthropic_client.messages.create(
                    model=ANTHROPIC_MODEL,
                    max_tokens=1500,
                    temperature=0.1,
                    system=HUB_PROMPT,
                    messages=messages,
                    tools=[HOROSCOPE_TOOL, SPEND_CHART_TOOL, HUNCH_SPEND_CHART_TOOL, CAPTURE_TODO_TOOL, UPDATE_TODO_TOOL]
                )
        
        # Extract text response
        result_text = ""
        for block in response.content:
            if hasattr(block, 'text'):
                result_text = block.text
                break
        
        result_text = _strip_markdown_json(result_text)
        result = json.loads(result_text)
        
        print(f"[hub] Type: {result.get('type')}")
        print(f"[hub] Message: {result.get('message', '')[:50]}...")
        if result.get('jobs'):
            print(f"[hub] Jobs returned: {result.get('jobs')}")

        # Attach the spend chart PNG if the tool was used
        if pending_attachment:
            result['attachment'] = pending_attachment
            if pending_attachment.get('type') == 'chart':
                result['type'] = 'chart'

        # Tell the frontend what to refresh (e.g. ['todo'] after a capture)
        if mutated_types:
            result['mutated'] = mutated_types

        return result
        
    except json.JSONDecodeError as e:
        print(f"[hub] JSON error: {e}")
        print(f"[hub] Raw response: {result_text[:200] if result_text else 'empty'}")
        # If Claude returned plain text, treat it as an answer
        if result_text and result_text.strip():
            return {
                'type': 'answer',
                'message': result_text.strip(),
                'jobs': None,
                'nextPrompt': None
            }
        return {
            'type': 'answer',
            'message': "Sorry, I got in a muddle over that one.",
            'jobs': None,
            'nextPrompt': "Try asking another way?"
        }
        
    except Exception as e:
        print(f"[hub] Error: {e}")
        import traceback
        traceback.print_exc()
        return {
            'type': 'answer', 
            'message': "Sorry, I got in a muddle over that one.",
            'jobs': None,
            'nextPrompt': "Try asking another way?"
        }
