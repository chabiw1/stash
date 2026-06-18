import imaplib
import email
import email.utils
import re
import json
import os
import io
from datetime import date, datetime
from dateutil.relativedelta import relativedelta

import PyPDF2
import pdfplumber
import yfinance as yf


GMAIL_USER = os.environ.get("GMAIL_USER", "")
GMAIL_PASS = os.environ.get("GMAIL_PASS", "")
DOB = os.environ.get("DOB", "")  # DDMMYYYY format

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORTFOLIO_PATH = os.path.join(BASE_DIR, "data", "portfolio.json")


def load_json(path):
    with open(path) as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_email_body(msg):
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    return payload.decode("utf-8", errors="ignore")
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                payload = part.get_payload(decode=True)
                if payload:
                    return payload.decode("utf-8", errors="ignore")
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            return payload.decode("utf-8", errors="ignore")
    return ""


def fetch_gmail_by_subject(subject_keyword):
    """Search Gmail inbox for messages matching subject keyword."""
    mail = imaplib.IMAP4_SSL("imap.gmail.com")
    mail.login(GMAIL_USER, GMAIL_PASS)
    mail.select("inbox")
    _, data = mail.search(None, f'SUBJECT "{subject_keyword}"')
    ids = data[0].split()
    messages = []
    for uid in ids:
        _, msg_data = mail.fetch(uid, "(RFC822)")
        msg = email.message_from_bytes(msg_data[0][1])
        messages.append(msg)
    mail.logout()
    return messages


def decrypt_pdf(pdf_data, dob):
    """Decrypt password-protected PDF and return decrypted bytes."""
    reader = PyPDF2.PdfReader(io.BytesIO(pdf_data))
    if reader.is_encrypted:
        reader.decrypt(dob)
    writer = PyPDF2.PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def extract_pdf_text(pdf_data, dob):
    """Extract all text from PDF, decrypting first if needed."""
    decrypted = decrypt_pdf(pdf_data, dob)
    with pdfplumber.open(io.BytesIO(decrypted)) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)


def get_pdf_from_msg(msg):
    """Return PDF attachment bytes from email message, or None."""
    for part in msg.walk():
        filename = part.get_filename() or ""
        content_type = part.get_content_type()
        if content_type == "application/pdf" or filename.lower().endswith(".pdf"):
            return part.get_payload(decode=True)
    return None


def parse_statement_month(subject):
    """Parse statement month from email subject. Returns a date(year, month, 1) or None."""
    # "Monthly Statement August 2025" / "Aug 2025" / "08/2025"
    for fmt in ("%B %Y", "%b %Y"):
        match = re.search(r'([A-Za-z]{3,9})\s+(\d{4})', subject)
        if match:
            try:
                return datetime.strptime(f"{match.group(1)} {match.group(2)}", fmt).date().replace(day=1)
            except ValueError:
                continue
    match = re.search(r'(\d{1,2})[/\-](\d{4})', subject)
    if match:
        return date(int(match.group(2)), int(match.group(1)), 1)
    return None


def last_day_of_month(d):
    next_month = d.replace(day=28) + relativedelta(days=4)
    return (next_month.replace(day=1) - relativedelta(days=1))


