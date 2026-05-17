# Mynd Entrepreneur Agent

Mynd is an AI-powered agent designed specifically for entrepreneurs. It automates high-leverage tasks like networking follow-ups, calendar management, and application form drafting using a powerful LLM backend.

## Features

### 1. Smart Networking Follow-ups
- Generates highly personalized follow-up messages based on who you met, where you met them, and conversation notes.
- Uses Groq LLM (Llama 3.3 70B) to seamlessly blend your profile, your tagline, and context into a human-sounding message.
- Supports WhatsApp, LinkedIn, and Email templates out of the box.

### 2. Calendar Management
- Integrates with Google Calendar.
- Create, query, and delete events directly via natural language (e.g., *"Block 2 hours tomorrow for deep work"*).
- Configurable Timezone using `MYND_TIMEZONE` and `MYND_UTC_OFFSET` to prevent hardcoded IST constraints.

### 3. Application & Grant Drafting
- Store private/sensitive information securely in an encrypted local vault.
- Automatically draft applications (startup grants, incubator applications) by passing form fields to the LLM to intelligently extract and answer questions based on your profile and vault data.

### 4. Interactive UIs
- **Chainlit App (`app.py`)**: A chat interface to interact with the agent natively.
- **FastAPI Web Dashboard (`web_app.py`)**: A structured web view for reviewing contacts, calendars, and analytics.

## Setup & Execution

### Prerequisites
1. Python 3.10+
2. A Groq API key for the LLM.
3. Google Calendar API credentials (`credentials.json`).

### Environment Variables
Copy `.env.example` to `.env` and fill in the required keys:
```
GROQ_API_KEY=your_groq_api_key_here
MYND_TIMEZONE=Asia/Kolkata
MYND_UTC_OFFSET=+05:30
```

### Running the App
**Start the Chat UI (Chainlit):**
```bash
chainlit run app.py -w
```

**Start the Web Dashboard (FastAPI):**
```bash
uvicorn web_app:app --reload
```

## Security & Storage
- Contacts, profile information, and vault data are stored locally in the `contacts/` and `data/` directories.
- Private info in the vault is encrypted using Fernet (AES).
- Keep your `credentials.json`, `token.json`, and `.secret.key` safe.
