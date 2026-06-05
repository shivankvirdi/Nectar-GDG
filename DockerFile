FROM python:3.12-slim

WORKDIR /app

# Install deps first (better layer caching)
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Download NLTK data at build time so the container starts fast
RUN python -c "import nltk; nltk.download('vader_lexicon', quiet=True); nltk.download('stopwords', quiet=True); nltk.download('punkt', quiet=True); nltk.download('punkt_tab', quiet=True); nltk.download('wordnet', quiet=True); nltk.download('averaged_perceptron_tagger', quiet=True)"

# Copy the whole project
COPY . .

# Cloud Run injects $PORT; default to 8080 for local Docker runs
ENV PORT=8080

CMD uvicorn backend.main:app --host 0.0.0.0 --port ${PORT}