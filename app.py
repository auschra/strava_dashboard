import os
import requests
from flask import Flask, jsonify, render_template, request
from datetime import datetime
from dotenv import load_dotenv, set_key

load_dotenv()

STRAVA_CLIENT_ID = os.getenv('STRAVA_CLIENT_ID')
STRAVA_CLIENT_SECRET = os.getenv('STRAVA_CLIENT_SECRET')
STRAVA_ACCESS_TOKEN = os.getenv('STRAVA_ACCESS_TOKEN')
STRAVA_REFRESH_TOKEN = os.getenv('STRAVA_REFRESH_TOKEN')
ATHLETE_IDS = os.getenv('ATHLETE_IDS').split(',')

STRAVA_API_BASE = 'https://www.strava.com/api/v3'

app = Flask(__name__)

# --- Token Refresh Helper ---
def refresh_access_token():
    global STRAVA_ACCESS_TOKEN, STRAVA_REFRESH_TOKEN  
    response = requests.post(
        f"{STRAVA_API_BASE}/oauth/token",
        data={
            "client_id": STRAVA_CLIENT_ID,
            "client_secret": STRAVA_CLIENT_SECRET,
            "grant_type": "refresh_token",
            "refresh_token": STRAVA_REFRESH_TOKEN
        }
    )
    if response.status_code == 200:
        tokens = response.json()
        STRAVA_ACCESS_TOKEN = tokens['access_token'].replace('"', '').replace("'", '')
        STRAVA_REFRESH_TOKEN = tokens['refresh_token'].replace('"', '').replace("'", '')
        # Read all lines from .env except the token lines
        with open('.env', 'r') as f:
            lines = f.readlines()
        with open('.env', 'w') as f:
            for line in lines:
                if not line.startswith('STRAVA_ACCESS_TOKEN=') and not line.startswith('STRAVA_REFRESH_TOKEN='):
                    f.write(line)
            # Write the new tokens (no quotes)
            f.write(f"STRAVA_ACCESS_TOKEN={STRAVA_ACCESS_TOKEN}\n")
            f.write(f"STRAVA_REFRESH_TOKEN={STRAVA_REFRESH_TOKEN}\n")
        print("Refreshed Strava access token.")
        return STRAVA_ACCESS_TOKEN
    else:
        print("Failed to refresh token:", response.text)
        return None

# --- Wrapped get_activities with auto-refresh ---
def get_activities(athlete_id, access_token):
    url = f"{STRAVA_API_BASE}/athlete/activities"
    headers = {"Authorization": f"Bearer {access_token}"}
    params = {"per_page": 100}
    r = requests.get(url, headers=headers, params=params)
    print(f"Fetching activities for athlete {athlete_id}, status: {r.status_code}")
    if r.status_code == 200:
        print(f"Returned {len(r.json())} activities")
        return r.json()
    else:
        print("Error:", r.text)
        return []

@app.route('/stats/<athlete_id>')
def stats(athlete_id):
    if athlete_id not in ATHLETE_IDS:
        return jsonify({"error": "Invalid athlete ID"}), 400
    activities = get_activities(athlete_id, STRAVA_ACCESS_TOKEN)
    total_km = sum(a['distance'] for a in activities) / 1000
    return jsonify({
        "athlete_id": athlete_id,
        "total_km_this_month": round(total_km, 2),
        "activity_count": len(activities)
    })

@app.route('/')
def dashboard():
    athlete_stats = []
    for athlete_id in ATHLETE_IDS:
        activities = get_activities(athlete_id, STRAVA_ACCESS_TOKEN)
        total_km = sum(a['distance'] for a in activities) / 1000
        athlete_stats.append({
            'athlete_id': athlete_id,
            'total_km_this_month': round(total_km, 2),
            'activity_count': len(activities)
        })
    return render_template('dashboard.html', athletes=athlete_stats)

