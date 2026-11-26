"""Ledger bridge: the Project Manager's read/write layer for the Google Sheet.
Every other part of the system (workers, dashboard, chat, email) uses this file,
so the Sheet stays the single source of truth."""
import os, json, datetime as dt
from zoneinfo import ZoneInfo

TAB = "Ledger"
FMT = "%Y-%m-%d %H:%M:%S"

# First 9 columns are the required ones. The last 3 are extras the dashboard needs.
HEADERS = [
    "Task ID", "Timestamp", "Assigned By", "Agent Name", "Task Description",
    "Priority", "Status", "Output / Result Link", "Completion Time",
    "Title", "Deadline", "Notes",
]
STATUSES = ["Queued", "In Progress", "Blocked", "Completed"]
PRIORITIES = ["Low", "Medium", "High", "Urgent"]

# Edit to match your 7+1 team
AGENTS = [
    "Project Manager", "Client Intake Agent", "Event Concept Planner",
    "Venue Scout", "Vendor Coordinator", "Budget Analyst",
    "Promotions Writer", "Feedback & Reporting Agent",
]


def now():
    return dt.datetime.now(ZoneInfo(os.environ.get("TIMEZONE", "UTC"))).replace(tzinfo=None)


def _worksheet():
    import gspread
    from google.oauth2.service_account import Credentials
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    info = json.loads(os.environ["GOOGLE_CREDS_JSON"])
    gc = gspread.authorize(Credentials.from_service_account_info(info, scopes=scopes))
    sh = gc.open_by_key(os.environ["SHEET_ID"])
    try:
        ws = sh.worksheet(TAB)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(TAB, rows=1000, cols=len(HEADERS))
    if ws.row_values(1) != HEADERS:
        ws.update(range_name="A1:L1", values=[HEADERS])
    return ws


def get_tasks():
    """All tasks as a list of dicts keyed by header name."""
    return _worksheet().get_all_records(expected_headers=HEADERS)


def _next_id(ws):
    nums = [int(v[2:]) for v in ws.col_values(1)[1:] if v.startswith("T-") and v[2:].isdigit()]
    return f"T-{(max(nums) if nums else 0) + 1:04d}"


def add_task(title, description, agent, assigned_by="Boss", priority="Medium",
             deadline="", status="Queued"):
    """Log a new task. Returns its Task ID."""
    if agent not in AGENTS:
        raise ValueError(f"Unknown agent: {agent}")
    if priority not in PRIORITIES or status not in STATUSES:
        raise ValueError("Invalid priority or status")
    ws = _worksheet()
    tid = _next_id(ws)
    ws.append_row(
        [tid, now().strftime(FMT), assigned_by, agent, description, priority,
         status, "", "", title, deadline, ""],
        value_input_option="USER_ENTERED",
    )
    return tid


def update_task(task_id, status=None, output_link=None, notes=None):
    """Change a task's status/output/notes. Completed stamps Completion Time."""
    ws = _worksheet()
    cell = ws.find(task_id, in_column=1)
    if cell is None:
        raise KeyError(f"{task_id} not found")
    row = cell.row
    updates = []
    def put(name, value):
        updates.append({"range": f"{chr(65 + HEADERS.index(name))}{row}", "values": [[value]]})
    if status:
        if status not in STATUSES:
            raise ValueError(f"Status must be one of {STATUSES}")
        put("Status", status)
        if status == "Completed":
            put("Completion Time", now().strftime(FMT))
    if output_link is not None:
        put("Output / Result Link", output_link)
    if notes is not None:
        put("Notes", notes)  # for Blocked tasks, put the reason here
    ws.batch_update(updates, value_input_option="USER_ENTERED")


if __name__ == "__main__":
    # Quick connection test:  python ledger.py
    tid = add_task("Connection test", "Test row from ledger.py", "Project Manager", "Boss", "Low")
    print("Created", tid)
