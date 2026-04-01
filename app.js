const generateBtn = document.getElementById("generateBtn");
const noteTextEl = document.getElementById("noteText");
const jsonTextEl = document.getElementById("jsonText");
const flagsEl = document.getElementById("flags");

async function generateNote() {
  const payload = {
    doctor_name: document.getElementById("doctorName").value.trim(),
    patient_name: document.getElementById("patientName").value.trim(),
    age: parseInt(document.getElementById("age").value, 10) || null,
    sex: document.getElementById("sex").value,
    transcript: document.getElementById("transcript").value.trim(),
    gemini_api_key: document.getElementById("geminiApiKey").value.trim(),
    model: document.getElementById("geminiModel").value.trim() || "gemini-2.5-flash",
  };

  if (!payload.transcript || payload.transcript.length < 10) {
    alert("Please provide a meaningful consultation transcript.");
    return;
  }

  noteTextEl.textContent = "Generating note...";

  try {
    const res = await fetch("/api/generate-note", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      const errPayload = await res.json().catch(() => ({}));
      throw new Error(errPayload.detail || "Failed to generate note");
    }

    const data = await res.json();
    noteTextEl.textContent = data.note_text;
    jsonTextEl.textContent = JSON.stringify(data.structured, null, 2);

    flagsEl.innerHTML = "";
    (data.quality_flags || []).forEach((flag) => {
      const li = document.createElement("li");
      li.textContent = flag;
      flagsEl.appendChild(li);
    });
  } catch (err) {
    noteTextEl.textContent = `Error generating note: ${err.message}`;
  }
}

generateBtn.addEventListener("click", generateNote);
