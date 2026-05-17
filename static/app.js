const profileForm = document.querySelector("#profileForm");
const completionPercent = document.querySelector("#completionPercent");
const completionBar = document.querySelector("#completionBar");
const completionHint = document.querySelector("#completionHint");
const profileName = document.querySelector("#profileName");
const profileMeta = document.querySelector("#profileMeta");
const previewTitle = document.querySelector("#previewTitle");
const profilePreview = document.querySelector("#profilePreview");
const avatarButton = document.querySelector("#avatarButton");
const profilePhoto = document.querySelector("#profilePhoto");
const profileInitial = document.querySelector("#profileInitial");
const profilePhotoInput = document.querySelector("#profilePhotoInput");
const chatDrawer = document.querySelector("#chatDrawer");
const chatToggle = document.querySelector("#chatToggle");
const chatClose = document.querySelector("#chatClose");
const messages = document.querySelector("#messages");
const chatForm = document.querySelector("#chatForm");
const chatInput = document.querySelector("#chatInput");
const businessCardInput = document.querySelector("#businessCardInput");
const csvInput = document.querySelector("#csvInput");
const contactModal = document.querySelector("#contactModal");
const contactForm = document.querySelector("#contactForm");
const contactModalClose = document.querySelector("#contactModalClose");
const contactModalTitle = document.querySelector("#contactModalTitle");

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
  profileInitial.textContent = initials(profile.name);
  if (profile.avatar_url) {
    profilePhoto.src = profile.avatar_url;
    profilePhoto.parentElement.classList.add("has-photo");
  } else {
    profilePhoto.parentElement.classList.remove("has-photo");
  }
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
  if (!response.ok) {
    const error = await response.json();
    addMessage("assistant", error.detail || "Please check the profile fields.");
    return;
  }
  const profile = await response.json();
  renderProfile(profile);
  addMessage("assistant", "Profile saved. You can now ask Mynd to draft follow-ups, save contacts, or prepare application answers.");
});

profilePhotoInput.addEventListener("change", async () => {
  const file = profilePhotoInput.files[0];
  if (!file) return;
  const form = new FormData();
  form.append("file", file);
  const response = await fetch("/api/profile/photo", { method: "POST", body: form });
  if (response.ok) {
    const data = await response.json();
    profilePhoto.src = data.avatar_url;
    profilePhoto.parentElement.classList.add("has-photo");
  }
  profilePhotoInput.value = "";
});

function addMessage(role, text) {
  const bubble = document.createElement("div");
  bubble.className = `message ${role}`;
  bubble.innerHTML = linkify(text);
  messages.appendChild(bubble);
  messages.scrollTop = messages.scrollHeight;
}

function linkify(text) {
  const escaped = String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
  return escaped
    .replace(/(https?:\/\/[^\s]+)/g, '<a href="$1" target="_blank" rel="noreferrer">$1</a>')
    .replace(/(mailto:[^\s]+)/g, '<a href="$1">$1</a>');
}

async function sendChat(text) {
  const clean = text.trim();
  if (!clean) return;
  if (/\b(i\s+)?met\s+/i.test(clean)) {
    addMessage("user", clean);
    chatInput.value = "";
    const response = await fetch("/api/contacts/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: clean }),
    });
    const data = await response.json();
    openContactModal(data.contact || {}, data.duplicate || null);
    addMessage("assistant", data.duplicate ? "I found a possible duplicate. Review it before merging." : "I extracted the contact. Review it before saving.");
    return;
  }
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

function openContactModal(contact = {}, duplicate = null) {
  contactModal.classList.remove("hidden");
  contactModalTitle.textContent = duplicate ? "Review duplicate before merge" : "Review before saving";
  for (const element of contactForm.elements) {
    if (!element.name) continue;
    element.value = contact[element.name] || "";
  }
}

contactModalClose.addEventListener("click", () => contactModal.classList.add("hidden"));

contactForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = Object.fromEntries(new FormData(contactForm).entries());
  const response = await fetch("/api/contacts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await response.json();
  contactModal.classList.add("hidden");
  addMessage("assistant", `${data.message}\n\n${data.contact.name} is now in your contacts.`);
});

businessCardInput.addEventListener("change", async () => {
  const file = businessCardInput.files[0];
  if (!file) return;
  const form = new FormData();
  form.append("file", file);
  addMessage("user", `Uploaded business card: ${file.name}`);
  const response = await fetch("/api/business-card", { method: "POST", body: form });
  const data = await response.json();
  openContactModal(data.contact || {}, data.duplicate || null);
  businessCardInput.value = "";
});

csvInput.addEventListener("change", async () => {
  const file = csvInput.files[0];
  if (!file) return;
  const form = new FormData();
  form.append("file", file);
  const response = await fetch("/api/contacts/import", { method: "POST", body: form });
  const data = await response.json();
  addMessage("assistant", `Imported ${data.imported || 0} contact(s) from CSV.`);
  csvInput.value = "";
});

addMessage(
  "assistant",
  "Welcome to Mynd. I can save networking contacts, draft follow-up messages, prepare application answers from your saved profile, and schedule Google Calendar tasks. Tell me the task in plain English."
);

loadProfile();
