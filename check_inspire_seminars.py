import json, os, sys, ssl, smtplib, urllib.request
from email.message import EmailMessage
from datetime import datetime, timezone

API_URL = os.environ.get(
    "INSPIRE_API_URL",
    "https://inspirehep.net/api/seminars?sort=dateasc&size=25&page=1&start_date=upcoming",
)
SEEN_PATH = "seen.json"

SMTP_SERVER = os.environ["SMTP_SERVER"]
SMTP_PORT = int(os.environ.get("SMTP_PORT", "465"))
SMTP_USERNAME = os.environ["SMTP_USERNAME"]
SMTP_PASSWORD = os.environ["SMTP_PASSWORD"]
MAIL_FROM = os.environ["MAIL_FROM"]
MAIL_TO = [x.strip() for x in os.environ["MAIL_TO"].split(",") if x.strip()]

def http_get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))

def load_seen() -> set[str]:
    if not os.path.exists(SEEN_PATH):
        return set()
    with open(SEEN_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return set(data.get("seen_ids", []))

def save_seen(seen: set[str]) -> None:
    with open(SEEN_PATH, "w", encoding="utf-8") as f:
        json.dump(
            {"seen_ids": sorted(seen), "updated_at": datetime.now(timezone.utc).isoformat()},
            f,
            ensure_ascii=False,
            indent=2,
        )

def pick_fields(hit: dict):
    sid = str(hit.get("id") or hit.get("control_number") or "")
    md = hit.get("metadata", {}) if isinstance(hit.get("metadata", {}), dict) else {}
    title = md.get("title") or (md.get("titles", [{}])[0].get("title") if isinstance(md.get("titles"), list) else None) or "Seminar"
    dt = md.get("start_datetime") or md.get("date") or md.get("start_date") or ""
    url = f"https://inspirehep.net/seminars/{sid}" if sid else "https://inspirehep.net/seminars"
    return sid, title, dt, url

def send_one_email(subject: str, body: str):
    msg = EmailMessage()
    msg["From"] = MAIL_FROM
    msg["To"] = ", ".join(MAIL_TO)
    msg["Subject"] = subject
    msg.set_content(body)

    if SMTP_PORT == 465:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, context=context, timeout=30) as s:
            s.login(SMTP_USERNAME, SMTP_PASSWORD)
            s.send_message(msg)
    else:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=30) as s:
            s.ehlo()
            s.starttls(context=ssl.create_default_context())
            s.login(SMTP_USERNAME, SMTP_PASSWORD)
            s.send_message(msg)

def main():
    data = http_get_json(API_URL)
    hits = (((data.get("hits") or {}).get("hits")) or [])
    if not isinstance(hits, list):
        print("Unexpected API shape", file=sys.stderr)
        sys.exit(1)

    seen = load_seen()
    new_items = []
    for h in hits:
        if not isinstance(h, dict):
            continue
        sid, title, dt, url = pick_fields(h)
        if sid and sid not in seen:
            new_items.append((sid, title, dt, url))

    if not new_items:
        print("No new seminars.")
        return

    for sid, title, dt, url in new_items:
        subject = f"[INSPIRE] {title}"
        body = f"{title}\n\n" + (f"time: {dt}\n" if dt else "") + f"link: {url}\n\nsource: {API_URL}\n"
        send_one_email(subject, body)
        seen.add(sid)
        save_seen(seen)

    print(f"Sent {len(new_items)} emails.")

if __name__ == "__main__":
    main()
