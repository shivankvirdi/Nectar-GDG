Nectar is a product-analyzer Chrome extension that provides in-depth information on products’ price points, review integrity, quality, brand reputation, and more, recommending the best option. Our mission is to reduce shoppers’ stress when buying products and provide a more educated shopping experience.

## Setting up environment:
```bash
git clone https://github.com/aagarw56/GDGC-Ballers.git
cd GDGC-Ballers/backend
python -m venv .venv
.venv/Scripts/activate
pip install -r requirements.txt
```
Also install node.js (http://nodejs.org/en/download) and add to PATH.
## Create .env file in root directory and add/fill this code:
```bash
CANOPY_API_KEY="your_api_key_here"
GROQ_API_KEY="your_api_key_here"
```
## How to run:
```bash
cd frontend
npm install
npm run build #sets up frontend
cd..
uvicorn backend.main:app --reload #starts backend server (port 8000)
```
Go to chrome://extensions/, turn on "Developer mode", click load unpacked, and upload the Nectar/frontend/dist file.  
_____________________________________________________________________________________________________________________________________________________
Co-developed with Iyanna Arches, Jaycob Pakingan, Aanya Agarwal, & Kaylana Chaun. We hope you enjoy using our extension!
