import imaplib
import email
import re


def get_body(msg):
    """Extract plain-text body from email message."""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    return payload.decode("utf-8", errors="ignore")
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            return payload.decode("utf-8", errors="ignore")
    return ""


def get_kbank_balance(gmail_user, gmail_pass):
    """
    Scrape latest KBank available balance from the most recent
    KPLUS notification email. Returns float (THB) or None.
    """
    mail = imaplib.IMAP4_SSL("imap.gmail.com")
    mail.login(gmail_user, gmail_pass)
    mail.select("inbox")
    _, data = mail.search(None, 'FROM "KPLUS@kasikornbank.com"')
    ids = data[0].split()
    if not ids:
        mail.logout()
        return None

    _, msg_data = mail.fetch(ids[-1], "(RFC822)")
    msg = email.message_from_bytes(msg_data[0][1])
    body = get_body(msg)
    mail.logout()

    match = re.search(r'Available Balance\s*\(THB\)\s*:\s*([\d,]+\.\d{2})', body)
    if match:
        return float(match.group(1).replace(",", ""))
    return None
