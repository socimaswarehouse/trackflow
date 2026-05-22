# TRACKFLOW

QR Document Tracking & Submission System

## Overview

This repository contains the initial backend project foundation for TRACKFLOW using FastAPI, SQLAlchemy, MySQL, and Jinja2 templates. The structure is prepared for enterprise-scale growth while keeping the starter code clean and modular.

## Project Structure

```text
trackflow/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── database/
│   │   ├── __init__.py
│   │   ├── connection.py
│   │   └── session.py
│   ├── models/
│   │   └── __init__.py
│   ├── routes/
│   │   ├── __init__.py
│   │   └── base.py
│   ├── services/
│   │   └── __init__.py
│   ├── static/
│   ├── templates/
│   ├── uploads/
│   └── utils/
│       └── __init__.py
├── .env
├── README.md
└── requirements.txt
```

## Setup

1. Create a virtual environment:

   ```powershell
   python -m venv .venv
   ```

2. Activate the virtual environment:

   ```powershell
   .\\.venv\\Scripts\\Activate.ps1
   ```

3. Install dependencies:

   ```powershell
   pip install -r requirements.txt
   ```

4. Create the MySQL database in XAMPP:

   ```sql
   CREATE DATABASE trackflow_db;
   ```

5. Update the `.env` file if your MySQL credentials differ from the defaults.

## Run The Application

```powershell
uvicorn app.main:app --reload
```

## Test Endpoint

Open the following URL after startup:

- `http://127.0.0.1:8000/`

Expected response:

```json
{
  "message": "TRACKFLOW Backend Running"
}
```
