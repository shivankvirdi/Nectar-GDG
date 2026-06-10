# Nectar

https://github.com/user-attachments/assets/503b7d96-bcd8-418d-aa47-0589f6e007b4


E-commerce lacks trustworthy product intelligence, with consumers losing billions to misleading/inflated reviews and poor purchasing decisions every year. That's why we built Nectar, a product-analyzer Electron desktop app that builds this needed trust layer by comparing products and providing in-depth insights on price, review integrity, quality, brand reputation, and similar alternatives. Nectar recommends the best option to help reduce shopper stress and support more informed purchasing decisions.

## Features
- AI-powered product analysis
- Review integrity detection
- Brand and seller reputation scoring
- Personalized product recommendations
- Product comparison tools
- Scan history and recommendation memory
- Amazon and eBay support

## Technologies Used
- Frontend: React, TypeScript, Vite, CSS
- Desktop Shell: Electron
- Backend: FastAPI, Python
- AI: Google Gemini
- NLP/Scoring: NLTK --> VADER, custom review-integrity logic
- Marketplace Data: Canopy API, ScraperAPI
- Reputation Data: Google Places API
- Storage: Browser localStorage for scan history and recommendation memory
- Deployment: Docker, Google Cloud Run, Cloud Build

---

## Architecture Diagram
```mermaid
%%{init: {'theme': 'redux-dark', 'themeVariables': {'fontSize': '15px', 'fontFamily': 'ui-monospace, monospace'}}}%%

flowchart TD

    USER(["🛒 User browses Amazon or eBay"])

    subgraph SHELL["Electron Desktop Overlay"]
        direction LR
        DET["Active URL detection\nAppleScript · PowerShell · xdotool"]
        WIN["Frameless always-on-top window\nFrosted glass · IPC fit-to-content"]
    end

    subgraph UI["React + TypeScript Frontend"]
        direction LR
        SCAN["Scan module\nPaste or auto-detect URL\nCancel mid-scan"]
        RESULTS["Results view\nScore · verdict · keywords\nreputation insights"]
        REC["Recommendations\nPrompt · image upload\nfilter · marketplace"]
        HIST["Scan history\nCompare two products\nside-by-side metrics"]
    end

    subgraph API["FastAPI Backend — Cloud Run · GCP Secret Manager"]
        direction LR
        EP1["/current-url\nRun full scan\naccepts scanId"]
        EP2["/cancel-scan\nasyncio Event\nflag abort"]
        EP3["/explain-score\nGemini narrative\nper metric"]
        EP4["/recommendations\nGemini query builder\nrank · dedupe · top 5"]
    end

    subgraph PIPE["Analysis Pipeline — vision_model.py"]
        direction TB
        ADAPT["Marketplace adapter registry\nAmazonCanopyAdapter  amazon.*\nEbayScraperAPIAdapter  ebay.*"]
        FETCH["fetch_product_profile\nTitle · price · rating · images\nReviews normalised to shared shape\nAmazon: brand  ·  eBay: seller dict"]
        POST["Keyword + accessory inference\nURL slug + title → product keyword\nFilter out cases · cables · chargers\nbuild_similar_search_terms → adapter"]
        ADAPT --> FETCH --> POST
    end

    subgraph NLP["NLP Scoring Engine — NLTK"]
        direction LR

        subgraph INTEG["Review Integrity  review_integrity.py"]
            RI["VADER scored per sentence not whole review\n'Battery is terrible' scores negative\neven inside a 4-star review\nIntegrity = 60% verified ratio + 40% star-sentiment agreement\nFlags: low_verified · star_text_mismatch · inflated_ratings"]
        end

        subgraph KWDS["Keyword Extraction  nlp_utils.py"]
            KW["WordNet lemmatisation  batteries → battery\nTF-IDF: count × log(N/df) × domain boost\n  boost words  quality · durable          ×2\n  curated bigrams  battery life           ×3\n  negation pairs  not working             ×4\nSentence-level VADER sentiment per term"]
        end

        subgraph REPUT["Reputation Scoring  brand_reputation.py"]
            BR["Amazon: fuzzy brand → Google Places\n  aggregate rating + NLP on reviews\n  Bayesian blend  score = prior×(1−c) + signal×c  prior = 68\n  Insights: Support · Shipping · Build Quality\neBay: seller positive-% + top-rated flag\n  Insights: Trust · Shipping · Condition · Returns"]
        end

        subgraph SCORE["Overall Score"]
            SC["Amazon  40% star + 35% integrity + 25% brand\neBay    30% star + 25% integrity + 45% seller\n        blended 70/30 with seller positive-%"]
        end
    end

    subgraph AILAY["Gemini AI Layer — ai_analysis.py\ngemini-2.5-flash → gemini-2.5-flash-lite fallback · structured JSON output · 3 retries"]
        direction LR
        VER["Verdict\n3 pros + 3 cons from reviews\nBUY / COMPARE / SKIP\nthreshold 75 / 50"]
        EXP["Score explainer\n3–5 sentence narrative\nper metric on demand"]
        QRY["Rec query builder\nHistory + filter + image\n→ search term + scope"]
    end

    subgraph EXT["External Data Sources"]
        direction LR
        CANOPY["Canopy API\nAmazon GraphQL\nproducts · reviews\nsearch · retry+backoff"]
        SCRAPER["ScraperAPI\neBay structured\nproduct + search\nnormalised shape"]
        PLACES["Google Places API\nBrand fuzzy match\naggregate rating\n+ review text · 1hr cache"]
        GAPI["Gemini API\ngoogle-genai client\nkeys via\nSecret Manager"]
    end

    USER --> SHELL
    SHELL -->|"detected URL"| UI
    UI -->|"HTTP/JSON · X-Nectar-Secret"| API
    API --> PIPE
    PIPE --> NLP
    NLP --> AILAY
    AILAY -->|"verdict + pros/cons + rec"| UI
    PIPE -->|"product fetch"| CANOPY
    PIPE -->|"product fetch"| SCRAPER
    REPUT -->|"brand lookup"| PLACES
    AILAY -->|"LLM calls"| GAPI
    EP4 -->|"rec searches"| CANOPY
    EP4 -->|"rec searches"| SCRAPER
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
2. Set VITE_API_URL=https://nectar-gdg-93066440894.us-west1.run.app and VITE_NECTAR_SECRET to the password\
   (contact maintainers for access)
3. Run electron:
```
cd frontend
npm run electron:start
```

### Use Local Backend
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
