const profileForm = document.querySelector("#profileForm");
const completionPercent = document.querySelector("#completionPercent");
const completionBar = document.querySelector("#completionBar");
const completionHint = document.querySelector("#completionHint");
const profileName = document.querySelector("#profileName");
const profileMeta = document.querySelector("#profileMeta");
const previewTitle = document.querySelector("#previewTitle");
const profilePreview = document.querySelector("#profilePreview");
const avatarButton = document.querySelector("#avatarButton");
const chatDrawer = document.querySelector("#chatDrawer");
const chatToggle = document.querySelector("#chatToggle");
const chatClose = document.querySelector("#chatClose");
const messages = document.querySelector("#messages");
const chatForm = document.querySelector("#chatForm");
const chatInput = document.querySelector("#chatInput");

const previewFields = [
  ["email", "Email"],
  ["phone", "Phone"],
  ["university", "Affiliation"],
  ["domains", "Domains"],
  ["org", "Network"],
  ["linkedin", "LinkedIn"],
  ["instagram", "Instagram"],
  ["tagline", "Value line"],
];

function initials(name) {
  const parts = String(name || "Mynd").trim().split(/\s+/).filter(Boolean);
  return parts.slice(0, 2).map((part) => part[0]).join("").toUpperCase() || "M";
}

function setForm(profile) {
  for (const element of profileForm.elements) {
    if (!element.name) continue;
    element.value = profile[element.name] || "";
  }
}

function renderProfile(profile) {
  const completion = profile.completion || { percent: 0, missing: [] };
  completionPercent.textContent = `${completion.percent}%`;
  completionBar.style.width = `${completion.percent}%`;
  completionHint.textContent = completion.complete
    ? "Your profile is ready. Mynd will reuse it automatically."
    : `Missing: ${completion.missing.join(", ") || "profile details"}`;

  const name = profile.name || "Set up your profile";
  profileName.textContent = name;
  profileMeta.textContent = profile.setup_complete
    ? "Ready for personalized tasks"
    : "Complete the form to personalize Mynd";
  avatarButton.textContent = initials(profile.name);
  previewTitle.textContent = profile.name || "No profile saved yet";

  profilePreview.innerHTML = "";
  for (const [key, label] of previewFields) {
    const value = profile[key];
    if (!value) continue;
    const wrapper = document.createElement("div");
    const dt = document.createElement("dt");
    const dd = document.createElement("dd");
    dt.textContent = label;
    dd.textContent = value;
    wrapper.append(dt, dd);
    profilePreview.append(wrapper);
  }
}

async function loadProfile() {
  const response = await fetch("/api/profile");
  const profile = await response.json();
  setForm(profile);
  renderProfile(profile);
}

profileForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = Object.fromEntries(new FormData(profileForm).entries());
  const response = await fetch("/api/profile", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const profile = await response.json();
  renderProfile(profile);
  addMessage("assistant", "Profile saved. You can now ask Mynd to draft follow-ups, save contacts, or prepare application answers.");
});

function addMessage(role, text) {
  const bubble = document.createElement("div");
  bubble.className = `message ${role}`;
  bubble.textContent = text;
  messages.appendChild(bubble);
  messages.scrollTop = messages.scrollHeight;
}

async function sendChat(text) {
  const clean = text.trim();
  if (!clean) return;
  addMessage("user", clean);
  chatInput.value = "";
  const pending = document.createElement("div");
  pending.className = "message assistant";
  pending.textContent = "Working on it...";
  messages.appendChild(pending);
  messages.scrollTop = messages.scrollHeight;

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: clean }),
    });
    const data = await response.json();
    pending.textContent = data.reply || "Done.";
  } catch (error) {
    pending.textContent = "I could not complete that request. Check the server terminal for details.";
  }
  messages.scrollTop = messages.scrollHeight;
}

chatForm.addEventListener("submit", (event) => {
  event.preventDefault();
  sendChat(chatInput.value);
});

chatInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    sendChat(chatInput.value);
  }
});

chatToggle.addEventListener("click", () => chatDrawer.classList.add("open"));
chatClose.addEventListener("click", () => chatDrawer.classList.remove("open"));
avatarButton.addEventListener("click", () => {
  document.querySelector(".profile-panel").scrollIntoView({ behavior: "smooth" });
});

document.querySelectorAll("[data-prompt]").forEach((button) => {
  button.addEventListener("click", () => {
    chatDrawer.classList.add("open");
    chatInput.value = button.dataset.prompt;
    chatInput.focus();
  });
});

addMessage(
  "assistant",
  "Welcome to Mynd. I can save networking contacts, draft follow-up messages, prepare application answers from your saved profile, and keep your business context ready. Tell me the task in plain English."
);

loadProfile();
