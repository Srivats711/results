#!/usr/bin/env python3
import os, time, logging, requests
from bs4 import BeautifulSoup

# ========= FILL THESE IN =========
TELEGRAM_BOT_TOKEN = "8433032956:AAGl8r8US6FGI0L3AG_GTr1WeSa62XqCg8o"
TELEGRAM_CHAT_ID   =  2094491473    # e.g., 2094491473  (integer)
# =================================

# MVSR creds
MVSR_USERNAME = os.getenv("MVSR_USERNAME", "245122737094")
MVSR_PASSWORD = os.getenv("MVSR_PASSWORD", "245122737094")

# Loop frequency (seconds)
LOOP_INTERVAL_SEC = int(os.getenv("LOOP_INTERVAL_SEC", "180"))  # 3 minutes
REQUEST_TIMEOUT   = int(os.getenv("REQUEST_TIMEOUT", "30"))

# URLs
BASE = "http://results.mvsrec.edu.in"
LOGIN_URL = f"{BASE}/SBLogin.aspx"
EXAM_URL  = f"{BASE}/STUDENTLOGIN/Frm_ExamMarksDet.aspx"

HEADERS = {"User-Agent": "Mozilla/5.0", "Origin": BASE, "Referer": LOGIN_URL}
logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)s: %(message)s")

def send_telegram(msg: str):
    if not (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID):
        logging.warning("Missing Telegram token or chat id; skipping send.")
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg}, timeout=REQUEST_TIMEOUT)
    except Exception as e:
        logging.error(f"Telegram send failed: {e}")

def hidden_fields(html: str):
    s = BeautifulSoup(html, "html.parser")
    out = {}
    for name in ["__VIEWSTATE","__VIEWSTATEGENERATOR","__EVENTVALIDATION",
                 "__EVENTTARGET","__EVENTARGUMENT","__SCROLLPOSITIONX","__SCROLLPOSITIONY"]:
        el = s.find("input", {"name": name})
        if el and el.get("value") is not None:
            out[name] = el["value"]
    return out

def find_cgpa(html: str):
    s = BeautifulSoup(html, "html.parser")
    el = s.find("span", {"id": "Stud_cpBody_lblCGPA"})
    return el.text.strip() if el else None

def fetch_current_cgpa() -> str:
    """Login and return CGPA (raises on failure)."""
    with requests.Session() as sess:
        sess.headers.update(HEADERS)

        # 1) GET login page
        r0 = sess.get(LOGIN_URL, timeout=REQUEST_TIMEOUT)
        r0.raise_for_status()
        hidden = hidden_fields(r0.text)

        # 2) POST login (field names from DevTools)
        payload = {
            **hidden,
            "txtUserName": MVSR_USERNAME,
            "txtPassword": MVSR_PASSWORD,
            "btnSubmit": "Login",
        }
        r1 = sess.post(LOGIN_URL, data=payload, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        r1.raise_for_status()
        if "modules.aspx" not in r1.url:
            raise RuntimeError("Login did not redirect to modules.aspx")

        # 3) GET Exam Marks page
        r2 = sess.get(EXAM_URL, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        r2.raise_for_status()
        cgpa = find_cgpa(r2.text)
        if cgpa:
            return cgpa

        # 4) If CGPA not visible, trigger Semester link postback
        hidden2 = hidden_fields(r2.text)
        postback_payload = {**hidden2, "__EVENTTARGET": "ctl00$cpBody$lnkSem", "__EVENTARGUMENT": ""}
        r3 = sess.post(EXAM_URL, data=postback_payload, timeout=REQUEST_TIMEOUT)
        r3.raise_for_status()
        cgpa = find_cgpa(r3.text)
        if not cgpa:
            raise RuntimeError("CGPA span not found after postback")
        return cgpa

if __name__ == "__main__":
    while True:
        try:
            cgpa = fetch_current_cgpa()
            logging.info(f"CGPA: {cgpa}")
            send_telegram(f"📊 Current CGPA: {cgpa}")
        except Exception as e:
            err = f"⚠️ MVSR CGPA check failed: {type(e).__name__}: {e}"
            logging.error(err)
            send_telegram(err)

        time.sleep(LOOP_INTERVAL_SEC)

