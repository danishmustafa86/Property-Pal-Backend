# Real Estate Intelligence Backend

Production-oriented backend for Pakistan real-estate discovery with FastAPI + MongoDB + Clerk auth + AI search parsing.

## Features
- Clerk JWT authentication with role-based authorization.
- Property CRUD with ownership checks.
- Advanced filter search with geo-radius and map viewport queries.
- Ranking score for relevance (quality, freshness, engagement, geo, price fit).
- AI query endpoint using LangGraph fallback parser.
- Cloudinary image upload endpoint.
- Saved searches, chat history, and seed data script.

## Project Structure
```text
app/
  main.py
  core/
  db/
  models/
  schemas/
  repositories/
  services/
  routes/
  auth/
  agents/
  observability/
  utils/
scripts/
  seed_data.py
```

## Run Locally
1. Create virtual environment and install dependencies:
   - `pip install -r requirements.txt`
2. Copy env file:
   - `cp .env.example .env`
3. Start API:
   - `uvicorn app.main:app --reload`

## Seed Data
- `python scripts/seed_data.py`

## Main Endpoints
- `POST /properties/`
- `GET /properties/`
- `GET /search/`
- `POST /search/intent`
- `GET /map-properties/`
- `POST /chat/query`
- `GET /chat/history`
- `POST /uploads/images`
- `GET /agents/`
- `GET /me/`
