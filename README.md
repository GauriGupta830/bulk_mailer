# 🚀 MailFlow Pro

**MailFlow Pro** is an AI-powered bulk email campaign platform that lets you upload leads from Excel/CSV files, generate personalized emails using AI, and send them directly through your Gmail account with real-time campaign tracking.

Built with **FastAPI** (Backend) and a **custom HTML/CSS/JavaScript dashboard** (Frontend), it integrates **Gmail OAuth 2.0** for secure email delivery and **Groq (LLaMA 3.3 70B)** for AI-powered content generation.

---

## ✨ Features

- 🔐 **Authentication**
  - Secure email/password signup and login
  - Session-based authentication

- 📊 **Interactive Dashboard**
  - Real-time campaign statistics
  - Delivery rate monitoring
  - Recent campaign history

- 📧 **Bulk Email Campaigns**
  - Import leads from Excel or CSV
  - Personalize emails using merge fields (`{Name}`, `{Company}`, etc.)
  - Launch bulk email campaigns

- 🤖 **AI Email Assistant**
  - Generate professional cold emails
  - Create AI-powered subject lines using **Groq LLaMA 3.3 70B**

- 📁 **Email Templates**
  - Save reusable templates
  - Load templates into new campaigns instantly

- 📈 **Reports & Analytics**
  - Export campaign results as CSV or Excel

- 🔗 **Gmail OAuth 2.0**
  - Send emails directly from your Gmail account
  - No third-party SMTP server required

- 🎨 **Custom Themes**
  - Indigo
  - Sunset
  - Ocean
  - Forest

---

# 🛠 Tech Stack

| Layer | Technology |
|--------|------------|
| **Backend** | FastAPI, Uvicorn |
| **Database** | SQLite |
| **Frontend** | HTML, CSS, JavaScript |
| **Email Service** | Gmail API + OAuth 2.0 |
| **AI** | Groq API (LLaMA 3.3 70B) |
| **Data Processing** | Pandas, OpenPyXL |

---

# 📦 Installation

## 1️⃣ Clone the Repository

```bash
git clone https://github.com/<your-username>/mailflow-pro.git
cd mailflow-pro
```

---

## 2️⃣ Create a Virtual Environment

### Windows

```bash
python -m venv venv
venv\Scripts\activate
```

### macOS / Linux

```bash
python -m venv venv
source venv/bin/activate
```

---

## 3️⃣ Install Dependencies

```bash
pip install -r requirements.txt
```

---

## 4️⃣ Configure Environment Variables

### Windows

```bash
copy .env.example .env
```

### macOS / Linux

```bash
cp .env.example .env
```

Update the `.env` file with your credentials.

| Variable | Description |
|----------|-------------|
| `SECRET_KEY` | Random secure secret key |
| `GROQ_API_KEY` | API key from Groq Console |
| `OAUTH_REDIRECT_URI` | `http://localhost:8000/oauth_callback` |
| `GOOGLE_CLIENT_SECRETS` | Path to `client_secrets.json` |
| `SEND_DELAY_SECONDS` | Delay between emails (Default: 1.5) |
| `DB_PATH` | SQLite database path |

---

## 5️⃣ Configure Google OAuth

1. Open **Google Cloud Console**
2. Navigate to:

```
APIs & Services → Credentials
```

3. Create an **OAuth 2.0 Client ID**
4. Select **Web Application**
5. Add the following Redirect URI:

```
http://localhost:8000/oauth_callback
```

6. Download the credentials JSON file.
7. Save it as:

```
client_secrets.json
```

inside the project root directory.

---

## 6️⃣ Run the Application

```bash
uvicorn main:app --reload --port 8000
```

Open your browser and visit:

```
http://localhost:8000
```

---

# 📁 Project Structure

```text
mailflow-pro/
├── main.py                       # FastAPI application entry point
├── requirements.txt              # Python dependencies
├── .env.example                  # Environment variables template
│
├── static/
│   └── index.html                # Frontend dashboard
│
├── backend/
│   ├── auth/
│   │   └── auth.py               # User authentication & sessions
│   │
│   ├── campaigns/
│   │   └── campaigns.py          # Campaign, lead & template CRUD
│   │
│   ├── ai/
│   │   └── ai_features.py        # AI email & subject generation
│   │
│   ├── utils/
│   │   └── excel_processor.py    # Excel/CSV processing
│   │
│   └── reports/
│       └── reports.py            # CSV & Excel report export
│
├── database/
│   └── schema.py                 # SQLite schema & database connection
│
└── services/
    └── email_engine.py           # Gmail OAuth & email sending engine

