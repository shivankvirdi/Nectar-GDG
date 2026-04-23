Nectar is a product-analyzer Chrome extension that compares products and provides in-depth information on price points, review integrity, quality, brand reputation, and more, recommending the best option. Our mission is to reduce shoppers’ stress when buying products and provide a more educated shopping experience.

## Clone Repository:
```bash
git clone https://github.com/aagarw56/GDGC-Ballers.git
cd GDGC-Ballers
```
## Backend Setup
```bash
cd backend
python -m venv .venv
```
### Activate virtual environment
```bash
.venv\Scripts\activate # Windows
source .venv/bin/activate # Mac/Linux
```
### Install dependencies
```bash
pip install -r requirements.txt
```
## Create .env in ROOT directory:
```
CANOPY_API_KEY="your_api_key_here"
GEMINI_API_KEY="your_api_key_here"
GOOGLE_PLACES_API_KEY=your_api_key_here
```
## Frontend Setup
Install Node.js (http://nodejs.org/en/download) and add to PATH.
```bash
cd frontend
npm install
```
### Build extension
```bash
npm run build
```
## Load Extension
1. Go to chrome://extensions/
2. Enable "Developer mode"
3. Click load unpacked
4. Select GDGC-Ballers/frontend/dist

## Deploying Backend Server
### Use hosted backend (Recommended): 
The backend is already deployed on Render -- no setup required.  
### Deploy locally (Optional)
1. Set frontend/.env.production to:
```bash
VITE_API_URL=http://127.0.0.1:8000
```
3. Rebuild extension:
```bash
cd frontend
npm run build
```
4. Run backend:
```bash
cd ..
uvicorn backend.main:app --reload
```
_____________________________________________________________________________________________________________________________________________________
Co-developed by Shivank Virdi, Iyanna Arches, Jaycob Pakingan, Aanya Agarwal, & Kaylana Chaun. We hope you enjoy using our extension!
