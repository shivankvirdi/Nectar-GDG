

https://github.com/user-attachments/assets/503b7d96-bcd8-418d-aa47-0589f6e007b4


E-commerce lacks trustworthy product intelligence, with consumers losing billions to misleading/inflated reviews and poor purchasing decisions every year. That's why we built Nectar, a product-analyzer Chrome extension that builds this needed trust layer, comparing products and providing in-depth insights on price, review integrity, quality, brand reputation, and similar alternatives. Nectar recommends the best option to help reduce shopper stress and support more informed purchasing decisions.

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
Install Node.js (http://nodejs.org/en/download) and add to PATH. Then install electron.
```powershell
cd frontend
npm install
npm install electron --save-dev
```
### Build extension
```powershell
npm run build
```
## Deploying Backend Server
### Use hosted backend (Requires a secret password): 
The backend is already deployed on Google Cloud!
1. Create file frontend/.env.production
2. Set VITE_API_URL=https://nectar-gdg-93066440894.us-west1.run.app and VITE_NECTAR_SECRET to the password
3. Run electron:
```
cd frontend
npm run electron:start
```

### Deploy locally
1. Create .env in ROOT directory and add keys
https://www.canopyapi.co/  
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
3. Rebuild extension:
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
---
Project led by Shivank Virdi and co-developed with Jaycob Pakingan, Iyanna Arches, Aanya Agarwal, & Kaylana Chuan. We hope you enjoy using our application!
