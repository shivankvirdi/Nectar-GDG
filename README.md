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

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                          Electron Desktop Shell                             │
│                         macOS · Windows · Linux                             │
│                                                                             │
│  ┌─────────────────────┐  ┌──────────────────────┐  ┌────────────────────┐  │
│  │  Window management  │  │   IPC / fit-to-      │  │  Active URL        │  │
│  │                     │  │   content            │  │  detection         │  │
│  │  Frameless,         │  │                      │  │                    │  │
│  │  transparent,       │  │  ResizeObserver →    │  │  AppleScript (mac) │  │
│  │  always-on-top      │  │  dynamic height via  │  │  PowerShell (win)  │  │
│  │  Frosted glass via  │  │  setBounds IPC       │  │  xdotool (linux)   │  │
│  │  vibrancy/acrylic   │  │  channel             │  │  Polling-based     │  │
│  └─────────────────────┘  └──────────────────────┘  └────────────────────┘  │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        React + TypeScript Frontend                          │
│                          Vite · Electron renderer                           │
│                                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌────────────────┐   │
│  │ Scan module  │  │ Results view │  │Recommendation│  │  Scan history  │   │
│  │              │  │              │  │              │  │                │   │
│  │ URL input    │  │ Overall score│  │ Chat/prompt  │  │ localStorage   │   │
│  │ Auto-detect  │  │ AI verdict   │  │ Image upload │  │ Compare view   │   │
│  │ Cancel scan  │  │ Integrity    │  │ Marketplaces │  │ Side-by-side   │   │
│  │ Status feed  │  │ Reputation   │  │ Filter       │  │ metric diff    │   │
│  │              │  │ Keywords     │  │ Fallback sort│  │                │   │
│  └──────────────┘  └──────────────┘  └──────────────┘  └────────────────┘   │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │  HTTP/JSON
                                       │  X-Nectar-Secret header auth
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         FastAPI Backend (Python)                            │
│              Google Cloud Run · us-west1 · GCP Secret Manager               │
│                                                                             │
│  ┌─────────────────┐  ┌─────────────────┐  ┌──────────────────────────┐     │  
│  │ POST            │  │ POST            │  │ POST                     │     │
│  │ /current-url    │  │ /cancel-scan    │  │ /explain-score           │     │
│  │                 │  │                 │  │                          │     │
│  │ Triggers full   │  │ Signals async   │  │ Sends metric + analysis  │     │
│  │ product scan.   │  │ cancel event    │  │ to Gemini, returns       │     │
│  │ Accepts scanId  │  │ via asyncio     │  │ 3–5 sentence narrative   │     │
│  │ for cancellation│  │ Event flag      │  │                          │     │
│  └─────────────────┘  └─────────────────┘  └──────────────────────────┘     │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ POST /recommendations                                               │    │
│  │                                                                     │    │
│  │ 1. Gemini builds a structured search query from scan history +      │    │
│  │    filter mode + optional text prompt/reference photo               │    │
│  │ 2. Searches Amazon (Canopy) and/or eBay (ScraperAPI) in parallel    │    │
│  │ 3. Normalises all results to a shared product shape                 │    │
│  │ 4. Relevance filter → TF-IDF-style rank → diversity cap             │    │
│  │    (max 2 per brand, max 4 per marketplace) → top 5                 │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                       Analysis Pipeline (vision_model.py)                   │
│                                                                             │
│  URL ──► Marketplace adapter registry                                       │
│          ├─ AmazonCanopyAdapter   (amazon.*/amzn.*)                         │
│          └─ EbayScraperAPIAdapter (ebay.*)                                  │
│                    │                                                        │
│                    ▼                                                        │
│          Extract listing ID  (ASIN regex / eBay item-ID regex)              │
│                    │                                                        │
│                    ▼                                                        │
│          fetch_product_profile()                                            │
│          ├─ Title, price, rating, images, feature bullets                   │
│          ├─ Reviews (up to ~30, normalised to shared shape)                 │
│          ├─ Amazon: brand field                                             │
│          └─ eBay:   seller dict (name, positive-%, top-rated flag)          │
│                    │                                                        │
│                    ▼                                                        │
│          Keyword inference  (URL slug + title → product keyword)            │
│          Accessory detection (phone case/charger/cable → filtered out)      │
│          Similar product search  (build_similar_search_terms → adapter)     │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      NLP Analysis + Scoring (NLTK)                          │
│                                                                             │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │  Review Integrity  (review_integrity.py)                               │ │
│  │                                                                        │ │
│  │  • VADER sentiment scored per sentence (not whole review)              │ │
│  │    → "Love the build quality. Battery is terrible."                    │ │
│  │       correctly labels 'battery' as negative                           │ │
│  │  • Star ↔ sentiment agreement check (4–5 must be ≥ +0.05 compound)     │ │
│  │  • Verified purchase ratio                                             │ │
│  │  • Integrity score = 60% verified ratio + 40% consistency ratio        │ │
│  │  • Flags: low_verified_ratio · star_text_mismatch · inflated_ratings   │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │  Keyword Extraction  (nlp_utils.py)                                    │ │
│  │                                                                        │ │
│  │  • WordNet lemmatisation  (batteries → battery)                        │ │
│  │  • Stop-word + domain noise-word removal                               │ │
│  │  • TF-IDF scoring:  count × log(N / df) × boost                        │ │
│  │    – domain boost words (quality, durable, …)  ×2                      │ │
│  │    – curated bigrams (battery life, build quality, …)  ×3              │ │
│  │    – negation pairs  (not working, never fits, …)  ×4, always negative │ │
│  │  • Proper-noun filter (brand names suppressed when ≥ 4 reviews)        │ │
│  │  • Sentence-level sentiment per top term                               │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │  Brand / Seller Reputation  (brand_reputation.py)                      │ │
│  │                                                                        │ │
│  │  Amazon path                                                           │ │
│  │  • Fuzzy brand name → Google Places text search                        │ │
│  │  • Place details: aggregate rating + up to 5 Google reviews            │ │
│  │  • NLP on combined Google + Amazon reviews                             │ │
│  │  • Topic insights: Customer Support · Shipping/Delivery · Build Quality│ │
│  │  • Bayesian blend:                                                     │ │
│  │    prior = 68,  confidence = f(review count, aggregate count)          │ │
│  │    score = prior × (1 − conf) + signal × conf                          │ │
│  │                                                                        │ │
│  │  eBay path                                                             │ │
│  │  • Seller positive-% + top-rated flag (no Google lookup)               │ │
│  │  • Product reviews → NLP insights                                      │ │
│  │  • Topic insights: Seller Trust · Shipping & Delivery ·                │ │
│  │    Item Condition · Returns & Support                                  │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │  Overall Score                                                         │ │
│  │                                                                        │ │
│  │  Amazon:  40% star rating + 35% review integrity + 25% brand rep       │ │
│  │  eBay:    30% star rating + 25% review integrity + 45% seller rep      │ │
│  │           (eBay score further blended 70/30 with seller positive-%)    │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      Gemini AI Layer  (ai_analysis.py)                      │
│              gemini-2.5-flash  →  gemini-2.5-flash-lite  (fallback)         │
│               Structured JSON output · 3 retry attempts per model           │
│                                                                             │
│  ┌───────────────────────┐  ┌────────────────────────┐  ┌───────────────┐   │
│  │  Verdict generation   │  │  Score explanation     │  │  Rec. query   │   │
│  │                       │  │                        │  │  building     │   │
│  │  3 pros + 3 cons      │  │  3–5 sentence          │  │               │   │
│  │  grounded in reviews  │  │  narrative for any     │  │  History +    │   │
│  │                       │  │  metric, on-demand     │  │  filter +     │   │
│  │  One-sentence verdict │  │                        │  │  image →      │   │
│  │  BUY / COMPARE / SKIP │  │  Uses full analysis    │  │  search term  │   │
│  │  threshold: 75 / 50   │  │  context + snippets    │  │  + scope      │   │
│  └───────────────────────┘  └────────────────────────┘  └───────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                           External Data Sources                             │
│                                                                             │
│  ┌─────────────────┐  ┌─────────────────┐  ┌──────────────┐  ┌──────────┐   │
│  │  Canopy API     │  │  ScraperAPI     │  │ Google Places│  │  Gemini  │   │
│  │  (Amazon)       │  │  (eBay)         │  │ API          │  │  API     │   │
│  │                 │  │                 │  │              │  │          │   │
│  │  GraphQL        │  │  Structured     │  │  Brand name  │  │  Google  │   │
│  │  Products,      │  │  eBay product   │  │  fuzzy match │  │  Cloud   │   │
│  │  reviews,       │  │  + search       │  │  Aggregate   │  │  Vertex  │   │
│  │  search.        │  │  endpoints.     │  │  ratings +   │  │  AI SDK  │   │
│  │  Retry with     │  │ Field           │  │  review text │  │          │   │
│  │  backoff,       │  │ normalisation   │  │              │  │ Keys via │   │
│  │  timeout guards │  │ to shared shape │  │  1-hr cache  │  │ Secret   │   │  
│  │                 │  │                 │  │              │  │ Manager  │   │    
│  └─────────────────┘  └─────────────────┘  └──────────────┘  └──────────┘   │
│                                                                             │
│  All keys injected at runtime via GCP Secret Manager (never in source)      │
└─────────────────────────────────────────────────────────────────────────────┘
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
