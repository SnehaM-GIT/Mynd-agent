# 🛣️ IMPLEMENTATION ROADMAP - Missing Features

## 🎯 Priority Matrix

```
HIGH IMPACT + HIGH EFFORT → Do Third
├─ Application Form Filling

HIGH IMPACT + LOW EFFORT → Do First
├─ Data Encryption (contacts.json)

MEDIUM IMPACT + LOW EFFORT → Do Second
├─ Call Logs Integration
├─ Social Media Enrichment

MEDIUM IMPACT + HIGH EFFORT → Do Fourth
├─ Full Social Media Connectors (LinkedIn/Instagram)
```

---

## 🔒 FEATURE 1: DATA ENCRYPTION (Priority: 1, Effort: 2 hours)

### Current State
- Contacts saved in plain JSON at `contacts/contacts.json`
- No encryption
- No password protection
- Security risk if file accessed

### Implementation Plan

#### Step 1: Add `cryptography` to requirements.txt
```bash
pip install cryptography
```

#### Step 2: Create `security.py`
```python
# security.py
from cryptography.fernet import Fernet
import os
import json

ENCRYPTION_KEY_FILE = "contacts/.encryption_key"
CONTACTS_FILE = "contacts/contacts.json"

def generate_key():
    """Generate and save encryption key (run once)"""
    key = Fernet.generate_key()
    with open(ENCRYPTION_KEY_FILE, "wb") as f:
        f.write(key)
    return key

def load_key():
    """Load existing encryption key"""
    if not os.path.exists(ENCRYPTION_KEY_FILE):
        raise FileNotFoundError("Encryption key not found. Run generate_key() first.")
    with open(ENCRYPTION_KEY_FILE, "rb") as f:
        return f.read()

def encrypt_data(data: dict) -> bytes:
    """Encrypt contact data"""
    key = load_key()
    f = Fernet(key)
    json_str = json.dumps(data)
    encrypted = f.encrypt(json_str.encode())
    return encrypted

def decrypt_data(encrypted_data: bytes) -> dict:
    """Decrypt contact data"""
    key = load_key()
    f = Fernet(key)
    decrypted = f.decrypt(encrypted_data).decode()
    return json.loads(decrypted)

def migrate_to_encrypted():
    """One-time migration of unencrypted contacts to encrypted"""
    if not os.path.exists(CONTACTS_FILE):
        return
    
    # Load unencrypted
    with open(CONTACTS_FILE, "r") as f:
        contacts = json.load(f)
    
    # Encrypt and save
    encrypted = encrypt_data(contacts)
    with open(CONTACTS_FILE, "wb") as f:
        f.write(encrypted)
    
    print(f"✅ Migrated {len(contacts)} contacts to encrypted format")
```

#### Step 3: Update `networking_tool.py`
Replace plain JSON operations with encryption:

```python
# In networking_tool.py - replace load_contacts():
def load_contacts() -> list:
    from security import decrypt_data
    if os.path.exists(CONTACTS_FILE):
        with open(CONTACTS_FILE, "rb") as f:
            encrypted_data = f.read()
        return decrypt_data(encrypted_data)
    return []

# Replace save_contacts():
def save_contacts(contacts: list):
    from security import encrypt_data
    encrypted = encrypt_data(contacts)
    with open(CONTACTS_FILE, "wb") as f:
        f.write(encrypted)
```

#### Step 4: Test Encryption
```python
# test_encryption.py
from security import generate_key, encrypt_data, decrypt_data
import json

# First time setup
generate_key()

# Test encrypt/decrypt
test_data = {"name": "Rajesh", "email": "test@example.com"}
encrypted = encrypt_data(test_data)
decrypted = decrypt_data(encrypted)
assert decrypted == test_data
print("✅ Encryption working!")
```

### Migration Instructions
```bash
# 1. Install cryptography
pip install cryptography

# 2. Add security.py to project

# 3. Generate encryption key (one-time)
python -c "from security import generate_key; generate_key(); print('Key generated!')"

# 4. Migrate existing contacts
python -c "from security import migrate_to_encrypted; migrate_to_encrypted()"

# 5. Test everything still works
# Run the app and verify contacts load correctly
```

