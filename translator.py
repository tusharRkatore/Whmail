from flask import Flask, request, jsonify, render_template
import speech_recognition as sr
import json
import os
import smtplib
import ssl
from werkzeug.utils import secure_filename
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from googletrans import Translator

app = Flask(__name__)
 
recognizer = sr.Recognizer()
translator = Translator()

# Email configuration
# 'wnon lavf hvxj ojqe'
# SMTP_SERVER = 'smtp.gmail.com'
# SMTP_PORT = 587
# SENDER_EMAIL = input("")  
# SENDER_PASSWORD = input("") 


# Function to translate text
def translate_text(text, output_lang):
    try:
        translation = translator.translate(text, dest=output_lang)
        return translation.text
    except json.JSONDecodeError:
        return "Error: Failed to translate text. Please try again later."
    except TypeError:
        return "Error: No valid translation response received."

# Global variables to store recognized text
recognized_subject = ""
recognized_body = ""

# Function to convert speech to text
def speech_to_text(input_lang, append=False, is_subject=True):
    global recognized_subject, recognized_body

    with sr.Microphone() as source:
        recognizer.adjust_for_ambient_noise(source)
        try:
            print("Listening... (will stop after 5 seconds of silence)")
            audio = recognizer.listen(source, timeout=5, phrase_time_limit=15)
            text = recognizer.recognize_google(audio, language=input_lang)

            if is_subject:  # If recognizing subject
                if append:  # Append to existing subject
                    recognized_subject += " " + text
                else:
                    recognized_subject = text
                print(f"Recognized Subject: {recognized_subject}")
                return recognized_subject
            else:  # If recognizing body
                if append:  # Append to existing body
                    recognized_body += " " + text
                else:
                    recognized_body = text
                print(f"Recognized Body: {recognized_body}")
                return recognized_body
        except sr.UnknownValueError:
            return "Error: Could not understand the audio."
        except sr.WaitTimeoutError:
            return "Error: No speech detected, stopping."
        except sr.RequestError as e:
            return f"Error: Could not request results from Google Speech Recognition service; {e}"

# Function to send email
# def send_email(recipient_email, subject, body_text):
#     message = MIMEMultipart()
#     message['From'] = SENDER_EMAIL
#     message['To'] = recipient_email
#     message['Subject'] = subject

# Main API routes
@app.route('/')
def home():
    return render_template('index.html')

# Start speech recognition route
@app.route('/start_recognition', methods=['POST'])
def start_recognition():
    data = request.json
    input_lang = data['inputLang']
    append = data.get('append', False)  # Check if we want to append the new text to previous one
    is_subject = data.get('isSubject', True)  # Determine if recognizing subject or body

    recognized_text_result = speech_to_text(input_lang, append, is_subject)

    if "Error" in recognized_text_result:
        return jsonify({'error': recognized_text_result}), 400
    else:
        return jsonify({'text': recognized_text_result})

# Stop recognition route
@app.route('/stop_recognition', methods=['POST'])
def stop_recognition():
    return jsonify({'message': 'Recognition stopped', 'recognizedSubject': recognized_subject, 'recognizedBody': recognized_body}), 200

# Translation route
@app.route('/translate', methods=['POST'])
def translate_text_route():
    data = request.json
    text = data['text']
    output_lang = data['outputLang']

    translated_text = translate_text(text, output_lang)

    if "Error" in translated_text:
        return jsonify({'error': translated_text}), 500
    else:
        return jsonify({'translated': translated_text})
    
@app.route('/upload_attachment', methods=['POST'])
def upload_attachment():
    if 'file' not in request.files:
        return 'No file part', 400  # Ensure this isn't the issue

    file = request.files['file']
    if file.filename == '':
        return 'No selected file', 400  # Ensure this isn't the issue

    upload_folder = 'uploads'
    if not os.path.exists(upload_folder):
        os.makedirs(upload_folder)

    attachment_path = os.path.join(upload_folder, secure_filename(file.filename))
    file.save(attachment_path)

    return jsonify({'message': f'File {file.filename} uploaded successfully', 'attachment_path': attachment_path}), 200


# Route to handle sending email
@app.route('/send_email', methods=['POST'])
def send_email():
    sender_email = request.form.get('senderEmail')
    sender_password = request.form.get('senderPassword')
    recipient_email = request.form.get('recipientEmail')
    subject = request.form.get('subject')
    body = request.form.get('body')
    attachment = request.files.get('attachment')

    if not sender_email or not sender_password or not recipient_email or not subject or not body:
        return jsonify({'error': 'Missing email fields'}), 400

    message = MIMEMultipart()
    message['From'] = sender_email
    message['To'] = recipient_email
    message['Subject'] = subject
    message.attach(MIMEText(body, 'plain'))

    if attachment and attachment.filename != '':
        upload_folder = 'uploads'
        if not os.path.exists(upload_folder):
            os.makedirs(upload_folder)
        
        attachment_path = os.path.join(upload_folder, secure_filename(attachment.filename))
        attachment.save(attachment_path)

        try:
            with open(attachment_path, 'rb') as attach_file:
                part = MIMEApplication(attach_file.read())
                part.add_header('Content-Disposition', f'attachment; filename="{attachment.filename}"')
                message.attach(part)
        except Exception as e:
            return jsonify({'error': f'Failed to attach file: {str(e)}'}), 500

    context = ssl.create_default_context()

    try:
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls(context=context)
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, recipient_email, message.as_string())
        return jsonify({'message': 'Email sent successfully!'})
    except Exception as e:
        return jsonify({'error': f'Failed to send email: {str(e)}'}), 500
    finally:
        if os.path.exists(attachment_path):
            os.remove(attachment_path)

if __name__ == '__main__':
    app.run(debug=True, port=5500)