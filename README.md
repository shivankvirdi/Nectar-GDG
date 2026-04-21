Nectar is a product-analyzer Chrome extension that provides in-depth information on products’ price points, review integrity, quality, brand reputation, and more, recommending the best option. Our mission is to reduce shoppers’ stress when buying products and provide a more educated shopping experience.

## Clone Repository:
```bash
git clone https://github.com/aagarw56/GDGC-Ballers.git
cd GDGC-Ballers
```
## Backend Setup
Install node.js (http://nodejs.org/en/download) and add to PATH.
```bash
cd backend
python -m venv .venv
.venv\Scripts\activate # Windows
source .venv/bin/activate # Mac/Linux
```
## Create .env in ROOT directory:
```
CANOPY_API_KEY="your_api_key_here"
GEMINI_API_KEY="your_api_key_here"
```
## Frontend Setup
```bash
cd frontend
npm install
npm run build
```
## Load Extension
1. Go to chrome://extensions/
2. Enable "Developer mode"
3. Click load unpacked
4. Select GDGC-Ballers/frontend/dist

## Deploying Backend Server
Use hosted backend already deployed on Render -- no setup required.  
### Deploy locally (optional)
Change frontend/.env.production to:
```
VITE_API_URL=http://127.0.0.1:8000
```
Then run this in terminal:
```bash
cd frontend
npm run build
cd..
uvicorn backend.main:app --reload
```
_____________________________________________________________________________________________________________________________________________________
Co-developed by Shivank Virdi, Iyanna Arches, Jaycob Pakingan, Aanya Agarwal, & Kaylana Chaun. We hope you enjoy using our extension!
