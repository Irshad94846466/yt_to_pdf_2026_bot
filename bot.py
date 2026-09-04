import os
import re
import time
import threading
import requests

from flask import Flask
from youtube_transcript_api import YouTubeTranscriptApi
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


# =========================
# SETTINGS
# =========================

BOT_TOKEN = os.environ.get("BOT_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is missing")

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

app = Flask(__name__)


# =========================
# HEALTH CHECK
# =========================

@app.route("/")
def home():
    return "YouTube PDF Bot is running!"


# =========================
# YOUTUBE VIDEO ID
# =========================

def get_video_id(url):
    patterns = [
        r"(?:youtube\.com/watch\?v=)([A-Za-z0-9_-]{11})",
        r"(?:youtu\.be/)([A-Za-z0-9_-]{11})",
        r"(?:youtube\.com/shorts/)([A-Za-z0-9_-]{11})",
        r"(?:youtube\.com/embed/)([A-Za-z0-9_-]{11})"
    ]

    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)

    return None


# =========================
# GET TRANSCRIPT
# =========================

def get_transcript(video_id):

    api = YouTubeTranscriptApi()

    # Hindi first, then English
    languages = ["hi", "en"]

    try:
        transcript = api.fetch(
            video_id,
            languages=languages
        )

        text = []

        for item in transcript:
            text.append(item.text)

        return " ".join(text)

    except Exception:

        # Try any available transcript
        try:
            transcript_list = api.list(video_id)

            for transcript in transcript_list:
                fetched = transcript.fetch()

                text = []

                for item in fetched:
                    text.append(item.text)

                return " ".join(text)

        except Exception as e:
            raise Exception(
                "Is video ka transcript/captions available nahi hai."
            ) from e


# =========================
# CREATE PDF
# =========================

def create_pdf(text, video_url):

    filename = f"/tmp/youtube_notes_{int(time.time())}.pdf"

    # Try Unicode font
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans.ttf"
    ]

    font_name = "Helvetica"

    for path in font_paths:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(
                    TTFont("DejaVu", path)
                )
                font_name = "DejaVu"
                break
            except Exception:
                pass

    doc = SimpleDocTemplate(
        filename,
        pagesize=A4,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "TitleCustom",
        parent=styles["Title"],
        fontName=font_name,
        fontSize=18,
        alignment=TA_CENTER,
        spaceAfter=20
    )

    body_style = ParagraphStyle(
        "BodyCustom",
        parent=styles["BodyText"],
        fontName=font_name,
        fontSize=10,
        leading=16,
        spaceAfter=8
    )

    story = []

    story.append(
        Paragraph(
            "YouTube Video Transcript",
            title_style
        )
    )

    story.append(
        Paragraph(
            f"Source: {video_url}",
            body_style
        )
    )

    story.append(Spacer(1, 15))

    # Split transcript into manageable paragraphs
    words = text.split()

    chunk = []

    for word in words:

        chunk.append(word)

        if len(chunk) >= 80:

            paragraph = " ".join(chunk)

            # Escape special HTML characters
            paragraph = (
                paragraph
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )

            story.append(
                Paragraph(
                    paragraph,
                    body_style
                )
            )

            chunk = []

    if chunk:

        paragraph = " ".join(chunk)

        paragraph = (
            paragraph
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

        story.append(
            Paragraph(
                paragraph,
                body_style
            )
        )

    doc.build(story)

    return filename


# =========================
# TELEGRAM FUNCTIONS
# =========================

def send_message(chat_id, text):

    requests.post(
        f"{TELEGRAM_API}/sendMessage",
        data={
            "chat_id": chat_id,
            "text": text
        },
        timeout=30
    )


def send_pdf(chat_id, filename):

    with open(filename, "rb") as pdf:

        requests.post(
            f"{TELEGRAM_API}/sendDocument",
            data={
                "chat_id": chat_id,
                "caption": "📄 Aapka YouTube PDF ready hai!"
            },
            files={
                "document": pdf
            },
            timeout=120
        )


# =========================
# HANDLE MESSAGE
# =========================

def process_message(message):

    chat_id = message["chat"]["id"]

    text = message.get("text", "").strip()

    if text == "/start":

        send_message(
            chat_id,
            "👋 Welcome!\n\n"
            "Mujhe YouTube video ka link bhejo.\n\n"
            "Main available transcript ko PDF mein convert karke bhej dunga. 📄"
        )

        return

    if not text.startswith("http"):

        send_message(
            chat_id,
            "❌ Please YouTube video ka link bhejo."
        )

        return

    video_id = get_video_id(text)

    if not video_id:

        send_message(
            chat_id,
            "❌ Ye valid YouTube link nahi lag raha."
        )

        return

    send_message(
        chat_id,
        "⏳ Video ka transcript nikala ja raha hai..."
    )

    try:

        transcript = get_transcript(video_id)

        if not transcript:
            raise Exception("Empty transcript")

        send_message(
            chat_id,
            "📄 PDF banaya ja raha hai..."
        )

        pdf_file = create_pdf(
            transcript,
            text
        )

        send_pdf(
            chat_id,
            pdf_file
        )

        try:
            os.remove(pdf_file)
        except Exception:
            pass

    except Exception as e:

        print("ERROR:", e)

        send_message(
            chat_id,
            "❌ Is video ka transcript available nahi mila.\n\n"
            "Kisi doosre YouTube video ka link try karo."
        )


# =========================
# TELEGRAM LONG POLLING
# =========================

def bot_loop():

    offset = None

    while True:

        try:

            response = requests.get(
                f"{TELEGRAM_API}/getUpdates",
                params={
                    "timeout": 50,
                    "offset": offset
                },
                timeout=60
            )

            data = response.json()

            if not data.get("ok"):
                time.sleep(5)
                continue

            for update in data["result"]:

                offset = update["update_id"] + 1

                if "message" in update:

                    process_message(
                        update["message"]
                    )

        except Exception as e:

            print("BOT ERROR:", e)
            time.sleep(5)


# =========================
# START BOT
# =========================

if __name__ == "__main__":

    threading.Thread(
        target=bot_loop,
        daemon=True
    ).start()

    port = int(
        os.environ.get(
            "PORT",
            10000
        )
    )

    app.run(
        host="0.0.0.0",
        port=port
    )
