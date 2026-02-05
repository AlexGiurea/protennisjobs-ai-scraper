# ProTennisJobs AI Scraper

AI-powered ProTennisJobs scraper with fit scoring, distance calculations,
auto-generated personalized emails, and a browsing dashboard. Demo:

## Features
- Scrapes tennis professional listings from ProTennisJobs.
- Scores each listing with an AI suitability score (0-10).
- Calculates distance to Harrogate, TN for quick location filtering.
- Web UI to browse, filter, and search jobs.
- Generates personalized email drafts for job outreach.
- Optional auto-refresh on a configurable interval.

## Requirements
- Python 3.10+
- An OpenAI API key for AI scoring and email drafts.

Install dependencies:
```
pip install -r requirements.txt
```

## Environment variables
Create a `.env` file in the project root if needed:
```
OPENAI_API_KEY=your_key_here
OPENAI_MODEL=gpt-4o-mini
OPENAI_EMAIL_MODEL=gpt-4o-mini
OPENAI_API_URL=https://api.openai.com/v1/responses
OPENAI_MIN_INTERVAL=0.2
OPENAI_MAX_INPUT_CHARS=1500
PTJ_COOKIES=key=value; key2=value2
PTJ_REFRESH_DAYS=3
```

Notes:
- `PTJ_COOKIES` is optional; it can help access gated pages if required.
- Set `PTJ_REFRESH_DAYS=0` to disable auto-refresh in the web server.

## Run the scraper
```
python src/scrape_protennisjobs.py
```

Outputs:
- `data/protennisjobs.json`
- `data/protennisjobs.csv`

## Run the web server
```
python src/server.py
```

Open `http://localhost:8000` in your browser.

## Data files
Generated data is stored in `data/`. This repo excludes local caches and
personal email drafts by default.

## Project goal
Help a tennis professional identify strong winter-season job opportunities by
automating listing collection, enrichment, scoring, and outreach preparation.
