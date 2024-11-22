# Speech-to-Text Translator with Email Integration WhisperMail

## Project Overview
This project is a web-based application that allows users to:
- Convert speech to text in multiple languages.
- Translate recognized text into a chosen language.
- Send translated text via email with optional file attachments.

## Features
- **Speech Recognition**: Uses Google Speech Recognition to convert speech to text.
- **Text Translation**: Translates recognized text into the specified language using Google Translate.
- **Email Integration**: Sends the translated text as an email with optional attachments.
- **User Interface**: A web-based UI to manage language selection, email fields, and file uploads.

## Tech Stack
- **Backend**: Python (Flask, `speech_recognition`, `googletrans`, `smtplib`, `ssl`)
- **Frontend**: HTML, CSS, JavaScript
- **SMTP Server**: Supports Gmail for email functionality

## Project Structure
├── app.py # Main application file with Flask server
├── uploads # For storing attachments Temporarily
├── templates/ 
│ └── index.html # HTML template for the web UI 
├── static/ 
│ ├── translator.js # JavaScript file for client-side functionality 
│ └── translator.css # CSS for styling the UI 
└── README.md # Project documentation

## Installation

### Prerequisites
- **Python** 3.x installed on your machine
- Required Python libraries:
  - Flask
  - SpeechRecognition
  - Googletrans
  - smtplib
  - ssl

### Setup Instructions

1. Install dependencies:
   - pip install flask speechrecognition googletrans

2. Configure email settings if using a personal email provider:
    - Update the SMTP_SERVER and SMTP_PORT settings in app.py.
    - Ensure sender_email and sender_password fields are configured in the frontend.

### Running the Application

1. Start the Flask server:
    python app.py

2. Open a browser and navigate to http://127.0.0.1:5500 to access the application

## Usage
- **Select Input Language** : Choose the language for speech recognition from the dropdown.
- **Translate Text**: Once the speech is converted to text, select the output language for translation.
- **Send Email**: Enter sender and recipient email details, add an attachment if necessary, and send the email.

## Troubleshooting
- **No Speech Detected**: Ensure your microphone is working and try increasing the timeout settings in app.py.
- **Translation Issues**: Check your internet connection and Google Translate API availability.
- **Email Sending Issues**: Verify your email provider's SMTP settings and allow less secure app access if using Gmail.