# New endpoint: Get all activities for all athletes (for heatmaps, art, etc.)
@app.route('/api/activities')
def api_activities():
    # Get month/year from query params if present
    month = request.args.get('month', type=int)
    year = request.args.get('year', type=int)
    results = []
    for athlete_id in ATHLETE_IDS:
        acts = get_activities(athlete_id, STRAVA_ACCESS_TOKEN)
        acts = acts[:10]  # Only use the last 10 activities
        for a in acts:
            # Filter by month/year if provided
            if month and year:
                try:
                    dt = datetime.strptime(a['start_date'][:10], '%Y-%m-%d')
                    if dt.month != month or dt.year != year:
                        continue
                except Exception:
                    continue
            results.append({
                'athlete_id': athlete_id,
                'id': a['id'],
                'name': a.get('name'),
                'distance': a.get('distance', 0),
                'moving_time': a.get('moving_time', 0),
                'start_date': a.get('start_date'),
                'polyline': a.get('map', {}).get('summary_polyline'),
                'elevation_gain': a.get('total_elevation_gain', 0),
                'elevations': a.get('elevations', [])
            })
    return jsonify(results)

# New endpoint: Calendar data for heatmaps
@app.route('/api/calendar')
def api_calendar():
    data = {}
    for athlete_id in ATHLETE_IDS:
        acts = get_activities(athlete_id, STRAVA_ACCESS_TOKEN)
        cal = {}
        for a in acts:
            day = a['start_date'][:10]  # YYYY-MM-DD
            cal[day] = cal.get(day, 0) + 1
        data[athlete_id] = cal
    return jsonify(data)

# New endpoint: Best of (longest, fastest)
@app.route('/api/bestof')
def api_bestof():
    best = {}
    for athlete_id in ATHLETE_IDS:
        acts = get_activities(athlete_id, STRAVA_ACCESS_TOKEN)
        if not acts:
            continue
        longest = max(acts, key=lambda x: x.get('distance', 0))
        fastest = max(acts, key=lambda x: x.get('distance', 0)/x.get('moving_time', 1) if x.get('moving_time', 0) else 0)
        best[athlete_id] = {
            'longest': {
                'id': longest['id'],
                'distance': longest.get('distance', 0),
                'polyline': longest.get('map', {}).get('polyline'),
                'name': longest.get('name')
            },
            'fastest': {
                'id': fastest['id'],
                'distance': fastest.get('distance', 0),
                'speed': fastest.get('distance', 0)/fastest.get('moving_time', 1),
                'polyline': fastest.get('map', {}).get('polyline'),
                'name': fastest.get('name')
            }
        }
    return jsonify(best)

# New endpoint: Elevation profiles
@app.route('/api/elevation')
def api_elevation():
    data = {}
    for athlete_id in ATHLETE_IDS:
        acts = get_activities(athlete_id, STRAVA_ACCESS_TOKEN)
        data[athlete_id] = [a.get('total_elevation_gain', 0) for a in acts]
    return jsonify(data)

# New endpoint: Leaderboard
@app.route('/api/leaderboard')
def api_leaderboard():
    month = request.args.get('month', type=int)
    year = request.args.get('year', type=int)
    leaderboard = []
    for athlete_id in ATHLETE_IDS:
        acts = get_activities(athlete_id, STRAVA_ACCESS_TOKEN)
        # Filter for selected month/year
        monthly_acts = []
        for a in acts:
            try:
                dt = datetime.strptime(a['start_date'][:10], '%Y-%m-%d')
                if dt.month == month and dt.year == year:
                    monthly_acts.append(a)
            except Exception:
                continue
        # Sort by date
        monthly_acts.sort(key=lambda a: a['start_date'])
        # Cumulative distance by day
        daily = {}
        for a in monthly_acts:
            day = a['start_date'][:10]
            daily[day] = daily.get(day, 0) + a.get('distance', 0)
        # Cumulative sum
        cum = []
        total = 0
        for day in sorted(daily.keys()):
            total += daily[day]
            cum.append({'date': day, 'cum_km': round(total/1000, 2)})
        leaderboard.append({
            'athlete_id': athlete_id,
            'cum': cum,
            'total_km': round(total/1000, 2),
            'activity_count': len(monthly_acts)
        })
    return jsonify(leaderboard)

# Update dashboard route to use new advanced template
@app.route('/advanced')
def advanced_dashboard():
    return render_template('dashboard_advanced.html')

if __name__ == '__main__':
    app.run(debug=True)
