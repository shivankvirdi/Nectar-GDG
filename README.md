

https://github.com/user-attachments/assets/503b7d96-bcd8-418d-aa47-0589f6e007b4


E-commerce lacks trustworthy product intelligence, with consumers losing billions to misleading/inflated reviews and poor purchasing decisions every year. That's why we built Nectar, a product-analyzer Electron desktop app that builds this needed trust layer by comparing products and providing in-depth insights on price, review integrity, quality, brand reputation, and similar alternatives. Nectar recommends the best option to help reduce shopper stress and support more informed purchasing decisions.

# Nectar Project Overview
The active application flow is centered around:

- `frontend/src/App.tsx` for the main React UI
- `frontend/electron-main.js` for the desktop Electron shell
- `frontend/preload.js` for secure renderer-to-Electron IPC
- `backend/main.py` for the FastAPI surface
- `backend/vision_model.py` for the main product analysis pipeline
- `backend/ai_analysis.py` for Gemini-powered verdicts, explanations, and recommendations

---

## Architecture Diagram

```text
User
  |
  v
Electron Desktop App
  - Window controls
  - Active browser URL detection
  - Opens external product links
  |
  v
React + Vite Frontend
  - Scan module
  - Product results
  - Smart recommendations
  - Scan history
  - Compare view
  |
  | HTTP requests
  v
FastAPI Backend
  - /current-url
  - /cancel-scan
  - /explain-score
  - /recommendations
  |
  v
Analysis Pipeline
  - Marketplace adapter selection
  - Product data fetching
  - Review integrity scoring
  - Brand/seller reputation scoring
  - Overall trust score generation
  |
  +--> Canopy API: Amazon product data
  +--> ScraperAPI: eBay product data
  +--> Google Places API: brand reputation context
  +--> Gemini API: verdicts, explanations, smart recommendations
```
## Clone Repository:
```powershell
git clone https://github.com/shivankvirdi/Nectar-GDG.git
cd Nectar-GDG
```
## Backend Setup
```powershell
cd backend
python -m venv .venv
```
### Activate virtual environment
```powershell
.venv\Scripts\activate # Windows
source .venv/bin/activate # Mac/Linux
```
### Install dependencies
```powershell
pip install -r requirements.txt
```
## Frontend Setup
Install Node.js (http://nodejs.org/en/download) and add to PATH
```powershell
cd frontend
npm install
```
### Build Frontend Assets
```powershell
npm run build
```
## Deploying Backend Server
### Use hosted backend (Requires a secret password): 
The backend is already deployed on Google Cloud!
1. Create file frontend/.env.production
2. Set VITE_API_URL=https://nectar-gdg-93066440894.us-west1.run.app and VITE_NECTAR_SECRET to the password\
   (contact maintainers for access)
4. Run electron:
```
cd frontend
npm run electron:start
```

### Deploy locally
1. Create .env in ROOT directory and add keys ('Nectar-GDG/.env')\
https://www.canopyapi.co/ (GraphQL API)\
https://aistudio.google.com/app/api-keys  
https://console.cloud.google.com/marketplace/product/google/places.googleapis.com
```
CANOPY_API_KEY=your_api_key_here
GEMINI_API_KEY=your_api_key_here
GOOGLE_PLACES_API_KEY=your_api_key_here
```
2. Set frontend/.env.production to:
```powershell
VITE_API_URL=http://127.0.0.1:8000
```
3. Rebuild frontend:
```powershell
cd frontend
npm run build
```
4. Run backend and electron:
```powershell
#Terminal 1 in frontend directory
npm run electron:start
#Terminal 2 in ROOT
uvicorn backend.main:app --reload
```
## Troubleshooting
### Electron won't start
Delete node_modules and reinstall:
```
npm install
```
### Backend fails to start
Verify:
- CANOPY_API_KEY
- GEMINI_API_KEY
- GOOGLE_PLACES_API_KEY
### CORS or connection issues
#### Verify VITE_API_URL matches your backend URL.
---
Project led by Shivank Virdi and co-developed with Jaycob Pakingan, Iyanna Arches, Aanya Agarwal, & Kaylana Chuan. We hope you enjoy using our application!
