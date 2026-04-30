

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
## Create .env in ROOT directory and add keys
https://www.canopyapi.co/  
https://aistudio.google.com/app/api-keys  
https://console.cloud.google.com/marketplace/product/google/places.googleapis.com
```
CANOPY_API_KEY="your_api_key_here"
GEMINI_API_KEY="your_api_key_here"
GOOGLE_PLACES_API_KEY=your_api_key_here
```
## Frontend Setup
Install Node.js (http://nodejs.org/en/download) and add to PATH.
```powershell
cd frontend
npm install
```
### Build extension
```powershell
npm run build
```
## Load Extension
1. Go to chrome://extensions/
2. Enable "Developer mode"
3. Click load unpacked
4. Select Nectar-GDG/frontend/dist

## Deploying Backend Server
### Use hosted backend (Recommended): 
The backend is already deployed on Render -- no setup required. (Check if VITE URL correct)
### Deploy locally (Optional)
1. Set frontend/.env.production to:
```powershell
VITE_API_URL=http://127.0.0.1:8000
```
3. Rebuild extension:
```powershell
cd frontend
npm run build
```
4. Run backend:
```powershell
cd ..
uvicorn backend.main:app --reload
```
---
Project led by Shivank Virdi and co-developed with Jaycob Pakingan, Iyanna Arches, Aanya Agarwal, & Kaylana Chuan. We hope you enjoy using our extension!
