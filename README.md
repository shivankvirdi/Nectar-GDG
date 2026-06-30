<img width="4000" height="2151" alt="colored-logo" src="https://github.com/user-attachments/assets/16f37d8e-4db0-4c01-be25-36844072743c" />

<table width="100%">
  <tr>
    <td width="50%" align="center" style="vertical-align: top;">
      <video src="https://github.com/user-attachments/assets/ddae5e9f-4c1e-467c-8047-de4eda39c38a" width="100%" controls></video> 
    </td>
    <td width="50%" align="center" style="vertical-align: top;">
      <img width="100%" alt="nectar price history" src="https://github.com/user-attachments/assets/f6fddc62-5f93-4d36-bbc6-846302878deb" />
    </td>
  </tr>
</table>

E-commerce lacks trustworthy product intelligence, with consumers losing $245 billion to poor purchasing decisions yearly in the US alone. That's why we built Nectar, a desktop overlay application that helps consumers make smarter online purchasing decisions by analyzing products on Amazon and eBay in real time. The app combines review authenticity detection, AI review summaries/product verdicts, personalized recommendations, brand reputation analysis, estimated price trends, and product comparison tools to identify trustworthy products and flag potentially misleading listings. By increasing transparency in e-commerce, Nectar reduces decision fatigue and empowers users to shop with greater confidence and accuracy.

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
    A["<img src="https://github.com/user-attachments/assets/5ab7c2bb-3334-4314-a9b9-63f6f7c7e47f" width='50' />"]
    subgraph ELECTRON["Electron Shell"]
        E1["Frameless glass overlay<br/>always-on-top · IPC resize"]
        E2["URL detection<br/>AppleScript · PS · xdotool"]
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
> **Note on Price History:** The price trend chart and "likely to drop" call are generated, not scraped from real marketplace history. Nectar deterministically synthesizes a 30-day series anchored to the actual scraped price (so the chart always ends at the true current price), with a seeded wiggle, drift, and one simulated dip for realism. Gemini then writes a narrative and confidence score based on that synthetic series. This is a placeholder for a future real price-tracking integration and should not be used to make real purchasing-timing decisions.

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
> Skip this section if you're only using the hosted backend
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
### Choosing Backend
Before building, choose your backend (see below) and create `frontend/.env.production` accordingly
#### Use Hosted Backend (Requires a secret password)
The backend is already deployed on Google Cloud!\
Create file `frontend/.env.production`:
``` 
VITE_API_URL=https://nectar-gdg-93066440894.us-west1.run.app
NECTAR_API_SECRET=...
# contact maintainers for password access
```
#### Use Local Backend
1. Follow .env.example & add keys to `Nectar-GDG/.env` (repo root)
2. Create file `frontend/.env.production`:
```powershell
VITE_API_URL=http://127.0.0.1:8000
# no password
```
### Build frontend assets:
```powershell
npm run build
```
## Running Nectar:
```powershell
# Terminal 1 in frontend directory
npm run electron:start
# Terminal 2 in ROOT — only if using local backend (run alongside Terminal 1)
# Make sure backend/.venv is activated first
uvicorn backend.main:app --reload
```
## Troubleshooting
### Electron won't start
Delete `node_modules` and reinstall:
```
npm install
```
### Backend fails to start
Verify:
- `CANOPY_API_KEY`
- `GEMINI_API_KEY`
- `GOOGLE_PLACES_API_KEY`
- `SCRAPERAPI_KEY`
### CORS or connection issues
#### Verify `VITE_API_URL` matches correct URL.
```text
http://127.0.0.1:8000 (for localhost)
https://nectar-gdg-93066440894.us-west1.run.app (for Google Cloud)
```
---
Project led by Shivank Virdi and co-developed with Iyanna Arches, Jaycob Pakingan, Aanya Agarwal, & Kaylana Chuan. We hope you enjoy using our application!