def parse_monthly_statement(text):
    """
    Parse Dime monthly statement PDF text.
    Returns (holdings_dict, dime_cash_usd).
    holdings_dict: {symbol: {shares, avg_cost_usd, asset_type}}
    """
    holdings = {}
    current_type = None

    for line in text.split("\n"):
        stripped = line.strip()

        # Detect asset type section headers (Thai + English)
        if re.search(r'หุ้นสามัญ|Common Stock', stripped):
            current_type = "stock"
            continue
        if re.search(r'กองทุน ETF|ETF Fund', stripped):
            current_type = "etf"
            continue
        # Reset on other major section headers
        if re.search(r'Summary|สรุป|Total|รวม', stripped) and current_type:
            if not re.match(r'^[A-Z]{1,5}\s', stripped):
                current_type = None
            continue

        if current_type is None:
            continue

        # Match: SYMBOL  shares  avg_cost  [other fields...]
        # PDF rows often: "TSLA 0.5164601 290.40 ..."
        match = re.match(
            r'^([A-Z]{1,5})\s+([\d,]+\.[\d]+)\s+([\d,]+\.[\d]+)',
            stripped
        )
        if match:
            symbol = match.group(1)
            shares = float(match.group(2).replace(",", ""))
            avg_cost = float(match.group(3).replace(",", ""))
            holdings[symbol] = {
                "shares": shares,
                "avg_cost_usd": avg_cost,
                "asset_type": current_type,
            }

    # Parse Cash Balance USD
    dime_cash_usd = 0.0
    patterns = [
        r'Cash Balance\s*[\d,]+\s*USD\s*([\d,]+\.\d+)\s*USD',
        r'Cash Balance[^\n]*?\s([\d,]+\.\d{2})\s*USD',
        r'Cash\s+Balance\s+([\d,]+\.\d{2})',
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            dime_cash_usd = float(m.group(1).replace(",", ""))
            break

    return holdings, dime_cash_usd


def get_last_month_statement():
    """
    Fetch the most recent Dime monthly statement from Gmail.
    Returns dict with statement_date, dime_cash_usd, holdings or None.
    """
    msgs = fetch_gmail_by_subject("Monthly Statement")
    if not msgs:
        return None

    latest_msg = None
    latest_month = None
    for msg in msgs:
        subject = msg.get("Subject", "")
        month_start = parse_statement_month(subject)
        if month_start and (latest_month is None or month_start > latest_month):
            latest_month = month_start
            latest_msg = msg

    if not latest_msg or not latest_month:
        return None

    pdf_data = get_pdf_from_msg(latest_msg)
    if not pdf_data:
        return None

    text = extract_pdf_text(pdf_data, DOB)
    holdings, dime_cash_usd = parse_monthly_statement(text)

    statement_date = last_day_of_month(latest_month)
    return {
        "statement_date": str(statement_date),
        "dime_cash_usd": dime_cash_usd,
        "holdings": holdings,
    }


def parse_confirmation_note(text):
    """
    Parse trade rows from a Dime confirmation note PDF.
    Returns list of {symbol, action, shares, price_usd}.
    """
    trades = []
    for line in text.split("\n"):
        stripped = line.strip()
        match = re.match(
            r'(BUY|SEL|SELL)\s+([A-Z]{1,5})\s+([\d,]+\.[\d]+)\s+([\d,]+\.[\d]+)',
            stripped, re.IGNORECASE
        )
        if match:
            action = match.group(1).upper()
            if action == "SELL":
                action = "SEL"
            trades.append({
                "symbol": match.group(2).upper(),
                "action": action,
                "shares": float(match.group(3).replace(",", "")),
                "price_usd": float(match.group(4).replace(",", "")),
            })
    return trades


def get_this_month_trades(cutoff_date):
    """
    Fetch all Dime confirmation note PDFs from Gmail after cutoff_date.
    Returns combined list of trades.
    """
    msgs = fetch_gmail_by_subject("Confirmation Note")
    all_trades = []
    for msg in msgs:
        date_str = msg.get("Date", "")
        try:
            msg_date = email.utils.parsedate_to_datetime(date_str).date()
        except Exception:
            continue
        if msg_date <= cutoff_date:
            continue
        pdf_data = get_pdf_from_msg(msg)
        if not pdf_data:
            continue
        text = extract_pdf_text(pdf_data, DOB)
        trades = parse_confirmation_note(text)
        all_trades.extend(trades)
    return all_trades


def merge_portfolio(holdings_dict, new_trades):
    """
    Apply new_trades onto holdings_dict.
    holdings_dict: {symbol: {shares, avg_cost_usd, asset_type}}
    BUY → weighted average cost; SEL → subtract shares, remove if <= 0.
    Returns updated dict.
    """
    portfolio = {k: dict(v) for k, v in holdings_dict.items()}

    for trade in new_trades:
        symbol = trade["symbol"]
        action = trade["action"]
        qty = trade["shares"]
        price = trade["price_usd"]

        if action == "BUY":
            if symbol in portfolio:
                old = portfolio[symbol]
                new_shares = old["shares"] + qty
                new_cost = (old["shares"] * old["avg_cost_usd"] + qty * price) / new_shares
                portfolio[symbol] = {
                    "shares": new_shares,
                    "avg_cost_usd": new_cost,
                    "asset_type": old.get("asset_type", "stock"),
                }
            else:
                try:
                    info = yf.Ticker(symbol).fast_info
                    asset_type = "etf" if getattr(info, "quote_type", "").upper() == "ETF" else "stock"
                except Exception:
                    asset_type = "stock"
                portfolio[symbol] = {
                    "shares": qty,
                    "avg_cost_usd": price,
                    "asset_type": asset_type,
                }
        elif action == "SEL":
            if symbol in portfolio:
                new_shares = portfolio[symbol]["shares"] - qty
                if new_shares <= 0:
                    del portfolio[symbol]
                else:
                    portfolio[symbol]["shares"] = new_shares

    return portfolio


def last_day_of_current_month():
    return last_day_of_month(date.today())


def run_daily(portfolio_path):
    data = load_json(portfolio_path)
    current_month_end = last_day_of_current_month()

    if data.get("statement_date") != str(current_month_end):
        holdings_data = get_last_month_statement()
        if holdings_data:
            data.update(holdings_data)
            save_json(portfolio_path, data)

    cutoff = date.fromisoformat(data["statement_date"])
    new_trades = get_this_month_trades(cutoff)
    if new_trades:
        merged = merge_portfolio(data["holdings"], new_trades)
        data["holdings"] = merged
        save_json(portfolio_path, data)


if __name__ == "__main__":
    run_daily(PORTFOLIO_PATH)
