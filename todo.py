"""
Dot Todo Classifier
Receives a raw todo dump (from skill or forwarded email).
Classifies via Claude, writes to Airtable, returns confirmation.

PATTERN:
- Receive: {text, sender_email}
- Classify: Claude returns JSON {title, bucket, client_code, urgent}
- Write: airtable.create_todo()
- Return: {success, message, todo}

Mirrors hub.py's simple pattern. Tools reused from traffic.py for client lookup.

ARCHITECTURE: Dot Thinks. Workers Work. Airtable Remembers.
The skill is just a courier. Brain classifies. Airtable stores.
"""

import os
import json
import httpx
from anthropic import Anthropic

import airtable
import traffic  # for tool functions and CLAUDE_TOOLS subset

# ===================
# CONFIG
# ===================

ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY')
ANTHROPIC_MODEL = 'claude-sonnet-4-6'

# Load prompt
PROMPT_PATH = os.path.join(os.path.dirname(__file__), 'prompt_todo.txt')
with open(PROMPT_PATH, 'r') as f:
    TODO_PROMPT = f.read()

# Anthropic client
anthropic_client = Anthropic(
    api_key=ANTHROPIC_API_KEY,
    http_client=httpx.Client(timeout=30.0, follow_redirects=True)
)

# ===================
# TOOLS
# ===================
# Reuse a subset of traffic.py's tools - just the lookup ones.
# No write tools - the backend handles the Airtable write.

TODO_TOOLS = [
    tool for tool in traffic.CLAUDE_TOOLS
    if tool['name'] in ('search_people', 'get_client_detail')
]


# ===================
# HELPERS
# ===================

def _strip_markdown_json(content):
    """Strip markdown fences and any preamble from Claude's JSON response."""
    content = content.strip()
    if content.startswith('```'):
        content = content.split('\n', 1)[1] if '\n' in content else content[3:]
    if content.endswith('```'):
        content = content.rsplit('```', 1)[0]
    first_brace = content.find('{')
    last_brace = content.rfind('}')
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        content = content[first_brace:last_brace + 1]
    return content.strip()


def _build_confirmation(classification, todo_record):
    """Build a friendly confirmation message for the caller."""
    title = classification.get('title', 'todo')
    bucket = classification.get('bucket', 'OTHER')
    client_code = classification.get('client_code')
    urgent = classification.get('urgent', False)

    parts = [f"Got it. Added '{title}' to {bucket}"]
    if client_code:
        parts.append(f"({client_code})")
    if urgent:
        parts.append("- marked urgent")
    return ' '.join(parts) + '.'


# ===================
# MAIN HANDLER
# ===================

def handle_todo_request(data):
    """
    Classify a todo dump and write to Airtable.

    Args:
        data: dict with at minimum {text}, optionally {sender_email}

    Returns:
        dict with:
        - success: bool
        - message: confirmation string for the caller
        - todo: the classified todo dict (or None on failure)
    """
    text = (data.get('text') or '').strip()
    sender_email = data.get('sender_email', '')

    if not text:
        return {'success': False, 'message': 'No text provided.', 'todo': None}

    print(f"[todo] === CLASSIFYING ===")
    print(f"[todo] Text: {text}")
    print(f"[todo] Sender: {sender_email}")

    user_message = f"Sender: {sender_email or 'unknown'}\nDump: {text}"

    messages = [{'role': 'user', 'content': user_message}]

    try:
        response = anthropic_client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=1000,
            temperature=0.1,
            system=TODO_PROMPT,
            messages=messages,
            tools=TODO_TOOLS
        )

        # Tool loop - keep going until Claude returns final JSON
        max_rounds = 3
        rounds = 0
        while response.stop_reason == 'tool_use' and rounds < max_rounds:
            rounds += 1

            # Append assistant turn
            messages.append({'role': 'assistant', 'content': response.content})

            # Execute each tool call and build the user turn
            tool_results = []
            for block in response.content:
                if block.type == 'tool_use':
                    print(f"[todo] Tool: {block.name} input: {block.input}")
                    result = traffic.execute_tool(block.name, block.input)
                    tool_results.append({
                        'type': 'tool_result',
                        'tool_use_id': block.id,
                        'content': json.dumps(result)
                    })

            messages.append({'role': 'user', 'content': tool_results})

            response = anthropic_client.messages.create(
                model=ANTHROPIC_MODEL,
                max_tokens=1000,
                temperature=0.1,
                system=TODO_PROMPT,
                messages=messages,
                tools=TODO_TOOLS
            )

        # Extract final text
        result_text = ''
        for block in response.content:
            if hasattr(block, 'text') and block.text:
                result_text = block.text
                break

        if not result_text:
            print(f"[todo] No text in final response (stop_reason={response.stop_reason})")
            return {'success': False, 'message': 'Sorry, I got in a muddle classifying that.', 'todo': None}

        # Parse JSON
        cleaned = _strip_markdown_json(result_text)
        classification = json.loads(cleaned)

        # Validate
        title = (classification.get('title') or '').strip()
        bucket = (classification.get('bucket') or 'OTHER').upper()
        if bucket not in ('CLIENTS', 'OTHER'):
            bucket = 'OTHER'
        client_code = (classification.get('client_code') or '').strip().upper() or None
        urgent = bool(classification.get('urgent', False))

        if not title:
            return {'success': False, 'message': 'Could not extract a title from that.', 'todo': None}

        print(f"[todo] Classified: title='{title}' bucket={bucket} client={client_code} urgent={urgent}")

        # Write to Airtable
        write_result = airtable.create_todo(
            title=title,
            bucket=bucket,
            client_code=client_code,
            urgent=urgent
        )

        if not write_result.get('success'):
            error = write_result.get('error', 'unknown error')
            print(f"[todo] Write failed: {error}")
            return {
                'success': False,
                'message': f"Classified it but couldn't save: {error}",
                'todo': None
            }

        # Build confirmation
        normalised = {
            'title': title,
            'bucket': bucket,
            'client_code': client_code,
            'urgent': urgent
        }
        message = _build_confirmation(normalised, write_result.get('todo'))

        return {
            'success': True,
            'message': message,
            'todo': write_result.get('todo'),
            'classification': normalised
        }

    except json.JSONDecodeError as e:
        print(f"[todo] JSON parse error: {e}")
        print(f"[todo] Raw: {result_text[:200] if result_text else 'empty'}")
        return {
            'success': False,
            'message': "Sorry, I got in a muddle classifying that.",
            'todo': None
        }
    except Exception as e:
        print(f"[todo] Error: {e}")
        import traceback
        traceback.print_exc()
        return {
            'success': False,
            'message': "Sorry, something went wrong adding that todo.",
            'todo': None
        }
