# translator.py
import os
import uuid
import shutil
import subprocess
import traceback
import base64
from flask import Flask, request, jsonify, render_template
import speech_recognition as sr
from werkzeug.utils import secure_filename
from pydub import AudioSegment, effects
from deep_translator import GoogleTranslator
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
import requests

app = Flask(__name__, template_folder="templates", static_folder="static")
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

translator = GoogleTranslator(source="auto")

# ----------------------------
# ffmpeg detection
# ----------------------------
def find_ffmpeg():
    return shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")
FFMPEG_BIN = find_ffmpeg()
if not FFMPEG_BIN:
    print("WARNING: ffmpeg not found on PATH. Install ffmpeg for audio conversion.")

def ffmpeg_convert(in_path, out_wav_path):
    if not FFMPEG_BIN:
        raise RuntimeError("ffmpeg not found on PATH.")
    cmd = [
        FFMPEG_BIN, "-y", "-i", in_path,
        "-ac", "1", "-ar", "16000", "-sample_fmt", "s16",
        out_wav_path
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {proc.stderr.strip()}")
    if not os.path.exists(out_wav_path) or os.path.getsize(out_wav_path) < 500:
        raise RuntimeError("Converted WAV missing or too small.")
    return out_wav_path

def normalize_and_save(in_path, out_path):
    audio = AudioSegment.from_file(in_path)
    if audio.dBFS < -35.0:
        target_db = -20.0
        change = target_db - audio.dBFS
        audio = audio.apply_gain(change)
    audio = effects.normalize(audio)
    audio.export(out_path, format="wav",
                 parameters=["-ac", "1", "-ar", "16000", "-sample_fmt", "s16"])
    if not os.path.exists(out_path) or os.path.getsize(out_path) < 500:
        raise RuntimeError("Normalization produced empty file.")
    return out_path

def transcribe_wav(wav_path, lang="en-US"):
    r = sr.Recognizer()
    try:
        with sr.AudioFile(wav_path) as source:
            audio_data = r.record(source)
        text = r.recognize_google(audio_data, language=lang)
        return text
    except sr.UnknownValueError:
        raise RuntimeError("Could not understand audio. Speak clearly and try again.")
    except sr.RequestError as e:
        raise RuntimeError(f"Speech recognition request failed: {e}")
    except Exception as e:
        raise RuntimeError(f"Transcription error: {e}")

# ----------------------------
# Routes
# ----------------------------
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/start_recognition", methods=["POST"])
def start_recognition():
    try:
        if "audio_file" not in request.files:
            return jsonify({"error": "No audio_file in request"}), 400

        f = request.files["audio_file"]
        if f.filename == "":
            return jsonify({"error": "Empty filename"}), 400

        uid = uuid.uuid4().hex
        fname = secure_filename(f.filename)
        saved = os.path.join(UPLOAD_DIR, f"{uid}_{fname}")
        f.save(saved)

        # convert to safe wav
        converted = os.path.join(UPLOAD_DIR, f"{uid}_conv.wav")
        try:
            ffmpeg_convert(saved, converted)
        except Exception as e:
            # try a forced demux fallback for webm
            try:
                alt_conv = os.path.join(UPLOAD_DIR, f"{uid}_conv_alt.wav")
                cmd = [FFMPEG_BIN, "-y", "-f", "webm", "-i", saved, "-ac", "1", "-ar", "16000", "-sample_fmt", "s16", alt_conv]
                subprocess.run(cmd, capture_output=True, text=True)
                if os.path.exists(alt_conv) and os.path.getsize(alt_conv) > 500:
                    converted = alt_conv
                else:
                    raise RuntimeError("Fallback conversion failed")
            except Exception:
                try: os.remove(saved)
                except: pass
                return jsonify({"error": f"Audio conversion failed: {str(e)}"}), 400

        normalized = os.path.join(UPLOAD_DIR, f"{uid}_norm.wav")
        try:
            normalize_and_save(converted, normalized)
        except Exception:
            normalized = converted

        input_lang = request.form.get("inputLang", "en-US")
        try:
            text = transcribe_wav(normalized, lang=input_lang)
        except Exception as e:
            for p in (saved, converted, normalized):
                try: os.remove(p)
                except: pass
            return jsonify({"error": str(e)}), 400

        for p in (saved, converted, normalized):
            try:
                if os.path.exists(p): os.remove(p)
            except: pass

        return jsonify({"text": text})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": f"Server error: {e}"}), 500

@app.route("/translate", methods=["POST"])
def translate_route():
    data = request.json or {}
    text = data.get("text", "")
    output_lang = data.get("outputLang", "en")
    try:
        translator = GoogleTranslator(source="auto", target=output_lang)
        translated_text = translator.translate(text)
        return jsonify({"translated": translated_text})
    except Exception as e:
        return jsonify({"error": f"Translation failed: {e}"}), 500

@app.route("/upload_attachment", methods=["POST"])
def upload_attachment():
    if "file" not in request.files:
        return jsonify({"error": "No file part"}), 400
    f = request.files["file"]
    if f.filename == "":
        return jsonify({"error": "No selected file"}), 400
    path = os.path.join(UPLOAD_DIR, secure_filename(f.filename))
    f.save(path)
    return jsonify({"message": "File uploaded", "attachment_path": path})

# ----------------------------
# Email sending:
# - Prefer BREVO_API_KEY (Brevo / Sendinblue REST SMTP endpoint)
# - If BREVO_API_KEY not present or Brevo fails, fallback to Gmail SMTP using app password
# ----------------------------
BREVO_API_KEY = os.environ.get("xsmtpsib-038c66eaabbf2346cc2b9f3f936b3040aaee94a83d00eba52f6bb98ba3b1149e-3joQumhnPnmN3scp", "").strip()  # set this in env for Docker/hosting
GMAIL_FALLBACK = os.environ.get("ppxx uwzx loln ofdw", "true").lower() != "false"

def send_via_brevo(sender, receiver, subject, body, attachment_file_path=None, attachment_filename=None):
    payload = {
        "sender": {"email": sender},
        "to": [{"email": receiver}],
        "subject": subject,
        "htmlContent": body.replace("\n", "<br>")
    }

    if attachment_file_path and attachment_filename:
        with open(attachment_file_path, "rb") as fh:
            file_bytes = fh.read()
        payload["attachment"] = [{
            "name": attachment_filename,
            "content": base64.b64encode(file_bytes).decode("ascii")
        }]

    headers = {
        "Accept": "application/json",
        "api-key": BREVO_API_KEY,
        "Content-Type": "application/json"
    }

    res = requests.post("https://api.brevo.com/v3/smtp/email", json=payload, headers=headers, timeout=30)
    return res

def send_via_gmail(sender, password, receiver, subject, body, attachment_file_path=None, attachment_filename=None):
    msg = MIMEMultipart()
    msg["From"] = sender
    msg["To"] = receiver
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))
    if attachment_file_path and attachment_filename:
        with open(attachment_file_path, "rb") as fh:
            part = MIMEApplication(fh.read())
            part.add_header("Content-Disposition", f'attachment; filename="{attachment_filename}"')
            msg.attach(part)

    ctx = ssl.create_default_context()
    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.ehlo()
        server.starttls(context=ctx)
        server.ehlo()
        server.login(sender, password)
        server.sendmail(sender, receiver, msg.as_string())

