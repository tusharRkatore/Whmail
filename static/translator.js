// Globals for recorder
let mediaRecorder = null;
let audioChunks = [];

// start recording (returns when media stream started)
async function startRecording() {
  audioChunks = [];
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  mediaRecorder = new MediaRecorder(stream);
  mediaRecorder.ondataavailable = (e) => {
    if (e.data && e.data.size > 0) audioChunks.push(e.data);
  };
  mediaRecorder.start();
}

// stop recording and send to backend, returns JSON response
async function stopRecordingAndSend(inputLang, append, is_subject) {
  return new Promise((resolve, reject) => {
    if (!mediaRecorder) return reject("Recorder not started");

    mediaRecorder.onstop = async () => {
      const blob = new Blob(audioChunks, {
        type: audioChunks[0]?.type || "audio/webm",
      });
      const formData = new FormData();
      formData.append("audio", blob, "recording.webm"); // filename used by backend
      formData.append("inputLang", inputLang);
      formData.append("append", append ? "true" : "false");
      formData.append("is_subject", is_subject ? "true" : "false");

      try {
        const res = await fetch("/start_recognition", {
          method: "POST",
          body: formData,
        });
        const json = await res.json();
        resolve(json);
      } catch (err) {
        reject(err);
      }
    };

    mediaRecorder.stop();
    // stop all tracks so mic light goes off
    mediaRecorder.stream.getTracks().forEach((t) => t.stop());
    mediaRecorder = null;
  });
}

// Utility: record for a seconds and return the backend response
async function recordForSecondsAndSend(seconds, inputLang, append, is_subject) {
  await startRecording();
  return new Promise((resolve, reject) => {
    setTimeout(async () => {
      try {
        const result = await stopRecordingAndSend(
          inputLang,
          append,
          is_subject
        );
        resolve(result);
      } catch (e) {
        reject(e);
      }
    }, seconds * 1000);
  });
}

// ---------------- UI handlers ----------------

// Translate recognized subject/body
document.getElementById("translateBtn").addEventListener("click", () => {
  const subjectText = document.getElementById("recognizedSubject").value;
  const bodyText = document.getElementById("recognizedBody").value;
  const outputLang = document.getElementById("outputLang").value;

  fetch("/translate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text: subjectText, outputLang }),
  })
    .then((r) => r.json())
    .then(
      (d) =>
        (document.getElementById("translatedSubject").value =
          d.translated || "")
    );

  fetch("/translate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text: bodyText, outputLang }),
  })
    .then((r) => r.json())
    .then(
      (d) =>
        (document.getElementById("translatedBody").value = d.translated || "")
    );
});

// Recognize Email Subject (record 4 sec)
document
  .getElementById("speakSubjectBtn")
  .addEventListener("click", async () => {
    try {
      const data = await recordForSecondsAndSend(
        4,
        document.getElementById("inputLang").value,
        false,
        true
      );
      if (data.text)
        document.getElementById("recognizedSubject").value = data.text;
      else if (data.error) alert(data.error);
    } catch (e) {
      console.error(e);
      alert("Recording failed: " + e);
    }
  });

// Continue Recognizing Email Subject (append)
document
  .getElementById("continueSubjectBtn")
  .addEventListener("click", async () => {
    try {
      const data = await recordForSecondsAndSend(
        4,
        document.getElementById("inputLang").value,
        true,
        true
      );
      if (data.text)
        document.getElementById("recognizedSubject").value = data.text;
      else if (data.error) alert(data.error);
    } catch (e) {
      console.error(e);
      alert("Recording failed: " + e);
    }
  });

// Recognize Email Body
document.getElementById("speakBodyBtn").addEventListener("click", async () => {
  try {
    const data = await recordForSecondsAndSend(
      4,
      document.getElementById("inputLang").value,
      false,
      false
    );
    if (data.text) document.getElementById("recognizedBody").value = data.text;
    else if (data.error) alert(data.error);
  } catch (e) {
    console.error(e);
    alert("Recording failed: " + e);
  }
});

// Continue Recognizing Email Body (append)
document
  .getElementById("continueBodyBtn")
  .addEventListener("click", async () => {
    try {
      const data = await recordForSecondsAndSend(
        4,
        document.getElementById("inputLang").value,
        true,
        false
      );
      if (data.text)
        document.getElementById("recognizedBody").value = data.text;
      else if (data.error) alert(data.error);
    } catch (e) {
      console.error(e);
      alert("Recording failed: " + e);
    }
  });

// Stop recognition manually (returns stored concatenated subject/body)
document.getElementById("stopBtn").addEventListener("click", async () => {
  try {
    const res = await fetch("/stop_recognition", { method: "POST" });
    const data = await res.json();
    document.getElementById("recognizedSubject").value =
      data.recognizedSubject || "";
    document.getElementById("recognizedBody").value = data.recognizedBody || "";
  } catch (e) {
    console.error(e);
    alert("Stop failed: " + e);
  }
});

// Send Email (unchanged)
document.getElementById("sendEmailBtn").addEventListener("click", async () => {
  const senderEmail = document.getElementById("senderEmail").value;
  const senderPassword = document.getElementById("senderpassword").value;
  const recipientEmail = document.getElementById("recipientEmail").value;
  const subject = document.getElementById("translatedSubject").value;
  const bodyText = document.getElementById("translatedBody").value;
  const attachmentFile = document.getElementById("attachment").files[0];

  if (!attachmentFile) {
    alert("Please select a file to attach.");
    return;
  }

  const formData = new FormData();
  formData.append("senderEmail", senderEmail);
  formData.append("senderPassword", senderPassword);
  formData.append("recipientEmail", recipientEmail);
  formData.append("subject", subject);
  formData.append("body", bodyText);
  formData.append("attachment", attachmentFile);

  try {
    const response = await fetch("/send_email", {
      method: "POST",
      body: formData,
    });
    const result = await response.json();
    alert(result.message || result.error);
  } catch (error) {
    console.error("Error:", error);
    alert("Failed to send the email.");
  }
});

// Upload attachment
document.getElementById("uploadBtn").addEventListener("click", function () {
  const fileInput = document.getElementById("attachment");
  const file = fileInput.files[0];

  if (file) {
    const formData = new FormData();
    formData.append("file", file);

    fetch("/upload_attachment", { method: "POST", body: formData })
      .then((response) => {
        if (!response.ok) throw new Error("Failed to upload file");
        return response.json();
      })
      .then((data) => {
        alert(data.message || "File uploaded successfully!");
      })
      .catch((error) => {
        console.error("Error:", error);
        alert("Error uploading file");
      });
  } else {
    alert("No file selected");
  }
});
