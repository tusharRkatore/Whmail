from flask import Flask, request, jsonify, render_template
import speech_recognition as sr
import os
import smtplib
import ssl
from werkzeug.utils import secure_filename
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from deep_translator import GoogleTranslator
from pydub import AudioSegment
import uuid
from pydub.utils import which

app = Flask(__name__)

translator = GoogleTranslator(source='auto')

# Globals
recognized_subject = ""
recognized_body = ""


def translate_text(text, output_lang):
    try:
        return GoogleTranslator(source='auto', target=output_lang).translate(text)
    except Exception as e:
        return f"Error: Translation failed → {e}"


def ensure_wav(path):
    """
    Convert any audio file into WAV.
    Works for webm / m4a / mp3 / ogg / mp4
    """
    filename = os.path.basename(path)
    name, ext = os.path.splitext(filename)
    ext = ext.lower()

    if ext == ".wav":
        return path

    wav_path = f"temp_{uuid.uuid4().hex}.wav"

    try:
        audio = AudioSegment.from_file(path)
        audio.export(wav_path, format="wav")
        return wav_path
    except Exception as e:
        raise RuntimeError(f"Audio conversion failed: {e}")


def speech_to_text_from_file(uploaded, input_lang, append=False, is_subject=True):
    global recognized_subject, recognized_body

    orig_path = f"upload_{uuid.uuid4().hex}_{secure_filename(uploaded.filename)}"
    uploaded.save(orig_path)

    wav_path = None

    try:
        wav_path = ensure_wav(orig_path)

        r = sr.Recognizer()
        with sr.AudioFile(wav_path) as source:
            r.adjust_for_ambient_noise(source, duration=0.3)
            audio_data = r.record(source)

        text = r.recognize_google(audio_data, language=input_lang)

        if is_subject:
            recognized_subject = (recognized_subject +
                                  " " + text).strip() if append else text
            return recognized_subject
        else:
            recognized_body = (recognized_body + " " +
                               text).strip() if append else text
            return recognized_body

    except sr.UnknownValueError:
        return "Error: Could not understand audio."
    except sr.RequestError as e:
        return f"Error: Google STT failed → {e}"
    except RuntimeError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Unexpected error: {e}"
    finally:
        try:
            if os.path.exists(orig_path):
                os.remove(orig_path)
            if wav_path and wav_path != orig_path and os.path.exists(wav_path):
                os.remove(wav_path)
        except:
            pass


@app.route('/')
def home():
    return render_template('index.html')


@app.route('/start_recognition', methods=['POST'])
def start_recognition():
    if "audio" not in request.files:
        return jsonify({"error": "No audio file received"}), 400

    audio_file = request.files["audio"]
    input_lang = request.form.get("inputLang", "en")
    append = request.form.get("append", "false").lower() == "true"
    is_subject = request.form.get("is_subject", "true").lower() == "true"

    result = speech_to_text_from_file(
        audio_file, input_lang, append, is_subject)

    if isinstance(result, str) and result.startswith("Error"):
        return jsonify({"error": result}), 400
    return jsonify({"text": result})


@app.route('/stop_recognition', methods=['POST'])
def stop_recognition():
    return jsonify({
        "recognizedSubject": recognized_subject,
        "recognizedBody": recognized_body
    })


@app.route('/translate', methods=['POST'])
def translate_text_route():
    data = request.json
    text = data.get("text", "")
    output_lang = data.get("outputLang", "en")

    translation = translate_text(text, output_lang)

    if translation.startswith("Error"):
        return jsonify({"error": translation}), 500

    return jsonify({"translated": translation})


@app.route('/upload_attachment', methods=['POST'])
def upload_attachment():
    if "file" not in request.files:
        return "No file part", 400

    f = request.files["file"]
    if f.filename == "":
        return "No selected file", 400

    folder = "uploads"
    os.makedirs(folder, exist_ok=True)

    path = os.path.join(folder, secure_filename(f.filename))
    f.save(path)

    return jsonify({"message": "File uploaded successfully", "attachment_path": path})


# ---------------------------------------------------------
# UPDATED EMAIL SENDING WITH GMAIL APP PASSWORD SUPPORT
# ---------------------------------------------------------
@app.route('/send_email', methods=['POST'])
def send_email():
    sender = request.form.get("senderEmail")
    password = request.form.get("senderPassword")  # <-- Must be App Password
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
        folder = "uploads"
        os.makedirs(folder, exist_ok=True)
        att_path = os.path.join(folder, secure_filename(attachment.filename))
        attachment.save(att_path)

        with open(att_path, "rb") as f:
            part = MIMEApplication(f.read())
            part.add_header("Content-Disposition",
                            f'attachment; filename="{attachment.filename}"')
            msg.attach(part)

    try:
        ctx = ssl.create_default_context()

        # Gmail SMTP using App Password
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.ehlo()
            server.starttls(context=ctx)
            server.ehlo()
            server.login(sender, password)   # <-- WORKS ONLY WITH APP PASSWORD
            server.sendmail(sender, receiver, msg.as_string())

        return jsonify({"message": "Email sent successfully!"})

    except smtplib.SMTPAuthenticationError:
        return jsonify({
            "error": "Authentication failed. Use a Gmail App Password, not your normal password."
        }), 401
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if att_path and os.path.exists(att_path):
            os.remove(att_path)


if __name__ == '__main__':
    app.run(debug=True, port=5500)
