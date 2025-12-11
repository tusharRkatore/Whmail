// translator.js — recorder + UI handlers (frontend append-on-continue, Option A)

(() => {
  // ---------- helpers ----------
  const q = (id) => document.getElementById(id);

  // config: how many seconds to auto-record by default
  const DEFAULT_SECONDS = 6; // increase if you want longer recordings

  // state
  let mediaRecorder = null;
  let audioChunks = [];
  let isRecording = false;

  function setRecordingState(state) {
    isRecording = state;
    // disable start buttons while recording
    q("speakSubjectBtn").disabled = state;
    q("continueSubjectBtn").disabled = state;
    q("speakBodyBtn").disabled = state;
    q("continueBodyBtn").disabled = state;
    q("stopBtn").disabled = !state;
  }

  // ---------- recording ----------
  async function startRecording() {
    audioChunks = [];
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaRecorder = new MediaRecorder(stream);

      mediaRecorder.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) audioChunks.push(e.data);
      };

      // ensure mic tracks are stopped when recorder stops
      mediaRecorder.onstop = () => {
        try {
          stream.getTracks().forEach((t) => t.stop());
        } catch (e) {}
      };

      mediaRecorder.start();
      setRecordingState(true);
      console.log("Recording started");
      return true;
    } catch (err) {
      console.error("getUserMedia error:", err);
      alert(
        "Cannot access microphone. Allow microphone permission and try again."
      );
      throw err;
    }
  }

  function stopRecorderAndGetBlob() {
    return new Promise((resolve, reject) => {
      if (!mediaRecorder) return reject(new Error("Recorder not started"));

      // when onstop fires, the blob will be available
      mediaRecorder.onstop = () => {
        const blob = new Blob(audioChunks, {
          type: audioChunks[0]?.type || "audio/webm",
        });
        mediaRecorder = null;
        setRecordingState(false);
        resolve(blob);
      };

      try {
        mediaRecorder.stop();
      } catch (err) {
        reject(err);
      }
    });
  }

  function blobToFile(blob, filename) {
    try {
      return new File([blob], filename, { type: blob.type });
    } catch (e) {
      // older browsers fallback
      blob.name = filename;
      return blob;
    }
  }

  // ---------- send to server ----------
  async function sendBlobToServer(blob, isSubject, appendFlag) {
    if (!blob) {
      alert("No audio recorded.");
      return null;
    }

    const file = blobToFile(blob, `recording_${Date.now()}.webm`);
    const form = new FormData();
    // backend expects "audio_file"
    form.append("audio_file", file);
    form.append("inputLang", q("inputLang").value || "en");
    // we keep appendFlag for frontend logic (backend may ignore it)
    form.append("append", appendFlag ? "true" : "false");
    form.append("isSubject", isSubject ? "true" : "false");

    try {
      const resp = await fetch("/start_recognition", {
        method: "POST",
        body: form,
      });

      // parse JSON safely
      const json = await resp
        .json()
        .catch(() => ({ error: "Invalid JSON from server" }));

      if (!resp.ok) {
        const errMsg =
          json && json.error ? json.error : `Server responded ${resp.status}`;
        console.error("Server error:", errMsg);
        alert("Recognition failed: " + errMsg);
        return null;
      }

      // expected { text: "..." }
      return json.text || null;
    } catch (err) {
      console.error("Network/Fetch error:", err);
      alert("Network error while sending audio: " + (err.message || err));
      return null;
    }
  }

  // wrapper to record for seconds and send
  async function recordForSecondsThenSend(seconds, isSubject, appendFlag) {
    try {
      await startRecording();
    } catch (err) {
      return null;
    }

    return new Promise((resolve) => {
      // auto-stop after seconds
      setTimeout(async () => {
        let blob;
        try {
          blob = await stopRecorderAndGetBlob();
        } catch (err) {
          console.error("Stop error:", err);
          alert("Failed to stop recording.");
          resolve(null);
          return;
        }

        const text = await sendBlobToServer(blob, isSubject, appendFlag);
        resolve(text);
      }, seconds * 1000);
    });
  }

  // ---------- UI wiring ----------
  async function onSpeakSubject() {
    q("recognizedSubject").value = "Recording...";
    const text = await recordForSecondsThenSend(DEFAULT_SECONDS, true, false);
    if (text) {
      q("recognizedSubject").value = text; // start fresh
    } else {
      // If null, keep previous content (do not overwrite) and show message
      if (!q("recognizedSubject").value) q("recognizedSubject").value = "";
    }
  }

  async function onContinueSubject() {
    // preserve existing text and append new text when returned
    q("recognizedSubject").value =
      (q("recognizedSubject").value || "") + " [recording...]";
    const text = await recordForSecondsThenSend(DEFAULT_SECONDS, true, true);
    // Replace the temporary "[recording...]" suffix with real text (append)
    const prefix = (q("recognizedSubject").value || "").replace(
      /\s*\[recording\.\.\.\]$/,
      ""
    );
    if (text) {
      q("recognizedSubject").value = (prefix + " " + text).trim();
    } else {
      // remove the temp marker if failed
      q("recognizedSubject").value = prefix.trim();
    }
  }

  async function onSpeakBody() {
    q("recognizedBody").value = "Recording...";
    const text = await recordForSecondsThenSend(DEFAULT_SECONDS, false, false);
    if (text) {
      q("recognizedBody").value = text;
    } else {
      if (!q("recognizedBody").value) q("recognizedBody").value = "";
    }
  }

  async function onContinueBody() {
    q("recognizedBody").value =
      (q("recognizedBody").value || "") + " [recording...]";
    const text = await recordForSecondsThenSend(DEFAULT_SECONDS, false, true);
    const prefix = (q("recognizedBody").value || "").replace(
      /\s*\[recording\.\.\.\]$/,
      ""
    );
    if (text) {
      q("recognizedBody").value = (prefix + " " + text).trim();
    } else {
      q("recognizedBody").value = prefix.trim();
    }
  }

  // manual stop and send (if user wants to stop early)
  q("stopBtn").addEventListener("click", async () => {
    if (isRecording && mediaRecorder) {
      try {
        // stop recorder and immediately send captured audio
        const blob = await stopRecorderAndGetBlob();
        // determine if we were recording subject or body by placeholder text
        // But we don't track which one was recording — safe approach: ask user to click appropriate button.
        alert(
          "Recording stopped. To send, click the same Speak/Continue button again."
        );
      } catch (err) {
        console.error("Stop error:", err);
        alert("Failed to stop recording.");
      }
    } else {
      alert("No active recording to stop.");
    }
  });

  // translation
  q("translateBtn").addEventListener("click", async () => {
    const subjectText = q("recognizedSubject").value || "";
    const bodyText = q("recognizedBody").value || "";
    const outLang = q("outputLang").value || "en";

    // subject
    try {
      const res = await fetch("/translate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: subjectText, outputLang: outLang }),
      });
      const data = await res.json();
      q("translatedSubject").value = data.translated || data.error || "";
    } catch (err) {
      console.error("Translate subject error", err);
      alert("Translation (subject) failed");
    }

    // body
    try {
      const res = await fetch("/translate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: bodyText, outputLang: outLang }),
      });
      const data = await res.json();
      q("translatedBody").value = data.translated || data.error || "";
    } catch (err) {
      console.error("Translate body error", err);
      alert("Translation (body) failed");
    }
  });

  // send email
  q("sendEmailBtn").addEventListener("click", async () => {
    const senderEmail = q("senderEmail").value;
    const senderPassword = q("senderpassword").value;
    const recipientEmail = q("recipientEmail").value;
    const subject =
      q("translatedSubject").value || q("recognizedSubject").value;
    const body = q("translatedBody").value || q("recognizedBody").value;
    const attachment = q("attachment").files[0];

    if (
      !senderEmail ||
      !senderPassword ||
      !recipientEmail ||
      !subject ||
      !body
    ) {
      alert(
        "Fill sender, app password, recipient, subject and body before sending."
      );
      return;
    }

    const form = new FormData();
    form.append("senderEmail", senderEmail);
    form.append("senderPassword", senderPassword);
    form.append("recipientEmail", recipientEmail);
    form.append("subject", subject);
    form.append("body", body);
    if (attachment) form.append("attachment", attachment);

    try {
      const res = await fetch("/send_email", { method: "POST", body: form });
      const json = await res.json();
      alert(json.message || json.error || "No response");
    } catch (err) {
      console.error("Send email error:", err);
      alert("Failed to send email: " + err.message);
    }
  });

  // upload file (separate)
  q("uploadBtn").addEventListener("click", async () => {
    const file = q("attachment").files[0];
    if (!file) {
      alert("Select a file to upload");
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
    } catch (err) {
      console.error("Upload error:", err);
      alert("Upload failed");
    }
  });

  // attach button handlers
  q("speakSubjectBtn").addEventListener("click", onSpeakSubject);
  q("continueSubjectBtn").addEventListener("click", onContinueSubject);
  q("speakBodyBtn").addEventListener("click", onSpeakBody);
  q("continueBodyBtn").addEventListener("click", onContinueBody);

  // initial button state
  setRecordingState(false);
})();
