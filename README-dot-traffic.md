# dot-traffic-2.0

The brain of Dot. Routes emails and Hub messages through Claude, decides what to do, calls workers.

---

## Files

### app.py
**Job:** Flask server with HTTP endpoints. Receives requests from PA Listener (email) or Hub, passes to the brain, returns responses.  
**Connects with:** traffic.py (brain), airtable.py (logging), connect.py (workers)

---

### traffic.py
**Job:** The Claude brain. Analyzes messages, uses tools to fetch data, decides routing (answer, action, clarify, redirect). Manages conversation memory for Hub sessions.  
**Connects with:** Claude API, airtable.py (for tools), called by app.py

---

### airtable.py
**Job:** Airtable operations - check duplicates, log to Traffic table, get projects/clients, create update records.  
**Connects with:** Airtable API, used by traffic.py tools

---

### connect.py
**Job:** Connections to worker services - Teams channel posting, file routing signals.  
**Connects with:** Proxy service, Power Automate flows, and more

---

### prompt_unified.txt
**Job:** System prompt for Claude. Defines Dot's personality, available tools, response formats, routing logic.  
**Connects with:** Loaded by traffic.py, sent to Claude API

---

### SCHEMA.md
**Job:** Documentation of the universal job schema and data structures.  
**Connects with:** Reference for developers

---

## Architecture

```
Email (PA Listener) ──→ /traffic ──→ Claude Brain ──→ Workers
                              ↓              ↓
Hub (Ask Dot) ─────────→ /traffic ──→ Claude Brain ──→ Response to Hub
                                           ↓
                                    Airtable (logging)
```

---

## Key Endpoints

| Endpoint | Purpose |
|----------|---------|
| `/traffic` | Main routing - receives email or Hub message, returns Claude's decision |
| `/traffic/clear` | Clear conversation memory for a Hub session |
| `/health` | Health check |

---

## How It Works

1. **Gate checks** - Ignore self-emails, check sender domain, deduplicate
2. **Pending clarify?** - Check if this is a reply to a clarification request
3. **Claude decides** - Uses tools (get_active_jobs, search_people, etc.) to understand context
4. **Log to Traffic** - Record the routing decision in Airtable
5. **Route response** - Email source → call workers; Hub source → return JSON to frontend
