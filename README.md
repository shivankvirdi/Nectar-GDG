

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
+================================================================================+
|                                NECTAR DESKTOP                                  |
|                                                                                |
|  Desktop product scanner + trust analyzer + smart recommendation assistant      |
+================================================================================+

        +-------------------------------+
        | Electron Main Process         |
        | frontend/electron-main.js     |
        |-------------------------------|
        | Creates app window            |
        | Controls size/opacity       |
        | Handles minimize / close      |
        | Opens external product links  |
        | Detects active browser URL    |
        +---------------+---------------+
                        |
                        | IPC
                        v
        +-------------------------------+
        | Preload Bridge                |
        | frontend/preload.js           |
        |-------------------------------|
        | Exposes window.electronAPI    |
        | - getActiveTabUrl()           |
        | - resizeWindow()              |
        | - moveWindow()                |
        | - setOpacity()                |
        | - openExternal()              |
        +---------------+---------------+
                        |
                        | Safe browser APIs
                        v
+================================================================================+
|                              REACT FRONTEND                                    |
|                              frontend/src/App.tsx                              |
+================================================================================+
|                                                                                |
|  Main visible modules:                                                         |
|                                                                                |
|  +----------------------+       +----------------------------+                  |
|  | Scan Module          |       | Smart Recommendations      |                  |
|  |----------------------|       |----------------------------|                  |
|  | Manual URL input     |       | AI product suggestions     |                  |
|  | Active URL detection |       | Filter: overall/price/etc. |                  |
|  | Start/cancel scan    |       | Prompt refinement          |                  |
|  +----------+-----------+       | Image-based refinement     |                  |
|             |                   +-------------+--------------+                  |
|             |                                 |                                 |
|             v                                 v                                 |
|  +----------------------+       +----------------------------+                  |
|  | Results View         |       | Scan History               |                  |
|  |----------------------|       |----------------------------|                  |
|  | Overall score        |       | Local saved scans          |                  |
|  | Review integrity     |       | Load previous scan         |                  |
|  | Brand/seller score   |       | Delete / clear history     |                  |
|  | Gemini verdict       |       | Select scans to compare    |                  |
|  +----------+-----------+       +-------------+--------------+                  |
|             |                                 |                                 |
|             v                                 v                                 |
|  +------------------------------------------------------------+                 |
|  | Compare View                                                |                 |
|  |------------------------------------------------------------|                 |
|  | Compares two saved scans across score, trust, review,       |                 |
|  | reputation, product details, and AI recommendation fields.  |                 |
|  +------------------------------------------------------------+                 |
|                                                                                |
|  Local browser storage:                                                        |
|  - nectar_current_scan                                                         |
|  - nectar_previous_scan                                                        |
|  - nectar_scan_history                                                         |
|                                                                                |
+====================================+===========================================+
                                     |
                                     | HTTP JSON
                                     | API base:
                                     | - VITE_API_URL
                                     | - fallback http://127.0.0.1:8000
                                     |
                                     | Optional auth:
                                     | - X-Nectar-Secret
                                     v
+================================================================================+
|                              FASTAPI BACKEND                                   |
|                              backend/main.py                                   |
+================================================================================+
|                                                                                |
|  API routes:                                                                   |
|                                                                                |
|  GET  /health                                                                  |
|    -> Confirms backend is alive.                                                |
|                                                                                |
|  POST /current-url                                                             |
|    -> Starts product analysis for a marketplace URL.                            |
|                                                                                |
|  POST /cancel-scan                                                             |
|    -> Cancels an active scan using scanId.                                      |
|                                                                                |
|  POST /explain-score                                                           |
|    -> Uses AI to explain one score category from an existing analysis.          |
|                                                                                |
|  POST /recommendations                                                         |
|    -> Returns 5 filtered, available, priced product recommendations.            |
|                                                                                |
+====================================+===========================================+
                                     |
                                     | Product analysis request
                                     v
+================================================================================+
|                            ANALYSIS PIPELINE                                   |
|                            backend/vision_model.py                             |
+================================================================================+
|                                                                                |
|  1. Choose marketplace adapter                                                  |
|     - backend/marketplaces/registry.py                                          |
|                                                                                |
|  2. Extract marketplace listing ID                                              |
|     - Amazon ASIN                                                               |
|     - eBay item ID                                                              |
|                                                                                |
|  3. Fetch product profile                                                       |
|     - title, brand/seller, price, image, rating, reviews, related products      |
|                                                                                |
|  4. Analyze review integrity                                                    |
|     - backend/review_integrity.py                                               |
|     - backend/nlp_utils.py                                                      |
|                                                                                |
|  5. Score brand or seller reputation                                            |
|     - backend/brand_reputation.py                                               |
|                                                                                |
|  6. Build related/similar product pool                                          |
|     - adapter-provided related products                                         |
|     - marketplace search fallback                                               |
|                                                                                |
|  7. Compute overall product score                                               |
|     - Amazon: rating + review integrity + brand reputation                      |
|     - eBay: rating + review integrity + seller reputation                       |
|                                                                                |
|  8. Generate Gemini verdict                                                     |
|     - backend/ai_analysis.py                                                    |
|                                                                                |
|  9. Return normalized Analysis object to frontend                               |
|                                                                                |
+====================================+===========================================+
                                     |
                +--------------------+--------------------+
                |                    |                    |
                v                    v                    v
