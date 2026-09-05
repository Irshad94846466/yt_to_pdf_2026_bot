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

BOT_TOKEN = os.environ.get("BOT_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is missing")

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

app = Flask(__name__)


@app.route("/")
def home():
    return "YouTube PDF Bot is running!"


# -----------------------------
# GET YOUTUBE VIDEO ID
# -----------------------------
def get_video_id(url):
    patterns = [
        r"(?:youtube\.com/watch\?v=)([A-Za-z0-9_-]{11})",
        r"(?:youtu\.be/)([A-Za-z0-9_-]{11})",
        r"(?:youtube\.com/shorts/)([A-Za-z0-9_-]{11})",
        r"(?:youtube\.com/embed/)([A-Za-z0-9_-]{11})",
        r"(?:youtube\.com/live/)([A-Za-z0-9_-]{11})",
    ]

    for pattern in patterns:
        match = re.search(pattern, url)

        if match:
            return match.group(1)

    return None


# -----------------------------
# GET VIDEO TITLE
# -----------------------------
def get_video_title(video_id):
    try:
        url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"

        response = requests.get(url, timeout=20)

        if response.ok:
            data = response.json()
            return data.get("title", "YouTube Video")

    except Exception as e:
        print("TITLE ERROR:", e)

    return "YouTube Video"


# -----------------------------
# GET THUMBNAIL
# -----------------------------
def get_thumbnail(video_id):
    thumbnail_urls = [
        f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg",
        f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"
    ]

    for url in thumbnail_urls:

        try:
            response = requests.get(url, timeout=20)

            if response.ok:

                image = PILImage.open(BytesIO(response.content))
                image.load()

                return image

        except Exception as e:
            print("THUMBNAIL ERROR:", e)

    return None


# -----------------------------
# GET TRANSCRIPT
# -----------------------------
def get_transcript(video_id):

    api = YouTubeTranscriptApi()

    try:

        transcript = api.fetch(
            video_id,
            languages=["hi", "en"]
        )

        text = []

        for item in transcript:
            if hasattr(item, "text"):
                text.append(item.text)
            else:
                text.append(item["text"])

        return " ".join(text)

    except Exception as e:

        print("TRANSCRIPT ERROR:", e)

        try:

            transcript_list = api.list(video_id)

            for transcript in transcript_list:

                fetched = transcript.fetch()

                text = []

                for item in fetched:

                    if hasattr(item, "text"):
                        text.append(item.text)
                    else:
                        text.append(item["text"])

                if text:
                    return " ".join(text)

        except Exception as e2:

            print("TRANSCRIPT FALLBACK ERROR:", e2)

        raise Exception(
            "Is video ka transcript/captions available nahi hai."
        )


# -----------------------------
# CREATE PDF
# -----------------------------
def create_pdf(text, video_url, video_id, title):

    filename = f"/tmp/youtube_notes_{int(time.time())}.pdf"

    # Font
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
        spaceAfter=15
    )

    heading_style = ParagraphStyle(
        "HeadingCustom",
        parent=styles["Heading2"],
        fontName=font_name,
        fontSize=14,
        spaceBefore=15,
        spaceAfter=10
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

    # TITLE
    safe_title = (
        title
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )

    story.append(
        Paragraph(
            safe_title,
            title_style
        )
    )

    story.append(
        Paragraph(
            "YouTube Video Notes",
            heading_style
        )
    )

    # THUMBNAIL
    thumbnail = get_thumbnail(video_id)

    if thumbnail:

        try:

            thumbnail_path = f"/tmp/thumb_{video_id}.jpg"

            thumbnail.save(
                thumbnail_path,
                "JPEG"
            )

            img = Image(
                thumbnail_path,
                width=500,
                height=281
            )

            story.append(img)
            story.append(Spacer(1, 15))

        except Exception as e:

            print("IMAGE PDF ERROR:", e)

    # SOURCE
    safe_url = (
        video_url
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )

    story.append(
        Paragraph(
            f"<b>YouTube:</b> {safe_url}",
            body_style
        )
    )

    story.append(
        Spacer(1, 10)
    )

    story.append(
        Paragraph(
            "Transcript / Notes",
            heading_style
        )
    )

    # TEXT CHUNKS
    words = text.split()

    chunk = []

    for word in words:

        chunk.append(word)

        if len(chunk) >= 80:

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


# -----------------------------
# SEND MESSAGE
# -----------------------------
def send_message(chat_id, text):

    try:

        requests.post(
            f"{TELEGRAM_API}/sendMessage",
            data={
                "chat_id": chat_id,
                "text": text
            },
            timeout=30
        )

    except Exception as e:

        print("SEND MESSAGE ERROR:", e)


# -----------------------------
# SEND PDF
# -----------------------------
def send_pdf(chat_id, filename):

    try:

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

    except Exception as e:

        print("SEND PDF ERROR:", e)


# -----------------------------
# PROCESS MESSAGE
# -----------------------------
def process_message(message):

    chat_id = message["chat"]["id"]

    text = message.get(
        "text",
        ""
    ).strip()

    # START
    if text == "/start":

        send_message(
            chat_id,

            "👋 Welcome!\n\n"
            "🎥 YouTube video ka link bhejo.\n\n"
            "Main:\n"
            "📝 Transcript nikalaunga\n"
            "🖼️ Video thumbnail add karunga\n"
            "📄 PDF banaunga\n\n"
            "Aur PDF tumhe Telegram par bhej dunga. 🚀"
        )

        return

    # URL CHECK
    if not text.startswith("http"):

        send_message(
            chat_id,
            "❌ Please YouTube video ka link bhejo."
        )

        return

    # VIDEO ID
    video_id = get_video_id(text)

    if not video_id:

        send_message(
            chat_id,
            "❌ Ye valid YouTube link nahi lag raha."
        )

        return

    send_message(
        chat_id,
        "⏳ Video check ho raha hai..."
    )

    try:

        # TITLE
        title = get_video_title(video_id)

        send_message(
            chat_id,
            f"🎥 {title}\n\n"
            "📝 Transcript nikala ja raha hai..."
        )

        # TRANSCRIPT
        transcript = get_transcript(video_id)

        if not transcript:

            raise Exception(
                "Empty transcript"
            )

        send_message(
            chat_id,
            "🖼️ Image add ki ja rahi hai...\n"
            "📄 PDF banaya ja raha hai..."
        )

        # CREATE PDF
        pdf_file = create_pdf(
            transcript,
            text,
            video_id,
            title
        )

        # SEND
        send_pdf(
            chat_id,
            pdf_file
        )

        # DELETE TEMP FILE
        try:

            os.remove(pdf_file)

        except Exception:
            pass

        send_message(
            chat_id,
            "✅ PDF successfully ready hai! 🎉"
        )

    except Exception as e:

        print("ERROR:", e)

        send_message(
            chat_id,

            "❌ Is video ka transcript available nahi mila.\n\n"
            "👉 Aisa video try karo jisme YouTube captions/subtitles available hon."
        )


# -----------------------------
# BOT LOOP
# -----------------------------
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

                offset = (
                    update["update_id"] + 1
                )

                if "message" in update:

                    process_message(
                        update["message"]
                    )

        except Exception as e:

            print(
                "BOT LOOP ERROR:",
                e
            )

            time.sleep(5)


# -----------------------------
# START
# -----------------------------
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
