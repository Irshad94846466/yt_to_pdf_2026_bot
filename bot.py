import os
import re
import time
import threading
import requests

from io import BytesIO
from flask import Flask

from youtube_transcript_api import YouTubeTranscriptApi

from reportlab.lib.pagesizes import A4
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Image,
    PageBreak
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from PIL import Image as PILImage


# =========================================================
# SETTINGS
# =========================================================

BOT_TOKEN = os.environ.get("BOT_TOKEN")

if not BOT_TOKEN:
    print("ERROR: BOT_TOKEN environment variable is missing.")

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

app = Flask(__name__)


# =========================================================
# HEALTH CHECK
# =========================================================

@app.route("/")
def home():
    return "YouTube PDF Bot is running!"


# =========================================================
# YOUTUBE VIDEO ID
# =========================================================

def get_video_id(url):
    patterns = [
        r"(?:youtube\.com/watch\?v=)([A-Za-z0-9_-]{11})",
        r"(?:youtu\.be/)([A-Za-z0-9_-]{11})",
        r"(?:youtube\.com/shorts/)([A-Za-z0-9_-]{11})",
        r"(?:youtube\.com/embed/)([A-Za-z0-9_-]{11})",
        r"(?:youtube\.com/live/)([A-Za-z0-9_-]{11})"
    ]

    for pattern in patterns:
        match = re.search(pattern, url)

        if match:
            return match.group(1)

    return None


# =========================================================
# YOUTUBE TITLE
# =========================================================

def get_video_title(video_id):
    try:
        url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"

        response = requests.get(
            url,
            timeout=15,
            headers={
                "User-Agent": "Mozilla/5.0"
            }
        )

        if response.status_code == 200:
            data = response.json()
            return data.get("title", "YouTube Video")

    except Exception as e:
        print("TITLE ERROR:", e)

    return "YouTube Video"


# =========================================================
# YOUTUBE THUMBNAIL
# =========================================================

def get_thumbnail(video_id):
    urls = [
        f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg",
        f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
    ]

    for url in urls:

        try:
            response = requests.get(
                url,
                timeout=15,
                headers={
                    "User-Agent": "Mozilla/5.0"
                }
            )

            if response.status_code == 200:
                return response.content

        except Exception as e:
            print("THUMBNAIL ERROR:", e)

    return None


# =========================================================
# GET TRANSCRIPT
# =========================================================

def get_transcript(video_id):

    api = YouTubeTranscriptApi()

    # Method 1
    try:
        transcript = api.fetch(
            video_id,
            languages=["hi", "en", "ur"]
        )

        text = []

        for item in transcript:
            text.append(item.text)

        if text:
            return "\n".join(text)

    except Exception as e:
        print("TRANSCRIPT METHOD 1 ERROR:", repr(e))

    # Method 2
    try:
        transcripts = api.list(video_id)

        for transcript in transcripts:

            try:
                fetched = transcript.fetch()

                text = []

                for item in fetched:
                    text.append(item.text)

                if text:
                    return "\n".join(text)

            except Exception as e:
                print("TRANSCRIPT FETCH ERROR:", repr(e))

    except Exception as e:
        print("TRANSCRIPT METHOD 2 ERROR:", repr(e))

    return None


# =========================================================
# CREATE PDF
# =========================================================

def create_pdf(title, video_id, transcript, thumbnail_data):

    filename = f"/tmp/youtube_{video_id}.pdf"

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
        "TitleStyle",
        parent=styles["Title"],
        alignment=TA_CENTER,
        fontSize=18,
        leading=23,
        spaceAfter=15
    )

    normal_style = ParagraphStyle(
        "NormalStyle",
        parent=styles["BodyText"],
        fontSize=10,
        leading=15,
        spaceAfter=8
    )

    story = []

    # -----------------------------------------------------
    # TITLE
    # -----------------------------------------------------

    story.append(
        Paragraph(
            "YouTube Video PDF",
            title_style
        )
    )

    story.append(
        Paragraph(
            title,
            title_style
        )
    )

    story.append(Spacer(1, 10))

    # -----------------------------------------------------
    # THUMBNAIL
    # -----------------------------------------------------

    if thumbnail_data:

        try:
            image_stream = BytesIO(thumbnail_data)

            pil_image = PILImage.open(image_stream)

            width, height = pil_image.size

            max_width = 500
            max_height = 280

            ratio = min(
                max_width / width,
                max_height / height
            )

            new_width = width * ratio
            new_height = height * ratio

            image_stream.seek(0)

            img = Image(
                image_stream,
                width=new_width,
                height=new_height
            )

            story.append(img)
            story.append(Spacer(1, 15))

        except Exception as e:
            print("PDF IMAGE ERROR:", e)

    # -----------------------------------------------------
    # VIDEO LINK
    # -----------------------------------------------------

    youtube_url = (
        f"https://www.youtube.com/watch?v={video_id}"
    )

    story.append(
        Paragraph(
            f"<b>YouTube Link:</b> {youtube_url}",
            normal_style
        )
    )

    story.append(Spacer(1, 10))

    story.append(
        Paragraph(
            "<b>Transcript:</b>",
            styles["Heading2"]
        )
    )

    # -----------------------------------------------------
    # TRANSCRIPT
    # -----------------------------------------------------

    if transcript:

        paragraphs = transcript.split("\n")

        for line in paragraphs:

            line = line.strip()

            if not line:
                continue

            # Escape HTML characters
            line = (
                line.replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;")
            )

            story.append(
                Paragraph(
                    line,
                    normal_style
                )
            )

    else:

        story.append(
            Paragraph(
                "Transcript available nahi hai.",
                normal_style
            )
        )

    # -----------------------------------------------------
    # BUILD PDF
    # -----------------------------------------------------

    doc.build(story)

    return filename


