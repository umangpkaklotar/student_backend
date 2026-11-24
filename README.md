# Backend — Student Attendance & Fee Management System

FastAPI + Motor (async MongoDB) REST API for managing Karate and Skating students, daily attendance, monthly fees, and role-based dashboards.

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
   ```env
   MONGODB_URL=your_mongodb_connection_string
   DATABASE_NAME=Management_System
   JWT_SECRET_KEY=your_long_random_secret_key
   JWT_ALGORITHM=HS256
   ACCESS_TOKEN_EXPIRE_MINUTES=60
   FRONTEND_URL=http://localhost:5173
   ```
4. Create the first Admin account:
   ```powershell
   python -m app.utils.create_admin
   ```
5. Run the API server:
   ```powershell
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```
6. Open Swagger docs at `http://localhost:8000/docs`.
