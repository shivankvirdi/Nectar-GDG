# Nectar - GDG Solutions Challenge NA 2026



https://github.com/user-attachments/assets/f8b34e39-cb66-4d10-819a-a570b8969f3d



E-commerce lacks trustworthy product intelligence, with consumers losing billions to misleading/inflated reviews and poor purchasing decisions every year. That's why we built Nectar, a desktop overlay application that helps consumers make smarter online purchasing decisions by analyzing Amazon and eBay products in real time. The app combines review authenticity detection, AI review summaries/product verdicts, personalized recommendations, brand reputation analysis, estimated price trends, and product comparison tools to identify trustworthy products and flag potentially misleading listings. By increasing transparency in e-commerce, Nectar reduces decision fatigue and empowers users to shop with greater confidence and accuracy.

## Features
- AI-powered product analysis
- Review integrity detection
- Brand and seller reputation scoring
- Personalized product recommendations
- Product comparison tools
- Scan history and recommendation memory
- Estimated price trends and AI price-timing metrics
- Amazon and eBay support

## Technologies Used
- Frontend: React, TypeScript, Vite, CSS
- Desktop Shell: Electron
- Backend: FastAPI, Python
- AI: Google Gemini
- NLP/Scoring: NLTK --> VADER, custom review-integrity logic
- Marketplace Data: Canopy API, ScraperAPI
- Reputation Data: Google Places API
- Storage: Browser localStorage for scan history/recommendations and price intelligence
- Deployment: Docker, Google Cloud Run, Cloud Build

---

## Architecture Diagram
```mermaid
---
config:
  layout: dagre
  theme: redux-dark-color
  look: redux
  fontFamily: '''Source Code Pro Variable'', monospace'
  themeVariables:
    fontFamily: '''Source Code Pro Variable'', monospace'
---
flowchart LR
 subgraph USER_LAYER["User + Browser"]
        USER(["Amazon / eBay product page"])
  end
 subgraph ELECTRON["Electron Shell"]
        E1["Frameless glass overlay\nalways-on-top + IPC resize"]
        E2["URL detection\nAppleScript + PowerShell + xdotool"]
  end
 subgraph REACT["React + TypeScript Dashboard"]
        R1["Home\nScan + results + compare"]
        R2["Smart Recommendations\nGemini-planned search terms + filters"]
        R3["Price History\nEstimated trend chart + AI narrative"]
        R4["Scan History\nSaved products + comparison context"]
  end
 subgraph API["FastAPI on Cloud Run + Secret Manager"]
        A1["/current-url + /cancel-scan"]
        A2["/explain-score"]
        A3["/recommendations"]
        A4["/price-trend"]
  end
 subgraph PIPELINE["Marketplace + Analysis Pipeline"]
        P1["Marketplace adapter registry\nAmazon + eBay"]
        CANOPY["Canopy API\nAmazon GraphQL"]
        SCRAPER["ScraperAPI\neBay structured search"]
        P2["Fetch + normalize\nKeyword inference + dedupe"]
  end
 subgraph NLP["NLP + Scoring Engine"]
        N1["Review integrity\nVADER + flags + star/text match\nverified purchases"]
        N2["Reputation scoring\nBayesian blend\nprior = 68"]
        N3["WordNet + TF-IDF\nboost words + bigrams + negation pairs"]
        N4["Overall score weights\nAmazon 40/35/25\neBay 30/25/45"]
  end
 subgraph GEMINI["Gemini AI"]
        G1["Verdict generation\nBUY / COMPARE / SKIP"]
        G2["Score explainer\nmetric-specific rationale"]
        G3["Recommendation planner\nquery + 3-5 category-locked search terms"]
        G4["Price trend narrative\ntrajectory + likely-to-drop call"]
  end
    USER --> E1 --> R1
    E2 --> R1
    R1 -- "HTTP + X-Nectar-Secret" --> A1
    R1 --> R4
    R4 --> R2
    R2 -- "filter + prompt + history" --> A3
    R3 -- "selected scan" --> A4
    A1 --> P1
    A3 --> G3 --> P1
    A4 --> G4 --> R3
    P1 --> CANOPY --> P2
    P1 --> SCRAPER --> P2
    P2 --> N1 --> N4 --> G1 --> R1
    P2 --> N2 --> N4
    P2 --> N3 --> N4
    A2 --> G2 --> R1
    P2 -- "ranked, deduped products" --> A3 --> R2
```

# How to Use
## Clone Repository
Requirements:
- Python 3.11+
- Node.js 20+
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
## Running Nectar
### Use Hosted Backend (Requires a secret password): 
The backend is already deployed on Google Cloud!
1. Create file frontend/.env.production
2.
``` 
VITE_API_URL=https://nectar-gdg-93066440894.us-west1.run.app
NECTAR_API_SECRET=...
#contact maintainers for password access
```
3. Run electron:
```
cd frontend
npm run electron:start
```

### Use Local Backend
1. Create .env in ROOT directory, follow .env.example, and add keys ('Nectar-GDG/.env')\
https://www.canopyapi.co/ (GraphQL API)\
https://www.scraperapi.com/ \
https://aistudio.google.com/app/api-keys \
https://console.cloud.google.com/marketplace/product/google/places.googleapis.com

2. Set frontend/.env.production to:
```powershell
VITE_API_URL=http://127.0.0.1:8000
NECTAR_API_SECRET=your_shared_secret_here
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
- SCRAPERAPI_KEY
### CORS or connection issues
#### Verify VITE_API_URL matches your backend URL.
---
Project led by Shivank Virdi and co-developed with Jaycob Pakingan, Iyanna Arches, Aanya Agarwal, & Kaylana Chuan. We hope you enjoy using our application!