+--------------------------+ +--------------------+ +-----------------------------+
| Marketplace Adapters     | | Review NLP         | | Reputation Scoring          |
| backend/marketplaces     | |--------------------| |-----------------------------|
|--------------------------| | review_integrity.py| | brand_reputation.py         |
| base.py                  | | nlp_utils.py       | |                             |
| registry.py              | |                    | | Uses local review signals   |
| amazon_canopy.py         | | Checks verified    | | Uses rating/review volume   |
| ebay_scraper.py          | | review ratio,      | | Uses Google Places when     |
|                          | | sentiment mismatch,| | GOOGLE_PLACES_API_KEY exists|
| Amazon -> Canopy API     | | inflated ratings,  | |                             |
| eBay   -> ScraperAPI     | | keyword patterns   | | Caches reputation results   |
+-------------+------------+ +--------------------+ +--------------+--------------+
              |                                             |
              v                                             v
+--------------------------+                    +-----------------------------+
| External Product APIs    |                    | External Reputation API     |
|--------------------------|                    |-----------------------------|
| CANOPY_API_KEY           |                    | GOOGLE_PLACES_API_KEY       |
| - Amazon product data    |                    | - brand/place reputation    |
| - Amazon search results  |                    | - public rating signals     |
|                          |                    +-----------------------------+
| SCRAPERAPI_KEY           |
| - eBay product data      |
| - eBay search results    |
+--------------------------+

                                     |
                                     v
+================================================================================+
|                             GEMINI AI LAYER                                    |
|                             backend/ai_analysis.py                             |
+================================================================================+
|                                                                                |
|  Uses GEMINI_API_KEY.                                                           |
|                                                                                |
|  Responsibilities:                                                              |
|                                                                                |
|  1. Product verdicts                                                            |
|     - pros                                                                      |
|     - cons                                                                      |
|     - final verdict                                                             |
|     - BUY / COMPARE / SKIP recommendation                                       |
|                                                                                |
|  2. Score explanations                                                          |
|     - explains overall score, review integrity, brand reputation, etc.          |
|                                                                                |
|  3. Smart recommendation query building                                         |
|     - reads scan history                                                        |
|     - uses latest scanned product as strongest context                          |
|     - supports user text refinement                                             |
|     - supports uploaded image refinement                                        |
|     - restricts prompts to shopping/product recommendation intent               |
|                                                                                |
|  4. Prompt restriction                                                          |
|     - unrelated prompts are rejected                                            |
|     - frontend displays: "Sorry, I cannot help you with that"                   |
|                                                                                |
+================================================================================+

                                     |
                                     v
+================================================================================+
|                       SMART RECOMMENDATION FLOW                                |
+================================================================================+
|                                                                                |
|  Frontend smart rec module                                                      |
|  frontend/src/App.tsx                                                           |
|                                                                                |
|        |                                                                       |
|        | POST /recommendations                                                  |
|        v                                                                       |
|  backend/main.py                                                                |
|                                                                                |
|        |                                                                       |
|        | build_recommendation_query()                                           |
|        v                                                                       |
|  backend/ai_analysis.py                                                         |
|                                                                                |
|        |                                                                       |
|        | Returns a product-focused search query                                 |
|        v                                                                       |
|  Marketplace adapters                                                           |
|                                                                                |
|        |                                                                       |
|        | Search Amazon/eBay                                                     |
|        v                                                                       |
|  Backend product normalization                                                  |
|                                                                                |
|        |                                                                       |
|        | Removes products with:                                                  |
|        | - no usable title                                                       |
|        | - no positive numeric price                                             |
|        | - unavailable / out-of-stock / sold-out states                          |
|        v                                                                       |
|  Backend ranking                                                                |
|                                                                                |
|        |                                                                       |
|        | overall     -> balanced relevance, rating, reviews, price               |
|        | price       -> cheapest relevant available products                     |
|        | durability  -> durable/sturdy/protective signals + rating/reviews       |
|        | quality     -> premium/top-rated/high-quality signals + rating/reviews  |
|        v                                                                       |
|  Frontend displays top 5 products                                               |
|                                                                                |
+================================================================================+
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
