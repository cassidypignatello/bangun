# FastAPI Backend - Quick Start Guide

## 5-Minute Setup

### 1. Environment Setup (2 min)

```bash
cd backend

# Copy environment template
cp .env.example .env

# Generate encryption key
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# Copy output to FIELD_ENCRYPTION_KEY in .env

# Edit .env and fill in your credentials
# Required: SUPABASE_URL, SUPABASE_SERVICE_KEY, OPENAI_API_KEY
```

### 2. Install Dependencies (2 min)

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install requirements
pip install -r requirements.txt
```

### 3. Run Server (1 min)

```bash
uvicorn app.main:app --reload --port 8000
```

Visit http://localhost:8000/docs for interactive API documentation.

---

## Essential Environment Variables

**Minimum to run:**
```bash
ENV=development
DEBUG=true
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_SERVICE_KEY=eyJ...
OPENAI_API_KEY=sk-...
APIFY_TOKEN=apify_api_...
MIDTRANS_SERVER_KEY=SB-Mid-server-...
MIDTRANS_CLIENT_KEY=SB-Mid-client-...
FIELD_ENCRYPTION_KEY=your-generated-key
```

---

## Test the API

### Health Check
```bash
curl http://localhost:8000/health
```

### Create Estimate (requires database setup)
```bash
curl -X POST http://localhost:8000/estimate \
  -H "Content-Type: application/json" \
  -d '{
    "project_type": "bathroom_renovation",
    "description": "Modern bathroom, 10m2, ceramic tiles",
    "location": "Canggu"
  }'
```

---

## Database Setup (Required for Full Functionality)

See `IMPLEMENTATION_SUMMARY.md` for complete SQL schema.

Quick Supabase setup:
1. Go to https://supabase.com
2. Create new project
3. Run SQL from IMPLEMENTATION_SUMMARY.md section 1
4. Copy URL and service key to .env

---

## Common Issues

**Import errors?**
→ Make sure virtual environment is activated: `source venv/bin/activate`

**Database errors?**
→ Check SUPABASE_URL and SUPABASE_SERVICE_KEY in .env
→ Verify tables are created in Supabase

**OpenAI errors?**
→ Verify OPENAI_API_KEY is valid
→ Check API quota and billing

**Apify errors?**
→ Update actor ID in app/integrations/apify.py line 45
→ Verify APIFY_TOKEN is valid

---

## File Locations

- **Main app**: `app/main.py`
- **Config**: `app/config.py`
- **Routes**: `app/routes/`
- **Environment**: `.env`

---

## Key Commands

```bash
# Activate virtual environment
source venv/bin/activate

# Run server
uvicorn app.main:app --reload --port 8000

# Run tests
pytest tests/ -v

# Check syntax
python3 -m py_compile app/main.py

# Deactivate virtual environment
deactivate
```

---

## Next Steps After Setup

1. Set up database tables (see IMPLEMENTATION_SUMMARY.md)
2. Update Apify actor ID
3. Write unit tests
4. Test all endpoints
5. Deploy to production

---

## Documentation

- **Full Setup**: README.md
- **Implementation Details**: IMPLEMENTATION_SUMMARY.md
- **API Docs**: http://localhost:8000/docs (after running)
- **Environment Template**: .env.example

---

Ready to build! 🚀
