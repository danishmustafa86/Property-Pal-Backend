---
title: Real Estate Intelligence Backend
emoji: 🏠
colorFrom: blue
colorTo: green
sdk: docker
pinned: false
app_port: 7860
---

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

## Deploy to Hugging Face Spaces (Docker)

### 1. Create a new Space
Go to [huggingface.co/new-space](https://huggingface.co/new-space), choose **Docker** as the SDK, and push the contents of this `backend/` folder as the root of that space repository.

### 2. Set Space Secrets
In your space → **Settings → Variables and Secrets**, add the following as **Secrets** (never put real values in the Dockerfile):

| Secret | Description |
|--------|-------------|
| `MONGODB_URI` | MongoDB Atlas connection string |
| `MONGODB_DB_NAME` | Database name (default: `real_estate`) |
| `CLERK_ISSUER` | Clerk frontend API URL |
| `CLERK_JWKS_URL` | Clerk JWKS endpoint URL |
| `CLERK_SECRET_KEY` | Clerk backend secret key |
| `CLERK_AUDIENCE` | Clerk JWT audience (if using custom template) |
| `CLOUDINARY_CLOUD_NAME` | Cloudinary cloud name |
| `CLOUDINARY_API_KEY` | Cloudinary API key |
| `CLOUDINARY_API_SECRET` | Cloudinary API secret |
| `OPENAI_API_KEY` | AIML API / OpenAI key |
| `LLM_BASE_URL` | LLM provider base URL (e.g. `https://api.aimlapi.com/v1`) |
| `LLM_MODEL` | Model name (e.g. `meta-llama/Meta-Llama-3-70B-Instruct`) |
| `TAVILY_API_KEY` | Tavily web research API key |
| `CORS_ORIGINS` | Comma-separated list of allowed frontend origins (e.g. `https://your-app.vercel.app`) |

### 3. After deployment
Your API will be live at `https://<your-username>-<space-name>.hf.space`.
Add that URL (or your frontend URL) to `CORS_ORIGINS` in Space Secrets if needed.
