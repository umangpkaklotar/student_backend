# Backend — Student Attendance & Fee Management System

FastAPI + Motor (async MongoDB) REST API supporting student self-registration with Gmail SMTP OTP verification, JWT authentication, password reset with OTP, read-only student attendance/fee portals, and admin-protected backend APIs.

## Setup

1. Create and activate a virtual environment:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\activate
   ```
2. Install dependencies:
   ```powershell
   pip install -r requirements.txt
   ```
3. Configure `.env` from `.env.example`:
   - Set `MONGODB_URL`, `DATABASE_NAME`, and `JWT_SECRET_KEY`.
   - Set `SMTP_HOST=smtp.gmail.com`, `SMTP_PORT=587`, `SMTP_USERNAME`, `SMTP_PASSWORD` (use a **Gmail App Password**, never your normal Gmail account password), and `SMTP_FROM_EMAIL`.
4. Run the API server:
   ```powershell
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```
5. Swagger UI: `http://localhost:8000/docs`.