---

## 📞 FEATURE 2: CALL LOGS INTEGRATION (Priority: 2, Effort: 4 hours)

### Current State
- No call logs access
- Manual contact entry required
- Missing automatic context from calls

### Implementation Plan

#### Option A: Twilio Integration (Easiest)

**Install Twilio:**
```bash
pip install twilio
```

**Create `call_logs_tool.py`:**
```python
from twilio.rest import Client
import os
import json
import datetime
from dotenv import load_dotenv

load_dotenv()

# Get from https://twilio.com/console
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")

client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

def get_call_logs(limit=10):
    """
    Fetch recent call logs from Twilio
    Returns: List of calls with phone, duration, date
    """
    calls = client.calls.stream(limit=limit)
    
    call_logs = []
    for call in calls:
        call_logs.append({
            "phone": call.from_,
            "direction": call.direction,  # "inbound" or "outbound"
            "duration": call.duration,
            "date": call.date_created.isoformat(),
            "status": call.status,  # "completed", "failed", etc
            "recording_url": call.recording_url,  # if recorded
        })
    
    return call_logs

def enrich_contact_from_call(phone_number: str) -> dict:
    """
    Look up a phone number and check if it's in your contacts
    If not, create suggested contact entry
    """
    # Get all calls with this number
    calls = client.calls.stream(
        limit=5,
        from_=phone_number
    )
    
    call_count = len(list(calls))
    duration_total = sum(c.duration for c in calls)
    
    return {
        "phone": phone_number,
        "call_count": call_count,
        "total_duration": duration_total,
        "notes": f"Called {call_count} times, total {duration_total}s"
    }

def get_recent_calls_not_in_contacts():
    """
    Get calls from numbers not yet saved as contacts
    Useful for finding new networking opportunities
    """
    from networking_tool import load_contacts, get_all_contacts
    
    existing_phones = set()
    for contact in get_all_contacts():
        if contact.get("phone"):
            existing_phones.add(contact["phone"])
    
    calls = client.calls.stream(limit=20)
    new_calls = []
    
    for call in calls:
        phone = call.from_
        if phone not in existing_phones:
            new_calls.append({
                "phone": phone,
                "date": call.date_created.isoformat(),
                "duration": call.duration,
            })
    
    return new_calls
```

**Update `.env`:**
```
TWILIO_ACCOUNT_SID=your_account_sid_from_twilio
TWILIO_AUTH_TOKEN=your_auth_token_from_twilio
TWILIO_PHONE_NUMBER=+1234567890
```

**Integrate into `app.py`:**
```python
from call_logs_tool import get_recent_calls_not_in_contacts, enrich_contact_from_call

# Add to chat handler for "show recent calls" intent:
if "recent calls" in message.content.lower():
    calls = get_recent_calls_not_in_contacts()
    
    reply = "📞 Recent calls not yet saved as contacts:\n\n"
    for call in calls:
        reply += f"📱 {call['phone']} — {call['duration']}s on {call['date'][:10]}\n"
    
    reply += "\nReply with 'save [phone] as [name]' to add them!"
```

---

## 💼 FEATURE 3: APPLICATION FORM FILLING (Priority: 3, Effort: 8 hours)

### Current State
- No form integration
- Manual data entry to applications
- No tracking of submitted forms

### Implementation Plan

