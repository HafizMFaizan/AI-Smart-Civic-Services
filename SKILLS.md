# HACKATHON SKILLS & RULES: AI SMART CIVIC SERVICES

## 1. General Rules

- Write complete, production-ready, runnable code without placeholders or TODOs.
- Keep explanations ultra-brief to save tokens.
- Follow Clean OOP Architecture using proper Classes and Type Hints.

## 2. Tech Stack Requirements

- Backend: FastAPI (Python) running on Uvicorn.
- Database: SQLite with a dedicated DatabaseManager class.
- Frontend: Single Page Application (HTML5, Tailwind CSS via CDN, Vanilla JS fetch API).
- AI Engine: AIAnalyzer class for:
  1. Category Classification (Road, Water, Waste, Electricity, Drainage, Safety, Other)
  2. Priority Prediction (Low, Medium, High, Critical)
  3. Actionable Summary Generation for Service Teams

## 3. Data Model Schema

The Complaint object must contain:

- complaint_id (str/UUID)
- description (str)
- category (str)
- priority (str)
- location (str)
- date (datetime)
- status (Open / In Progress / Resolved)
- assigned_department (str)
- ai_summary (str)

## 4. Analytics & Statistics

Provide endpoints for statistical distribution:

- Total complaint count & Category frequencies
- Priority distribution (Percentages / Value counts)
- Average resolution metrics
