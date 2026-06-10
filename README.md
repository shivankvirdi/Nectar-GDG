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
%%{init: {'theme': 'redux-dark', 'themeVariables': {'primaryColor': '#1e1e2e', 'primaryTextColor': '#cdd6f4', 'primaryBorderColor': '#45475a', 'lineColor': '#f38ba8', 'secondaryColor': '#181825', 'tertiaryColor': '#313244', 'background': '#1e1e2e', 'mainBkg': '#1e1e2e', 'nodeBorder': '#45475a', 'clusterBkg': '#181825', 'titleColor': '#cba6f7', 'edgeLabelBackground': '#313244', 'fontFamily': 'ui-monospace, monospace'}}}%%

flowchart TD
    subgraph ELECTRON["① Electron Desktop Shell · macOS · Windows · Linux"]
        direction LR
        E1["Window management\n─────────────────\nFrameless, transparent\nalways-on-top\nFrosted glass via\nvibrancy / acrylic"]
        E2["IPC / fit-to-content\n─────────────────\nResizeObserver →\ndynamic height via\nsetBounds IPC channel"]
        E3["Active URL detection\n─────────────────\nAppleScript (mac)\nPowerShell (win)\nxdotool (linux)\nPolling-based"]
    end

    subgraph FRONTEND["② React + TypeScript Frontend · Vite · Electron renderer"]
        direction LR
        F1["Scan module\n─────────────────\nURL input\nAuto-detect\nCancel scan\nStatus feed"]
        F2["Results view\n─────────────────\nOverall score\nAI verdict\nIntegrity\nReputation\nKeywords"]
        F3["Recommendations\n─────────────────\nChat / prompt\nImage upload\nMarketplace filter\nFallback sort"]
        F4["Scan history\n─────────────────\nlocalStorage\nCompare view\nSide-by-side\nmetric diff"]
    end

    subgraph BACKEND["③ FastAPI Backend (Python) · Cloud Run · us-west1 · GCP Secret Manager"]
        direction LR
        B1["POST /current-url\n─────────────────\nTriggers full product\nscan. Accepts scanId\nfor cancellation"]
        B2["POST /cancel-scan\n─────────────────\nSignals async cancel\nevent via asyncio\nEvent flag"]
        B3["POST /explain-score\n─────────────────\nSends metric + analysis\nto Gemini, returns\n3–5 sentence narrative"]
        B4["POST /recommendations\n─────────────────\n1 · Gemini builds search query\n   from history + filter + image\n2 · Searches Amazon + eBay\n3 · Normalises to shared shape\n4 · Relevance filter → rank →\n   diversity cap → top 5"]
    end

    subgraph PIPELINE["④ Analysis Pipeline · vision_model.py"]
        direction TB
        P1["URL → Marketplace adapter registry\n──────────────────────────────────────\nAmazonCanopyAdapter   amazon.* / amzn.*\nEbayScraperAPIAdapter  ebay.*"]
        P2["Extract listing ID\n──────────────────────────────────────\nASIN regex  /  eBay item-ID regex"]
        P3["fetch_product_profile()\n──────────────────────────────────────\nTitle · price · rating · images · bullets\nReviews (up to ~30, normalised shape)\nAmazon: brand field\neBay:   seller dict (name, positive-%, top-rated)"]
        P4["Post-fetch processing\n──────────────────────────────────────\nKeyword inference  (URL slug + title)\nAccessory detection  (case/charger → filtered)\nSimilar product search  (build_similar_search_terms)"]
        P1 --> P2 --> P3 --> P4
    end

    subgraph NLP["⑤ NLP Analysis + Scoring · NLTK"]
        direction TB
        N1["Review Integrity · review_integrity.py\n────────────────────────────────────────────────────────\nVADER sentiment scored per sentence, not whole review\n→ correctly labels 'battery' negative in mixed reviews\nStar ↔ sentiment agreement check  (4–5★ ≥ +0.05 compound)\nVerified purchase ratio\nIntegrity score = 60% verified ratio + 40% consistency\nFlags: low_verified_ratio · star_text_mismatch · inflated_ratings"]
        N2["Keyword Extraction · nlp_utils.py\n────────────────────────────────────────────────────────\nWordNet lemmatisation  (batteries → battery)\nStop-word + domain noise-word removal\nTF-IDF:  count × log(N/df) × boost\n  · domain boost words (quality, durable …)         ×2\n  · curated bigrams (battery life, build quality …)  ×3\n  · negation pairs  (not working, never fits …)       ×4  always negative\nProper-noun filter  (brand names suppressed ≥ 4 reviews)\nSentence-level sentiment per top term"]
        N3["Brand / Seller Reputation · brand_reputation.py\n────────────────────────────────────────────────────────\nAMAZON  Fuzzy brand name → Google Places text search\n        Aggregate rating + up to 5 Google reviews\n        NLP on combined Google + Amazon reviews\n        Insights: Customer Support · Shipping · Build Quality\n        Bayesian blend:  prior=68 · conf=f(review count)\n        score = prior×(1−conf) + signal×conf\nEBAY    Seller positive-% + top-rated flag\n        Product reviews → NLP insights\n        Insights: Seller Trust · Shipping · Condition · Returns"]
        N4["Overall Score\n────────────────────────────────────────────────────────\nAmazon  40% star rating + 35% review integrity + 25% brand rep\neBay    30% star rating + 25% review integrity + 45% seller rep\n        eBay score further blended 70/30 with seller positive-%"]
    end

    subgraph GEMINI["⑥ Gemini AI Layer · ai_analysis.py\ngemini-2.5-flash → gemini-2.5-flash-lite fallback · structured JSON · 3 retries per model"]
        direction LR
        G1["Verdict generation\n─────────────────\n3 pros + 3 cons\ngrounded in reviews\nOne-sentence verdict\nBUY / COMPARE / SKIP\nthreshold: 75 / 50"]
        G2["Score explanation\n─────────────────\n3–5 sentence narrative\nfor any metric\non demand\nFull analysis context\n+ review snippets"]
        G3["Rec. query building\n─────────────────\nHistory + filter +\nimage → structured\nsearch term + scope"]
    end

    subgraph EXTERNAL["⑦ External Data Sources · All keys via GCP Secret Manager"]
        direction LR
        X1["Canopy API\n(Amazon)\n─────────────────\nGraphQL\nProducts, reviews\nsearch results\nRetry + backoff\ntimeout guards"]
        X2["ScraperAPI\n(eBay)\n─────────────────\nStructured eBay\nproduct + search\nendpoints\nField normalisation\nto shared shape"]
        X3["Google Places API\n─────────────────\nBrand name\nfuzzy match\nAggregate ratings\n+ review text\n1-hour cache"]
        X4["Gemini API\n─────────────────\ngoogle-genai\nclient\n(not Vertex SDK)\nKeys injected\nvia Secret Manager"]
    end

    ELECTRON --> FRONTEND
    FRONTEND -->|"HTTP/JSON · X-Nectar-Secret header"| BACKEND
    BACKEND --> PIPELINE
    PIPELINE --> NLP
    NLP --> GEMINI
    BACKEND --> EXTERNAL
    PIPELINE --> EXTERNAL
    GEMINI --> EXTERNAL
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