#### Step 1: Create `form_tool.py`
```python
# form_tool.py
import json
import os
from typing import Dict, List
from datetime import datetime

FORMS_DIR = "saved_forms"
SUBMISSIONS_DIR = "form_submissions"

os.makedirs(FORMS_DIR, exist_ok=True)
os.makedirs(SUBMISSIONS_DIR, exist_ok=True)

class FormTemplate:
    """Store reusable form templates"""
    def __init__(self, name: str, form_type: str, fields: List[Dict]):
        self.name = name
        self.form_type = form_type  # "google_forms", "typeform", "custom_url"
        self.fields = fields
        self.created_at = datetime.now().isoformat()
    
    def to_dict(self):
        return {
            "name": self.name,
            "type": self.form_type,
            "fields": self.fields,
            "created_at": self.created_at
        }

def save_form_template(template: FormTemplate):
    """Save a form template for reuse"""
    file_path = f"{FORMS_DIR}/{template.name}.json"
    with open(file_path, "w") as f:
        json.dump(template.to_dict(), f, indent=2)

def load_form_template(name: str) -> FormTemplate:
    """Load previously saved form template"""
    file_path = f"{FORMS_DIR}/{name}.json"
    with open(file_path, "r") as f:
        data = json.load(f)
    
    return FormTemplate(
        name=data["name"],
        form_type=data["type"],
        fields=data["fields"]
    )

def get_user_data(user_id: str) -> dict:
    """Get stored user data for auto-fill"""
    from networking_tool import load_profile
    
    profile = load_profile()
    
    return {
        "name": profile.get("name", ""),
        "email": profile.get("email", ""),
        "phone": profile.get("phone", ""),
        "linkedin": profile.get("linkedin", ""),
        "university": profile.get("university", ""),
        "organization": profile.get("org", ""),
        "bio": profile.get("tagline", ""),
    }

def auto_fill_form_data(template: FormTemplate, user_data: dict) -> dict:
    """
    Match form fields to user data and suggest values
    Returns: {field_name: suggested_value}
    """
    filled_data = {}
    
    field_name_lower = ""
    for field in template.fields:
        field_name = field.get("name", "").lower()
        
        # Try exact match in user_data
        for key, value in user_data.items():
            if key.lower() in field_name:
                filled_data[field["name"]] = value
                break
    
    return filled_data

def submit_form(template: FormTemplate, form_data: dict) -> dict:
    """
    Track form submission
    """
    submission = {
        "template": template.name,
        "fields": form_data,
        "submitted_at": datetime.now().isoformat(),
        "status": "submitted"
    }
    
    file_path = f"{SUBMISSIONS_DIR}/submission_{datetime.now().timestamp()}.json"
    with open(file_path, "w") as f:
        json.dump(submission, f, indent=2)
    
    return submission

def get_submission_history() -> List[Dict]:
    """Get all past form submissions"""
    submissions = []
    for file in os.listdir(SUBMISSIONS_DIR):
        if file.endswith(".json"):
            with open(f"{SUBMISSIONS_DIR}/{file}", "r") as f:
                submissions.append(json.load(f))
    
    return sorted(submissions, key=lambda x: x["submitted_at"], reverse=True)
```

#### Step 2: Google Forms Integration
```python
# In form_tool.py - add Google Forms handler
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google.auth.oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import re

SCOPES = ["https://www.googleapis.com/auth/forms", "https://www.googleapis.com/auth/drive"]

def get_forms_service(user_id):
    """Connect to Google Forms API"""
    creds = None
    token_path = f"tokens/forms_token_{user_id}.json"
    
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    
    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(
            "credentials.json", SCOPES
        )
        creds = flow.run_local_server(port=0)
        
        with open(token_path, "w") as token:
            token.write(creds.to_json())
    
    return build("forms", "v1", credentials=creds)

def extract_google_form_fields(form_url: str, user_id: str) -> List[Dict]:
    """
    Extract fields from Google Form URL
    Returns list of field names and types
    """
    # Extract form ID from URL
    # https://forms.gle/abc123 or 
    # https://docs.google.com/forms/d/e/FORM_ID/viewform
    
    match = re.search(r'(/d/e/|/d/)([a-zA-Z0-9-_]+)', form_url)
    if not match:
        raise ValueError("Invalid Google Forms URL")
    
    form_id = match.group(2)
    service = get_forms_service(user_id)
    
    try:
        form = service.forms().get(formId=form_id).execute()
        
        fields = []
        for item in form.get("items", []):
            field_info = {
                "id": item.get("itemId"),
                "title": item.get("title"),
                "type": list(item.get("questionItem", {}).keys())[0],
                "required": item.get("questionItem", {}).get("question", {}).get("required", False)
            }
            fields.append(field_info)
        
        return fields
    
    except Exception as e:
        raise Exception(f"Could not fetch form: {str(e)}")

def fill_google_form(form_url: str, form_data: dict, user_id: str) -> bool:
    """
    Programmatically fill and submit Google Form
    Note: Google Forms API doesn't support direct submission,
    so this would use Selenium for automation
    """
    try:
        from selenium import webdriver
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait, Select
        from selenium.webdriver.support import expected_conditions as EC
        
        driver = webdriver.Chrome()
        driver.get(form_url)
        
        # Wait for form to load
        wait = WebDriverWait(driver, 10)
        
        for field_name, value in form_data.items():
            try:
                # Try to find input by label
                input_elem = driver.find_element(By.XPATH, f"//label[contains(text(), '{field_name}')]/following::input")
                input_elem.send_keys(str(value))
            except Exception:
                pass
        
        # Click submit
        submit_btn = driver.find_element(By.XPATH, "//button[@type='submit']")
        submit_btn.click()
        
        driver.quit()
        return True
    
    except Exception as e:
        print(f"Form submission failed: {str(e)}")
        return False
```

