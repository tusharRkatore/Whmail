# translator.py
import os, uuid, shutil, subprocess, traceback
from flask import Flask, request, jsonify, render_template
import speech_recognition as sr
from werkzeug.utils import secure_filename
from pydub import AudioSegment, effects
from deep_translator import GoogleTranslator
import smtplib, ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication

app = Flask(__name__, template_folder="templates", static_folder="static")
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)
recognizer = sr.Recognizer()
translator = GoogleTranslator(source="auto")

# -----------------------------------------
# ffmpeg detection
# -----------------------------------------
def find_ffmpeg():
    return shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")
FFMPEG_BIN = find_ffmpeg()
if not FFMPEG_BIN:
    print("WARNING: ffmpeg not in PATH. Install ffmpeg for audio conversion.")

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

    audio.export(
        out_path,
        format="wav",
        parameters=["-ac", "1", "-ar", "16000", "-sample_fmt", "s16"]
    )

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

@app.route("/")
def index():
    return render_template("index.html")

# -----------------------------------------
# SPEECH TO TEXT ROUTE
# -----------------------------------------
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

        converted = os.path.join(UPLOAD_DIR, f"{uid}_conv.wav")
        try:
            ffmpeg_convert(saved, converted)
        except Exception as e:
            return jsonify({"error": f"Audio conversion failed: {str(e)}"}), 400

        normalized = os.path.join(UPLOAD_DIR, f"{uid}_norm.wav")
        try:
            normalize_and_save(converted, normalized)
        except:
            normalized = converted

        input_lang = request.form.get("inputLang", "en-US")
        try:
            text = transcribe_wav(normalized, lang=input_lang)
        except Exception as e:
            return jsonify({"error": str(e)}), 400

        for p in (saved, converted, normalized):
            try:
                if os.path.exists(p):
                    os.remove(p)
            except:
                pass

        return jsonify({"text": text})

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": f"Server error: {e}"}), 500

# -----------------------------------------
# UPDATED WORKING TRANSLATE ROUTE
# -----------------------------------------
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

# -----------------------------------------
# FILE UPLOAD + EMAIL REMAINS SAME
# -----------------------------------------
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

@app.route("/send_email", methods=["POST"])
def send_email():
    sender = request.form.get("senderEmail")
    password = request.form.get("senderPassword")
    receiver = request.form.get("recipientEmail")
    subject = request.form.get("subject")
    body = request.form.get("body")
    attachment = request.files.get("attachment")

    if not sender or not password or not receiver or not subject or not body:
        return jsonify({"error": "Missing email fields"}), 400

    msg = MIMEMultipart()
    msg["From"] = sender
    msg["To"] = receiver
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    att_path = None
    if attachment and attachment.filename:
        att_path = os.path.join(UPLOAD_DIR, secure_filename(attachment.filename))
        attachment.save(att_path)
        with open(att_path, "rb") as fh:
            part = MIMEApplication(fh.read())
            part.add_header(
                "Content-Disposition",
                f'attachment; filename="{attachment.filename}"'
            )
            msg.attach(part)

    try:
        ctx = ssl.create_default_context()
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls(context=ctx)
            server.login(sender, password)
            server.sendmail(sender, receiver, msg.as_string())
        return jsonify({"message": "Email sent successfully!"})
    except smtplib.SMTPAuthenticationError:
        return jsonify({"error": "Authentication failed. Use Gmail App Password."}), 401
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if att_path and os.path.exists(att_path):
            os.remove(att_path)

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 5500)))
