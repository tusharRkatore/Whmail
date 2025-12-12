// static/translator.js
function q(id) {
  return document.getElementById(id);
}

let mediaRecorder = null;
let audioChunks = [];
let isRecording = false;

function setRecordingState(state) {
  isRecording = state;
  q("speakSubjectBtn").disabled = state;
  q("continueSubjectBtn").disabled = state;
  q("speakBodyBtn").disabled = state;
  q("continueBodyBtn").disabled = state;
  q("stopBtn").disabled = !state;
}

async function startRecording() {
  audioChunks = [];
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    mediaRecorder = new MediaRecorder(stream);
    mediaRecorder.ondataavailable = (e) => {
      if (e.data && e.data.size > 0) audioChunks.push(e.data);
    };
    mediaRecorder.onstop = () => {
      try {
        stream.getTracks().forEach((t) => t.stop());
      } catch (e) {}
    };
    mediaRecorder.start();
    setRecordingState(true);
  } catch (err) {
    console.error("Microphone access error:", err);
    alert("Cannot access microphone. Allow mic permission and retry.");
    throw err;
  }
}

function stopRecordingGetBlob() {
  return new Promise((resolve, reject) => {
    if (!mediaRecorder) return reject(new Error("Recorder not started"));
    mediaRecorder.onstop = () => {
      const blob = new Blob(audioChunks, {
        type: audioChunks[0]?.type || "audio/webm",
      });
      setRecordingState(false);
      resolve(blob);
    };
    try {
      mediaRecorder.stop();
    } catch (err) {
      setRecordingState(false);
      const blob = new Blob(audioChunks, {
        type: audioChunks[0]?.type || "audio/webm",
      });
      resolve(blob);
    }
  });
}

async function sendBlob(blob, isSubject, appendFlag) {
  if (!blob || blob.size < 1000) {
    alert("Recording too short or empty — speak louder/closer and try again.");
    return null;
  }

  const file = new File([blob], `recording_${Date.now()}.webm`, {
    type: blob.type,
  });
  const form = new FormData();
  form.append("audio_file", file);
  form.append("inputLang", q("inputLang").value || "en-US");
  form.append("append", appendFlag ? "true" : "false");
  form.append("isSubject", isSubject ? "true" : "false");

  try {
    const resp = await fetch("/start_recognition", {
      method: "POST",
      body: form,
    });
    let json;
    try {
      json = await resp.json();
    } catch (e) {
      json = { error: "Invalid JSON response from server" };
    }

    if (!resp.ok) {
      const errMsg =
        json && json.error ? json.error : `Server responded ${resp.status}`;
      console.error("Server error:", errMsg);
      alert("Recognition failed: " + errMsg);
      return null;
    }
    return json.text || null;
  } catch (err) {
    console.error("Network error:", err);
    alert("Network error while sending audio: " + err.message);
    return null;
  }
}

async function recordThenSend(seconds, isSubject, appendFlag) {
  try {
    await startRecording();
  } catch (e) {
    return null;
  }
  return new Promise((resolve) => {
    setTimeout(async () => {
      const blob = await stopRecordingGetBlob();
      const text = await sendBlob(blob, isSubject, appendFlag);
      resolve(text);
    }, seconds * 1000);
  });
}

/* UI wiring */
q("speakSubjectBtn").addEventListener("click", async () => {
  q("recognizedSubject").value = "Recording...";
  const text = await recordThenSend(4, true, false);
  if (text) q("recognizedSubject").value = text;
});

q("continueSubjectBtn").addEventListener("click", async () => {
  const prev = q("recognizedSubject").value || "";
  q("recognizedSubject").value = prev + (prev ? " " : "") + "[recording...]";
  const text = await recordThenSend(4, true, true);
  const prefix = (q("recognizedSubject").value || "").replace(
    /\s*\[recording\.\.\.\]$/,
    ""
  );
  if (text) q("recognizedSubject").value = (prefix + " " + text).trim();
  else q("recognizedSubject").value = prefix.trim();
});

q("speakBodyBtn").addEventListener("click", async () => {
  q("recognizedBody").value = "Recording...";
  const text = await recordThenSend(4, false, false);
  if (text) q("recognizedBody").value = text;
});

q("continueBodyBtn").addEventListener("click", async () => {
  const prev = q("recognizedBody").value || "";
  q("recognizedBody").value = prev + (prev ? " " : "") + "[recording...]";
  const text = await recordThenSend(4, false, true);
  const prefix = (q("recognizedBody").value || "").replace(
    /\s*\[recording\.\.\.\]$/,
    ""
  );
  if (text) q("recognizedBody").value = (prefix + " " + text).trim();
  else q("recognizedBody").value = prefix.trim();
});

q("stopBtn").addEventListener("click", () => {
  if (isRecording && mediaRecorder) {
    try {
      mediaRecorder.stop();
      setRecordingState(false);
      alert("Recording stopped.");
    } catch (e) {
      console.warn(e);
    }
  } else {
    alert("No active recording.");
  }
});

q("translateBtn").addEventListener("click", async () => {
  const subject = q("recognizedSubject").value || "";
  const body = q("recognizedBody").value || "";
  const out = q("outputLang").value || "en";

  fetch("/translate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text: subject, outputLang: out }),
  })
    .then((r) => r.json())
    .then(
      (d) => (q("translatedSubject").value = d.translated || d.error || "")
    );
  fetch("/translate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text: body, outputLang: out }),
  })
    .then((r) => r.json())
    .then((d) => (q("translatedBody").value = d.translated || d.error || ""));
});

q("uploadBtn").addEventListener("click", async () => {
  const file = q("attachment").files[0];
  if (!file) {
    alert("Select a file");
    return;
  }
  const form = new FormData();
  form.append("file", file);
  try {
    const res = await fetch("/upload_attachment", {
      method: "POST",
      body: form,
    });
    const json = await res.json();
    alert(json.message || "Uploaded");
  } catch (e) {
    console.error(e);
    alert("Upload failed");
  }
});

q("sendEmailBtn").addEventListener("click", async () => {
  const sender = q("senderEmail").value.trim();
  const pass = q("senderpassword").value.trim();
  const receiver = q("recipientEmail").value.trim();
  const subject =
    q("translatedSubject").value.trim() || q("recognizedSubject").value.trim();
  const body =
    q("translatedBody").value.trim() || q("recognizedBody").value.trim();

  if (!sender) return alert("Sender required");
  if (!receiver) return alert("Recipient required");
  if (!subject) return alert("Subject required");
  if (!body) return alert("Body required");

  const form = new FormData();
  form.append("senderEmail", sender);
  form.append("senderPassword", pass);
  form.append("recipientEmail", receiver);
  form.append("subject", subject);
  form.append("body", body);

  const att = q("attachment").files[0];
  if (att) form.append("attachment", att);

  try {
    const res = await fetch("/send_email", { method: "POST", body: form });
    const json = await res.json();
    if (json.error) alert("Error: " + JSON.stringify(json.error));
    else alert(json.message || "Email result unknown");
  } catch (e) {
    console.error("Send email error:", e);
    alert("Send email failed: " + e.message);
  }
});