#### Step 3: Integrate into `app.py`
```python
from form_tool import (
    save_form_template, load_form_template, extract_google_form_fields,
    auto_fill_form_data, submit_form, get_user_data, get_submission_history
)

# Add to chat handler:
if "save application form" in message.content.lower():
    # Extract form URL
    form_url = message.content
    
    try:
        fields = extract_google_form_fields(form_url, user_id)
        user_data = get_user_data(user_id)
        suggested = auto_fill_form_data_from_fields(fields, user_data)
        
        reply = f"📋 Found {len(fields)} fields in your form:\n\n"
        for field in fields:
            suggested_value = suggested.get(field["title"], "[Enter value]")
            reply += f"• **{field['title']}** ({field['type']})\n  Suggested: {suggested_value}\n"
        
        reply += "\nShould I fill these in and submit?"
    
    except Exception as e:
        reply = f"❌ Could not read form: {str(e)}"

if "submit the form" in message.content.lower():
    # Auto-fill and submit
    form_data = suggested
    result = submit_form(form_template, form_data)
    
    reply = f"✅ Form submitted!\n\nReference: {result['submitted_at']}"
```

---

## 🌐 FEATURE 4: SOCIAL MEDIA ENRICHMENT (Priority: 4, Effort: 6 hours)

### Current State
- Manual entry required
- No social profile lookups
- No contact enrichment

### Basic Implementation

#### Create `enrichment_tool.py`
```python
import requests
import json
import re
from typing import Dict

def enrich_linkedin_profile(linkedin_url: str) -> dict:
    """
    Fetch public LinkedIn profile data
    Note: Requires LinkedIn API or scraping (limited free tier)
    """
    try:
        # Using RapidAPI LinkedIn profile endpoint (free tier available)
        api_key = os.getenv("RAPIDAPI_KEY")
        
        response = requests.get(
            "https://linkedin-profile-data.p.rapidapi.com/get-profile",
            headers={
                "x-rapidapi-key": api_key,
                "x-rapidapi-host": "linkedin-profile-data.p.rapidapi.com"
            },
            params={"profileUrl": linkedin_url}
        )
        
        data = response.json()
        
        return {
            "name": data.get("fullName"),
            "title": data.get("headline"),
            "company": data.get("company"),
            "bio": data.get("about"),
            "image_url": data.get("profileImage"),
            "followers": data.get("followerCount"),
            "connections": data.get("connectionsCount")
        }
    
    except Exception as e:
        return {"error": str(e)}

def enrich_from_email_domain(email: str) -> dict:
    """
    Lookup company from email domain
    Using Hunter.io API (has free tier)
    """
    domain = email.split("@")[1]
    
    try:
        api_key = os.getenv("HUNTER_API_KEY")
        
        response = requests.get(
            f"https://api.hunter.io/v2/domain-search",
            params={
                "domain": domain,
                "api_key": api_key
            }
        )
        
        data = response.json()
        
        return {
            "company_name": data.get("domain", {}).get("name"),
            "company_website": data.get("domain", {}).get("website"),
            "company_employees": data.get("domain", {}).get("employees"),
            "industry": data.get("domain", {}).get("industry")
        }
    
    except Exception as e:
        return {}

def extract_social_from_text(text: str) -> dict:
    """
    Use regex to find social handles and URLs in text/contact info
    """
    socials = {}
    
    # LinkedIn
    linkedin_match = re.search(r'linkedin\.com/in/([\w\-]+)', text, re.I)
    if linkedin_match:
        socials["linkedin"] = f"https://linkedin.com/in/{linkedin_match.group(1)}"
    
    # Twitter/X
    twitter_match = re.search(r'(?:twitter|x)\.com/([\w]+)', text, re.I)
    if twitter_match:
        socials["twitter"] = f"https://twitter.com/{twitter_match.group(1)}"
    
    # Instagram
    insta_match = re.search(r'instagram\.com/([\w.]+)', text, re.I)
    if insta_match:
        socials["instagram"] = f"https://instagram.com/{insta_match.group(1)}"
    
    # Personal website
    website_match = re.search(r'https?://([a-zA-Z0-9\-\.]+\.[a-zA-Z]{2,})', text)
    if website_match:
        socials["website"] = website_match.group(0)
    
    return socials
```

