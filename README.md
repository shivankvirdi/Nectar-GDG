# Nectar - GDG Solutions Challenge NA 2026



https://github.com/user-attachments/assets/f8b34e39-cb66-4d10-819a-a570b8969f3d



E-commerce lacks trustworthy product intelligence, with consumers losing billions to misleading/inflated reviews and poor purchasing decisions every year. That's why we built Nectar, a desktop overlay application that helps consumers make smarter online purchasing decisions by analyzing Amazon and eBay products in real time. The app combines review authenticity detection, AI review summaries, personalized recommendations/discovery, brand reputation analysis, estimated price trends, and product comparison tools to identify trustworthy products and flag potentially misleading listings. By increasing transparency in e-commerce, Nectar reduces decision fatigue and empowers users to shop with greater confidence and accuracy.

## Features
- AI-powered product analysis
- Review integrity detection
- Brand and seller reputation scoring
- Personalized product recommendations
- Product comparison tools
- Scan history and recommendation memory
- AI Product Discovery chatbot
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
- Storage: Browser localStorage for scan history/recommendation, chatbot conversation history, and price intelligence
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
 subgraph ELECTRON["Electron Shell (Desktop App)"]
        E1["Frameless glass overlay window\nalways-on-top · auto-resize via IPC"]
        E2["Active browser tab detector\nAppleScript (Mac) · PowerShell (Win) · xdotool (Linux)"]
  end

 subgraph REACT["React + TypeScript UI"]
        R1["Scan / Results / Compare views"]
        R2["Smart Recommendations panel\n+ Scan History"]
        R3["AI Discovery Chat\nimage upload · saved conversations"]
        R4["Estimated Price Intelligence panel\nproduct selector · chart · stats"]
  end

 subgraph API["FastAPI Backend (Cloud Run)"]
        A1["POST /current-url\nPOST /cancel-scan"]
        A2["POST /recommendations\nPOST /explain-score"]
        A3["POST /shopping-chat"]
        A4["POST /price-trend"]
  end

 subgraph PIPELINE["Analysis Pipeline"]
        P1["Marketplace adapter registry\npicks Amazon or eBay adapter from URL"]
        P2["Recommendation ranker\nrelevance filter · dedupe · brand/marketplace diversity"]
        P3["Price intelligence builder\nbuilds estimated 30-day series · low/high/avg/movement"]
  end

 subgraph NLP["NLP Scoring Engine"]
        N1["Review integrity analyzer\nVADER sentiment · verified-purchase ratio · mismatch flags"]
        N2["Reputation scorer\nBayesian blend, prior score = 68"]
        N3["Keyword extractor\nlemmatization · TF-IDF · curated bigrams · negation pairs"]
        N4["Overall trust score\nAmazon: 40% rating / 35% integrity / 25% reputation\neBay: 30% rating / 25% integrity / 45% seller rep"]
  end

 subgraph GEMINI["Gemini AI Reasoning"]
        G1["Verdict generator\noutputs BUY / COMPARE / SKIP + pros/cons"]
        G2["Query builder & score explainer\nturns scan history + filters into a search query"]
        G3["Discovery chat reasoner\nanswers conversationally first, offers a search only if useful"]
        G4["Price trend narrator\nwrites a likely-to-drop call with confidence"]
  end

 subgraph EXTERNAL["External Data Sources"]
        CANOPY["Canopy API\nAmazon GraphQL product + review data"]
        SCRAPER["ScraperAPI\neBay structured product + search data"]
        PLACES["Google Places API\nbrand lookup · public review signals"]
        GAPI["Gemini API\ngemini-2.5-flash and flash-lite"]
  end

    USER(["Amazon or eBay"]) --> E2
    E2 --> E1
    E1 --> R1

    R1 -- "1. user submits product URL" --> A1
    A1 -- "2. fetch listing data" --> P1
    P1 -- "Amazon listing" --> CANOPY
    P1 -- "eBay listing" --> SCRAPER
    P1 -- "3. normalized reviews" --> N1
    P1 -- "3. normalized reviews" --> N2
    P1 -- "3. normalized reviews" --> N3
    N1 -- "integrity score" --> N4
    N2 -- "reputation score" --> N4
    N3 -- "keyword signals" --> N4
    N4 -- "4. scores + review snippets" --> G1
    G1 -- "Gemini API call" --> GAPI
    G1 -- "5. verdict + trust score" --> R1

    R2 -- "1. filters, prompt, marketplace" --> A2
    A2 -- "2. build search query" --> G2
    G2 -- "Gemini API call" --> GAPI
    G2 -- "3. search query" --> P2
    P2 -- "4. searches via" --> P1
    P2 -- "5. ranked, deduped picks" --> R2

    R3 -- "1. message + optional image" --> A3
    A3 -- "2. reason about intent" --> G3
    G3 -- "Gemini API call" --> GAPI
    G3 -- "3. chat reply + optional search offer" --> R3
    R3 -. "user accepts the offered search" .-> R2

    R4 -- "1. selected past scan" --> A4
    A4 -- "2. build price series" --> P3
    P3 -- "3. series + stats" --> G4
    G4 -- "Gemini API call" --> GAPI
    G4 -- "4. trend narrative" --> R4

    N2 -- "brand/seller lookup" --> PLACES
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
2. Set VITE_API_URL=https://nectar-gdg-93066440894.us-west1.run.app and NECTAR_API_SECRET to the password\
   (contact maintainers for access)
3. Run electron:
```
cd frontend
npm run electron:start
```

### Use Local Backend
1. Create .env in ROOT directory and add keys ('Nectar-GDG/.env')\
https://www.canopyapi.co/ (GraphQL API)\
https://www.scraperapi.com/ \
https://aistudio.google.com/app/api-keys \
https://console.cloud.google.com/marketplace/product/google/places.googleapis.com
```
CANOPY_API_KEY=your_api_key_here
GEMINI_API_KEY=your_api_key_here
GOOGLE_PLACES_API_KEY=your_api_key_here
SCRAPERAPI_KEY=your_api_key_here
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
- SCRAPERAPI_KEY
### CORS or connection issues
#### Verify VITE_API_URL matches your backend URL.
---
Project led by Shivank Virdi and co-developed with Jaycob Pakingan, Iyanna Arches, Aanya Agarwal, & Kaylana Chuan. We hope you enjoy using our application!