@app.route("/send_email", methods=["POST"])
def send_email():
    sender = request.form.get("senderEmail", "").strip()
    password = request.form.get("senderPassword", "").strip()  # used if Gmail fallback
    receiver = request.form.get("recipientEmail", "").strip()
    subject = request.form.get("subject", "")
    body = request.form.get("body", "")
    attachment = request.files.get("attachment")

    if not sender or not receiver or not subject or not body:
        return jsonify({"error": "Missing email fields"}), 400

    file_path = None
    attach_name = None
    if attachment and attachment.filename:
        attach_name = secure_filename(attachment.filename)
        file_path = os.path.join(UPLOAD_DIR, f"{uuid.uuid4().hex}_{attach_name}")
        attachment.save(file_path)

    # Try Brevo if key present
    if BREVO_API_KEY:
        try:
            res = send_via_brevo(sender, receiver, subject, body, file_path, attach_name)
            # handle response
            if res.status_code >= 400:
                # try to extract json or text for clarity
                try:
                    detail = res.json()
                except:
                    detail = res.text
                # If Brevo rejected due to key, return explicit message
                if isinstance(detail, dict) and detail.get("code") == "unauthorized":
                    # optional fallback to Gmail if configured
                    if GMAIL_FALLBACK and password:
                        try:
                            send_via_gmail(sender, password, receiver, subject, body, file_path, attach_name)
                            return jsonify({"message": "Email sent via Gmail fallback (Brevo failed)."})
                        except Exception as e:
                            return jsonify({"error": f"Brevo rejected key and Gmail fallback also failed: {e}"}), 500
                    return jsonify({"error": f"Brevo error: {detail}"}), 401
                return jsonify({"error": f"Brevo error: {detail}"}), 500
            return jsonify({"message": "Email sent successfully via Brevo!"})
        except requests.exceptions.RequestException as e:
            # network or timeout - try Gmail fallback if configured
            if GMAIL_FALLBACK and password:
                try:
                    send_via_gmail(sender, password, receiver, subject, body, file_path, attach_name)
                    return jsonify({"message": "Email sent via Gmail fallback (Brevo request failed)."})
                except Exception as e2:
                    return jsonify({"error": f"Brevo request failed and Gmail fallback failed: {e2}"}), 500
            return jsonify({"error": f"Brevo request failed: {e}"}), 500
        except Exception as e:
            # other errors - try fallback
            if GMAIL_FALLBACK and password:
                try:
                    send_via_gmail(sender, password, receiver, subject, body, file_path, attach_name)
                    return jsonify({"message": "Email sent via Gmail fallback (Brevo error)."})
                except Exception as e2:
                    return jsonify({"error": f"Brevo error and Gmail fallback failed: {e2}"}), 500
            return jsonify({"error": f"Brevo error: {e}"}), 500

    # If no Brevo key or key empty - use Gmail fallback (requires app password)
    if GMAIL_FALLBACK:
        if not password:
            return jsonify({"error": "No BREVO_API_KEY and no Gmail app password provided."}), 400
        try:
            send_via_gmail(sender, password, receiver, subject, body, file_path, attach_name)
            return jsonify({"message": "Email sent successfully via Gmail SMTP."})
        except smtplib.SMTPAuthenticationError:
            return jsonify({"error": "Gmail authentication failed. Use an App Password (not normal password)."}), 401
        except Exception as e:
            traceback.print_exc()
            return jsonify({"error": f"Gmail send failed: {e}"}), 500

    return jsonify({"error": "No email provider configured."}), 500

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 5500)))
