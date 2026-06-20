# Nectar - GDG Solutions Challenge NA 2026

<div style="overflow-x: auto; white-space: nowrap; padding-bottom: 10px;">
  <table>
    <tr>
      <td style="vertical-align: top;">
        <video src="https://github.com/user-attachments/assets/1417cf5b-78a4-4967-b080-403c6544bf80" height="250" controls></video>
      </td>
      <td style="vertical-align: top; padding-left: 10px;">
        <img src="https://github.com/user-attachments/assets/5b95d33c-e470-4400-8a1d-8a8c21465292" height="250" alt="nectar price history">
      </td>
    </tr>
  </table>
</div>

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
 subgraph ELECTRON["Electron Shell"]
        E1["Frameless glass overlay\nalways-on-top · IPC resize"]
        E2["URL detection\nAppleScript · PS · xdotool"]
  end
 subgraph REACT["React + TypeScript"]
        R1["Scan · Results · Compare"]
        R2["Recommendations · History"]
        R3["Price History\nTrend chart · AI narrative"]
  end
 subgraph API["FastAPI · Cloud Run · Secret Manager"]
        A1["/current-url · /cancel-scan"]
        A2["/explain-score\n/recommendations"]
        A3["/price-trend"]
  end
 subgraph PIPELINE["Analysis Pipeline"]
        P1["Marketplace adapter registry\nAmazon · eBay"]
        P2["Fetch · normalise\nKeyword inference"]
  end
 subgraph NLP["NLP Engine"]
        N1["Review integrity\nVADER scoring · flags\n· star ↔ text match\n· verified purchases"]
        N2["Reputation scoring\nBayesian blend · prior = 68, prior × (1 − conf) + signal × conf"]
        N3["WordNet lemmatization · TF-IDF scoring + boost words · bigrams · negation pairs"]
        N4["Overall score %'s\nRating/Integrity/Rep\nAmazon 40/35/25\neBay  30/25/45"]
  end
 subgraph TREND["Price Intelligence"]
        T1["Seeded trend generator\n30-day series · hash seed"]
        T2["Insight detector\nlow · high · average\nmomentum · drop-watch"]
  end
 subgraph AILAY["Gemini AI · gemini-2.5-flash"]
        G1["Verdict · BUY / COMPARE / SKIP"]
        G2["Score explainer\nRec query builder"]
        G3["Price trend narrative\nlikely-to-drop · confidence · callouts"]
  end
    USER(["Amazon / eBay"]) --> E1
    E1 --> R1
    A1 --> P1
    P1 --> N1 & CANOPY["Canopy API\nAmazon GraphQL"] & SCRAPER["ScraperAPI\neBay structured"]
    N1 --> G1
    G1 -- verdict · scores --> R1
    N2 --> PLACES["Google Places\nBrand lookup · Review\nsignals · Insights"]
    G1 --> G2
    G2 --> GAPI["Gemini API\ngemini-2.5-flash ·  flash lite fallback · context + snippets"]
    R1 -- "HTTP · X-Nectar-Secret" --> A1
    R2 --> A2
    R3 -- "selected scan" --> A3
    A3 --> T1 --> T2 --> G3
    G3 -- "narrative · drop call · chart callouts" --> R3
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
NECTAR_API_SECRET=your_shared_secret_here
```
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
