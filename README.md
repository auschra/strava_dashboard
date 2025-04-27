# Strava Competition Dashboard

## Setup

1. Create a `.env` file with your Strava API credentials and athlete IDs (already scaffolded).
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Run the app:
   ```
   python app.py
   ```

## Features
- Fetches and displays stats for competition athletes.
- Visualizes total km for the month and activity paths.

## Notes
- Do not expose your `.env` file or secrets publicly.
- Rate limit: 100 requests per 10 minutes.
