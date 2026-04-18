Nectar is a product-analyzer Chrome extension that provides in-depth information on products’ price points, history, quality, brand reputation, and more, recommending the best option. Our mission is to reduce shopper’s stress when buying products and providing a more educated shopping experience.

## Setting up environment:
```
git clone https://github.com/aagarw56/GDGC-Ballers.git
cd GDGC-Ballers
cd backend
python -m venv .venv
.venv/Scripts/activate
pip install -r requirements.txt
```
Also install node.js (http://nodejs.org/en/download) and add to PATH.
## Create .env file in root directiry and add/fill this code:
```
CANOPY_API_KEY="your_api_key_here"
GROQ_API_KEY="your_api_key_here"
```
## How to run:
```
uvicorn backend.main:app --reload #starts backend server (port 8000)
cd frontend
npm install
npm run build #sets up frontend
```
Go to chrome://extensions/, turn on "Developer mode", click load unpacked, and upload GDGC-Ballers/frontend/dist file. We hope you enjoy using our extension!