# =========================================================
# SEND TELEGRAM MESSAGE
# =========================================================

def send_message(chat_id, text):

    try:

        requests.post(
            f"{TELEGRAM_API}/sendMessage",
            data={
                "chat_id": chat_id,
                "text": text
            },
            timeout=20
        )

    except Exception as e:

        print("SEND MESSAGE ERROR:", e)


# =========================================================
# SEND PDF
# =========================================================

def send_pdf(chat_id, pdf_file):

    try:

        with open(pdf_file, "rb") as file:

            requests.post(
                f"{TELEGRAM_API}/sendDocument",
                data={
                    "chat_id": chat_id,
                    "caption": "✅ Aapka YouTube PDF ready hai!"
                },
                files={
                    "document": file
                },
                timeout=60
            )

    except Exception as e:

        print("SEND PDF ERROR:", e)


# =========================================================
# PROCESS YOUTUBE LINK
# =========================================================

def process_video(chat_id, url):

    video_id = get_video_id(url)

    if not video_id:

        send_message(
            chat_id,
            "❌ YouTube link sahi nahi hai.\n\n"
            "Example:\n"
            "https://www.youtube.com/watch?v=XXXXXXXXXXX"
        )

        return

    send_message(
        chat_id,
        "⏳ Video mil gaya!\n\n"
        "📖 Transcript nikal raha hoon..."
    )

    title = get_video_title(video_id)

    thumbnail = get_thumbnail(video_id)

    transcript = get_transcript(video_id)

    if not transcript:

        send_message(
            chat_id,
            "❌ Is video ka transcript nahi mil saka.\n\n"
            "Possible reason:\n"
            "• YouTube captions available nahi hain\n"
            "• YouTube ne request block ki hai\n"
            "• Video restricted/private hai\n\n"
            "Kisi normal public video ka link try karo."
        )

        return

    send_message(
        chat_id,
        "📄 PDF bana raha hoon..."
    )

    try:

        pdf_file = create_pdf(
            title,
            video_id,
            transcript,
            thumbnail
        )

        send_pdf(
            chat_id,
            pdf_file
        )

    except Exception as e:

        print("PDF ERROR:", repr(e))

        send_message(
            chat_id,
            "❌ PDF banate waqt error aa gaya."
        )


# =========================================================
# TELEGRAM UPDATE HANDLER
# =========================================================

def handle_update(update):

    try:

        message = update.get("message")

        if not message:
            return

        chat = message.get("chat")

        if not chat:
            return

        chat_id = chat.get("id")

        text = message.get("text", "").strip()

        if not text:
            return

        # START
        if text == "/start":

            send_message(
                chat_id,
                "👋 Assalamualaikum!\n\n"
                "🎥 YouTube video ka link bhejo.\n"
                "Main uska transcript PDF bana dunga.\n\n"
                "Example:\n"
                "https://www.youtube.com/watch?v=XXXXXXXXXXX"
            )

            return

        # HELP
        if text == "/help":

            send_message(
                chat_id,
                "📌 Bot ka use:\n\n"
                "1️⃣ YouTube video ka link copy karo\n"
                "2️⃣ Yahan send karo\n"
                "3️⃣ Bot transcript PDF bana dega"
            )

            return

        # YOUTUBE LINK
        if (
            "youtube.com" in text
            or "youtu.be" in text
        ):

            threading.Thread(
                target=process_video,
                args=(chat_id, text),
                daemon=True
            ).start()

            return

        send_message(
            chat_id,
            "❌ Please sirf YouTube video ka link bhejo."
        )

    except Exception as e:

        print("UPDATE ERROR:", repr(e))


# =========================================================
# TELEGRAM LONG POLLING
# =========================================================

def telegram_bot():

    print("Telegram bot started...")

    offset = None

    while True:

        try:

            params = {
                "timeout": 30
            }

            if offset is not None:
                params["offset"] = offset

            response = requests.get(
                f"{TELEGRAM_API}/getUpdates",
                params=params,
                timeout=40
            )

            data = response.json()

            if not data.get("ok"):
                print("TELEGRAM ERROR:", data)
                time.sleep(5)
                continue

            updates = data.get("result", [])

            for update in updates:

                offset = update["update_id"] + 1

                handle_update(update)

        except Exception as e:

            print("POLLING ERROR:", repr(e))

            time.sleep(5)


# =========================================================
# START FLASK + TELEGRAM
# =========================================================

if __name__ == "__main__":

    bot_thread = threading.Thread(
        target=telegram_bot,
        daemon=True
    )

    bot_thread.start()

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
