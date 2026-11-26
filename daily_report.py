"""Builds and emails the daily status bulletin from the ledger.
  python daily_report.py            -> send email
  python daily_report.py --dry-run  -> write preview.html only"""
import os, sys, smtplib, ssl
import datetime as dt
from html import escape
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import ledger

COLORS = {"Completed": "#1a7f37", "In Progress": "#9a6700", "Blocked": "#cf222e", "Queued": "#57606a"}


def parse(s):
    try:
        return dt.datetime.strptime(str(s), ledger.FMT)
    except ValueError:
        return None


def table(headers, rows):
    if not rows:
        return '<p style="color:#57606a;margin:4px 0">None</p>'
    th = "".join(f'<th style="text-align:left;padding:6px;background:#f6f8fa;border:1px solid #d0d7de">{escape(h)}</th>' for h in headers)
    body = ""
    for r in rows:
        body += "<tr>" + "".join(f'<td style="padding:6px;border:1px solid #d0d7de">{c}</td>' for c in r) + "</tr>"
    return f'<table style="border-collapse:collapse;font-size:13px;width:100%"><tr>{th}</tr>{body}</table>'


def badge(text, status):
    return f'<b style="color:{COLORS[status]}">{escape(text)}</b>'


def build_html(rows, now):
    today = now.date()
    by = lambda s: [r for r in rows if r["Status"] == s]
    completed_today = [r for r in by("Completed")
                       if (parse(r["Completion Time"]) or dt.datetime.min).date() == today]
    in_prog, blocked, queued = by("In Progress"), by("Blocked"), by("Queued")

    def basic(r):
        link = str(r.get("Output / Result Link", ""))
        out = f'<a href="{escape(link)}">link</a>' if link.startswith("http") else escape(link)
        return [escape(str(r["Task ID"])), escape(r["Agent Name"]), escape(r["Title"] or r["Task Description"]),
                escape(r["Priority"]), out]

    # Per-employee KPIs
    kpi_rows = []
    for a in ledger.AGENTS:
        mine = [r for r in rows if r["Agent Name"] == a]
        done = [r for r in mine if r["Status"] == "Completed"]
        done_t = [r for r in done if (parse(r["Completion Time"]) or dt.datetime.min).date() == today]
        durs = []
        for r in done:
            s, e = parse(r["Timestamp"]), parse(r["Completion Time"])
            if s and e:
                durs.append((e - s).total_seconds() / 3600)
        avg = f"{sum(durs) / len(durs):.1f} h" if durs else "-"
        total = len(mine)
        rate = f"{round(100 * len(done) / total)}%" if total else "-"
        kpi_rows.append([escape(a), str(len(done_t)), str(sum(r["Status"] == "In Progress" for r in mine)),
                         str(sum(r["Status"] == "Blocked" for r in mine)),
                         str(sum(r["Status"] == "Queued" for r in mine)), avg, rate])

    blocked_rows = [basic(r)[:4] + [escape(str(r.get("Notes") or "No reason logged"))] for r in blocked]

    h = lambda t: f'<h3 style="margin:22px 0 6px">{t}</h3>'
    return f"""<div style="font-family:Arial,sans-serif;max-width:760px;color:#1f2328">
<h2 style="margin-bottom:4px">Daily Agency Bulletin</h2>
<div style="color:#57606a">{now.strftime('%A, %d %B %Y')}</div>
<p style="font-size:15px;margin:14px 0">
{badge(f'{len(completed_today)} completed today', 'Completed')} &nbsp;|&nbsp;
{badge(f'{len(in_prog)} in progress', 'In Progress')} &nbsp;|&nbsp;
{badge(f'{len(blocked)} blocked', 'Blocked')} &nbsp;|&nbsp;
{badge(f'{len(queued)} queued', 'Queued')}</p>
{h('Completed today')}{table(['ID','Employee','Task','Priority','Output'], [basic(r) for r in completed_today])}
{h('In progress')}{table(['ID','Employee','Task','Priority','Output'], [basic(r) for r in in_prog])}
{h('Blocked (needs attention)')}{table(['ID','Employee','Task','Priority','Reason'], blocked_rows)}
{h('Employee KPIs')}{table(['Employee','Done today','In progress','Blocked','Queued','Avg completion','Completion rate'], kpi_rows)}
<p style="color:#57606a;font-size:12px;margin-top:20px">Sent automatically by the Project Manager. Source: live Google Sheet ledger.</p>
</div>"""


def send(subject, html):
    user, pwd, to = os.environ["GMAIL_USER"], os.environ["GMAIL_APP_PASSWORD"], os.environ["BOSS_EMAIL"]
    msg = MIMEMultipart("alternative")
    msg["Subject"], msg["From"], msg["To"] = subject, user, to
    msg.attach(MIMEText("Open this email in an HTML-capable client to view the bulletin.", "plain"))
    msg.attach(MIMEText(html, "html"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context()) as s:
        s.login(user, pwd)
        s.sendmail(user, [to], msg.as_string())


if __name__ == "__main__":
    now = ledger.now()
    html = build_html(ledger.get_tasks(), now)
    if "--dry-run" in sys.argv:
        open("preview.html", "w").write(html)
        print("Wrote preview.html")
    else:
        send(f"Daily Agency Bulletin - {now.strftime('%d %b %Y')}", html)
        print("Email sent")
