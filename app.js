const generateBtn = document.getElementById("generateBtn");
const noteTextEl = document.getElementById("noteText");
const flagsEl = document.getElementById("flags");
const downloadPdfBtn = document.getElementById("downloadPdfBtn");

let lastGeneratedData = null;
let lastPayload = null;

function getApiBaseUrl() {
  if (window.location.port === "5500") {
    return "http://127.0.0.1:8000";
  }
  return "";
}

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
  downloadPdfBtn.style.display = "none";

  try {
    const endpoint = `${getApiBaseUrl()}/api/generate-note`;
    const res = await fetch(endpoint, {
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
    lastGeneratedData = data;
    lastPayload = payload;

    flagsEl.innerHTML = "";
    (data.quality_flags || []).forEach((flag) => {
      const li = document.createElement("li");
      li.textContent = flag;
      flagsEl.appendChild(li);
    });

    downloadPdfBtn.style.display = "inline-block";
  } catch (err) {
    noteTextEl.textContent = `Error generating note: ${err.message}`;
    downloadPdfBtn.style.display = "none";
  }
}

function downloadPdf() {
  if (!lastGeneratedData || !lastPayload) {
    alert("No note to download. Please generate a note first.");
    return;
  }

  const element = document.createElement("div");
  element.style.padding = "20px";
  element.style.fontFamily = "Arial, sans-serif";
  element.style.fontSize = "11pt";
  element.style.lineHeight = "1.6";

  const heading = `<h2 style="text-align:center; margin-bottom:5px;">Clinical Consultation Note</h2>
    <hr style="margin:10px 0;" />`;

  const doctorPatientInfo = `
    <table style="width:100%; margin-bottom:15px; border-collapse:collapse;">
      <tr>
        <td style="width:50%;"><strong>Doctor:</strong> ${lastPayload.doctor_name || "Not provided"}</td>
        <td style="width:50%;"><strong>Date:</strong> ${new Date().toLocaleDateString()}</td>
      </tr>
      <tr>
        <td><strong>Patient:</strong> ${lastPayload.patient_name || "Unknown"}</td>
        <td><strong>Age/Sex:</strong> ${lastPayload.age || "NA"}/${lastPayload.sex || "NA"}</td>
      </tr>
    </table>`;

  const noteContent = `<pre style="white-space: pre-wrap; font-family: 'Courier New', monospace; font-size:10pt; margin:15px 0; padding:10px; background:#f5f5f5; border-left:3px solid #0e8a61;">
${lastGeneratedData.note_text}
    </pre>`;

  const prescriptionSection = `
    <div style="margin-top:20px; padding-top:15px; border-top:1px solid #ccc;">
      <h3 style="margin-bottom:10px;">Prescription:</h3>
      <table style="width:100%; border-collapse:collapse;">
        <tr>
          <td style="border:1px solid #999; padding:8px; height:30px;"></td>
          <td style="border:1px solid #999; padding:8px; height:30px;"></td>
        </tr>
        <tr>
          <td style="border:1px solid #999; padding:8px; height:30px;"></td>
          <td style="border:1px solid #999; padding:8px; height:30px;"></td>
        </tr>
        <tr>
          <td style="border:1px solid #999; padding:8px; height:30px;"></td>
          <td style="border:1px solid #999; padding:8px; height:30px;"></td>
        </tr>
      </table>
      <div style="margin-top:20px;">
        <p><strong>Doctor's Signature:</strong> ___________________</p>
      </div>
    </div>`;

  element.innerHTML = heading + doctorPatientInfo + noteContent + prescriptionSection;

  const options = {
    margin: 10,
    filename: `clinical_note_${lastPayload.patient_name || "patient"}_${new Date().toISOString().split("T")[0]}.pdf`,
    image: { type: "jpeg", quality: 0.98 },
    html2canvas: { scale: 2 },
    jsPDF: { orientation: "portrait", unit: "mm", format: "a4" },
  };

  html2pdf().set(options).from(element).save();
}

generateBtn.addEventListener("click", generateNote);
downloadPdfBtn.addEventListener("click", downloadPdf);