---

## 🚀 IMPLEMENTATION PRIORITY GUIDE

### Week 1: Security
```bash
Day 1-2: Implement encryption
Day 3: Test with existing contacts
Day 4: Documentation
```

### Week 2-3: Call Logs
```bash
Day 1-2: Twilio API setup
Day 3: Integrate call logs
Day 4: Test and refine
```

### Week 4-5: Forms
```bash
Day 1-2: Form template system
Day 3: Google Forms integration
Day 4: Auto-fill logic
Day 5: Testing and edge cases
```

### Week 6: Enrichment
```bash
Day 1-2: Email domain enrichment
Day 3: LinkedIn profile lookup
Day 4: Integration and testing
```

---

## 📦 DEPENDENCIES TO ADD

```bash
# For encryption
pip install cryptography

# For Twilio
pip install twilio

# For form filling
pip install selenium google-auth-httplib2 google-auth-oauthlib

# For enrichment
pip install requests

# Add to requirements.txt:
cryptography==41.0.0
twilio==8.10.0
selenium==4.13.0
requests==2.31.0
```

---

## 🧪 TESTING EACH FEATURE

### Encryption Test
```python
python -c "
from security import generate_key, encrypt_data, decrypt_data
from networking_tool import load_contacts, add_contact

# Generate key
generate_key()

# Add test contact
test = {'name': 'Rajesh', 'company': 'TechCorp', 'event': 'Nasscom'}
add_contact(test)

# Load and verify
contacts = load_contacts()
assert contacts[0]['name'] == 'Rajesh'
print('✅ Encryption working!')
"
```

### Call Logs Test
```python
python -c "
from call_logs_tool import get_call_logs, get_recent_calls_not_in_contacts

# Get recent calls
calls = get_call_logs(limit=5)
print(f'Found {len(calls)} calls')

# Get calls not in contacts
new_calls = get_recent_calls_not_in_contacts()
print(f'Found {len(new_calls)} new contacts from calls')
"
```

### Forms Test
```python
python -c "
from form_tool import extract_google_form_fields, auto_fill_form_data, FormTemplate

# Test form extraction
url = 'https://docs.google.com/forms/d/e/YOUR_FORM_ID/viewform'
fields = extract_google_form_fields(url, 'test_user')
print(f'Found {len(fields)} fields in form')
"
```

---

## 💡 PRO TIPS

1. **Security First**: Always add encryption before handling sensitive data
2. **Test Early**: Test each feature individually before integration
3. **Document APIs**: Keep notes on API rate limits and costs
4. **Error Handling**: Add try-catch blocks for external API calls
5. **Backwards Compatibility**: Ensure old data still works with new features

