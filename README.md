# MailFlow Pro

AI-powered bulk email campaign platform — upload leads from Excel/CSV, personalize emails with AI, and send them via your Gmail account with real-time tracking.

Built with **FastAPI** (backend) + a custom HTML/JS dashboard (frontend), using **Gmail OAuth 2.0** for sending and **Groq (LLaMA)** for AI-generated content.

---

## ✨ Features

- 🔐 **Auth** — email/password signup & login with session-based auth
- 📊 **Dashboard** — real-time stats, delivery rate, recent campaigns
- 📧 **Campaigns** — upload Excel/CSV leads, personalize with merge fields (`{Name}`, `{Company}`, etc.), and launch bulk sends
- 🤖 **AI Tools** — generate cold emails and subject lines using Groq's LLaMA model
- 📁 **Templates** — save, reuse, and load templates directly into new campaigns
- 📈 **Reports** — export campaign results as CSV or Excel
- 🔗 **Gmail OAuth** — send directly from your own Gmail account, no third-party SMTP needed
- 🎨 **Themes** — 4 built-in color themes (Indigo, Sunset, Ocean, Forest)

---

## 🛠 Tech Stack

| Layer      | Technology |
|------------|------------|
| Backend    | FastAPI, Uvicorn |
| Database   | SQLite |
| Frontend   | Vanilla HTML/CSS/JS (served as static files) |
| Email      | Gmail API + OAuth 2.0 |
| AI         | Groq API (LLaMA 3.3 70B) |
| Data       | Pandas, OpenPyXL |

---

## 📦 Setup

### 1. Clone the repo
```bash
git clone https://github.com/<your-username>/mailflow-pro.git
cd mailflow-pro
```

### 2. Create a virtual environment
```bash
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # macOS/Linux
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure environment variables
```bash
copy .env.example .env        # Windows
cp .env.example .env          # macOS/Linux
```
Then fill in `.env` with your own values:

| Variable | Description |
|---|---|
| `SECRET_KEY` | Any long random string |
| `GROQ_API_KEY` | Free key from [console.groq.com](https://console.groq.com) |
| `OAUTH_REDIRECT_URI` | `http://localhost:8000/oauth_callback` for local dev |
| `GOOGLE_CLIENT_SECRETS` | Path to your downloaded `client_secrets.json` |
| `SEND_DELAY_SECONDS` | Delay between sends (default `1.5`) |
| `DB_PATH` | SQLite database path |

### 5. Add Google OAuth credentials
- Go to [Google Cloud Console](https://console.cloud.google.com) → APIs & Services → Credentials
- Create an OAuth 2.0 Client ID (Web application)
- Add `http://localhost:8000/oauth_callback` as an Authorized redirect URI
- Download the JSON and save it as `client_secrets.json` in the project root

### 6. Run the app
```bash
uvicorn main:app --reload --port 8000
```
Open **http://localhost:8000** in your browser.

---

## 📁 Project Structure

```
mailflow-pro/
├── main.py                       # FastAPI app entry point
├── requirements.txt
├── .env.example
├── static/
│   └── index.html                # Frontend dashboard
├── backend/
│   ├── auth/auth.py              # Signup, login, sessions
│   ├── campaigns/campaigns.py    # Campaign, lead & template CRUD
│   ├── ai/ai_features.py         # AI email/subject generation
│   ├── utils/excel_processor.py  # Excel/CSV parsing & personalization
│   └── reports/reports.py        # CSV/Excel export
├── database/
│   └── schema.py                 # SQLite schema & connection
└── services/
    └── email_engine.py           # Gmail OAuth + sending engine


## 📄 License

This project is for personal/educational use. Add a license of your choice if distributing publicly.
