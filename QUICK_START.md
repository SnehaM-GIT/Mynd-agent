# 🚀 QUICK START GUIDE - Entrepreneur AI Agent

## ⚡ 2-Minute Setup

### 1. Install Dependencies
```bash
cd c:\Users\sneha\Desktop\Project\entrepreneur-agent
pip install -r requirements.txt
```

### 2. Create `.env` File
```bash
# Create a new file called .env in the project folder with:
GROQ_API_KEY=gsk_your_key_from_groq_console
```

### 3. Get credentials.json
1. Go to https://console.cloud.google.com
2. Create/Select a project
3. Enable Calendar API
4. Create OAuth 2.0 credentials (Desktop app)
5. Download JSON and save as `credentials.json` in project root

### 4. Start the App
```bash
chainlit run app.py -w
```

Browser opens → Chat interface ready! 🎉

---

## 📝 TEST IN 5 MINUTES

Copy & paste these commands in the chat:

### Calendar Tests (✅ Should work immediately)
```
Block tomorrow at 2pm for team meeting

What do I have on friday?

Create a recurring standup every monday 9am for 4 weeks

Delete the team meeting tomorrow
```

### Networking Tests (✅ Should work immediately)
```
I met Rajesh Kumar at Nasscom. He's VP of TechCorp. Email: rajesh@techcorp.com

Show me all my contacts

Send Rajesh a follow-up message

/contacts
```

### Upload Business Card
- Click the image upload button
- Select a business card photo
- Type the event name (e.g., "Nasscom")
- Confirm extraction

---

## 🎯 WHAT'S WORKING RIGHT NOW

| Feature | Example Command | Status |
|---------|-----------------|--------|
| Create Events | "Block tomorrow 2pm for meeting" | ✅ Works |
| View Calendar | "What's on Friday?" | ✅ Works |
| Delete Events | "Delete tomorrow's meeting" | ✅ Works |
| Recurring Events | "Every monday 9am for 4 weeks" | ✅ Works |
| Save Contacts | "I met John at Nasscom..." | ✅ Works |
| Business Cards | Upload image → Auto-extract | ✅ Works |
| Follow-up Messages | "Send John a message" | ✅ Works |
| Contact Search | "Show contacts from Nasscom" | ✅ Works |
| Daily Brief | "/brief" | ✅ Works |
| Stats | "/stats" | ✅ Works |

---

## ❌ NOT YET IMPLEMENTED

- Application form filling
- Social media integrations
- Call logs access
- Data encryption
- WhatsApp API auto-send

(See IMPLEMENTATION_ANALYSIS.md for details on how to add these)

---

## 🆘 COMMON ISSUES

| Issue | Fix |
|-------|-----|
| "credentials.json not found" | Download from Google Cloud Console |
| "GROQ_API_KEY not found" | Create .env with: GROQ_API_KEY=your_key |
| Calendar not syncing | Check Google account has Calendar API enabled |
| Port 8000 in use | `chainlit run app.py --port 3001` |
| Business card OCR failing | Use clear JPG/PNG image |

---

## 📁 Project Structure
```
entrepreneur-agent/
├── app.py                 ← Main app, START HERE
├── calendar_tool.py       ← Calendar functions
├── networking_tool.py     ← Contacts & follow-ups
├── daily_brief.py         ← Morning summary
├── requirements.txt       ← Dependencies
├── credentials.json       ← Download from Google (you create)
├── .env                   ← Add GROQ_API_KEY (you create)
└── contacts/             ← Auto-created
    ├── contacts.json
    └── my_profile.json
```

---

## 🔧 PROFILE CUSTOMIZATION

Edit `contacts/my_profile.json` to change your intro:
```json
{
  "name": "Suriya Jayan",
  "university": "Anna University",
  "domains": "chemical engineering and finance",
  "org": "ITNT",
  "linkedin": "https://www.linkedin.com/in/suriya-jayan-af51705",
  "instagram": "https://www.instagram.com/suriyajayan.a",
  "tagline": "I'm always keen on building with ambitious founders..."
}
```

This will auto-inject into all follow-up messages! 🎯

---

## 📊 DATABASE LOCATION

- **Contacts:** `contacts/contacts.json`
- **Your Profile:** `contacts/my_profile.json`
- **Conversation History:** `histories/history_[user_id].json`
- **Google Tokens:** `tokens/token_[user_id].json`

All files auto-created on first use. No manual setup needed! ✅

---

## 🧪 FULL TEST SCRIPT (5-10 minutes)

```
1. Chat: "I met Priya Singh at Voko Run. She's PM at Flipcart"
   Expected: Contact saved with score 70-75

2. Upload: Business card image
   Expected: Fields auto-extracted

3. Chat: "Show my contacts"
   Expected: List with priority scores

4. Chat: "Send Priya a message"
   Expected: WhatsApp format message shown

5. Chat: "Sent it"
   Expected: Message marked as sent ✅

6. Chat: "Block friday 2pm for investor call"
   Expected: Event created in Google Calendar

7. Chat: "What do I have friday?"
   Expected: Shows the investor call

8. Chat: "/brief"
   Expected: Morning summary with calendar + networking

9. Chat: "/stats"
   Expected: Networking metrics dashboard

10. Chat: "/contacts"
    Expected: All contacts sorted by priority
```

Success = all 10 show expected output! ✅

---

## 💡 TIPS FOR BEST RESULTS

1. **Natural language works best:**
   - ✅ "Block thursday 2pm for meeting"
   - ✅ "What's my schedule tomorrow?"
   - ✅ "I met Rajesh Kumar at Nasscom"

2. **Contact info helps scoring:**
   - Add phone → +30 points
   - Add email → +20 points
   - Add LinkedIn → +15 points

3. **Business cards work best with:**
   - Clear lighting
   - High-resolution JPG/PNG
   - Straight angle (not tilted)

4. **Follow-ups are scored by:**
   - Contact freshness (recent = higher score)
   - Number of fields filled
   - Whether already sent message

---

## 🔐 PRIVACY NOTE

Your data is stored locally on your machine:
- ✅ Contacts saved in `contacts/contacts.json`
- ✅ Google tokens stored in `tokens/` 
- ✅ History stored in `histories/`
- ✅ NOT sent to any external server (except Google Calendar API)

To backup: Copy the `contacts/` and `histories/` folders!

---

## 🚀 NEXT STEPS

1. ✅ Run the app
2. ✅ Test all 10 features above
3. ✅ Customize your profile in `contacts/my_profile.json`
4. ✅ Read IMPLEMENTATION_ANALYSIS.md for missing features
5. ✅ Decide which missing features to implement first

---

## 📞 COMMAND REFERENCE

```
# CALENDAR COMMANDS
Block [date] [time] for [event]
Create [recurring pattern] for [event]
What do I have on [date]?
Delete [event] on [date]

# NETWORKING COMMANDS
I met [name] at [event]
Send [name] a follow-up message
Show all my contacts
Show contacts from [event]
/contacts (list all)
/stats (analytics dashboard)

# SYSTEM COMMANDS
/brief (morning summary)
/switchaccount (change Google account)
/clearhistory (forget conversations, keep data)
```

---

## ✨ QUALITY CHECKLIST

After running tests, verify:
- [ ] Google Calendar syncing works
- [ ] Contacts saving correctly
- [ ] Messages personalize with your profile
- [ ] Search finds contacts
- [ ] Scores calculate properly
- [ ] Dates parse naturally
- [ ] No errors in console
- [ ] Profile auto-injects into messages

Good luck! 🚀
