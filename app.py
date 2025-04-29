import os
import requests
from flask import Flask, jsonify, render_template, request
from datetime import datetime
from dotenv import load_dotenv, set_key
import json

load_dotenv()

STRAVA_CLIENT_ID = os.getenv('STRAVA_CLIENT_ID')
STRAVA_CLIENT_SECRET = os.getenv('STRAVA_CLIENT_SECRET')
STRAVA_ACCESS_TOKEN = os.getenv('STRAVA_ACCESS_TOKEN')
STRAVA_REFRESH_TOKEN = os.getenv('STRAVA_REFRESH_TOKEN')

# Load athlete mapping from athletes.json
with open(os.path.join(os.path.dirname(__file__), 'athletes.json'), 'r') as f:
    ATHLETE_MAP = json.load(f)

ATHLETE_IDS = list(ATHLETE_MAP.keys())

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
    print(f"[get_activities] athlete_id={athlete_id} using token={access_token[:8]}... status={r.status_code}")
    # Auto-refresh access token on authorization error
    if r.status_code == 401:
        print("Access token expired, refreshing...")
        new_token = refresh_access_token()
        if new_token:
            headers = {"Authorization": f"Bearer {STRAVA_ACCESS_TOKEN}"}
            r = requests.get(url, headers=headers, params=params)
            print(f"[get_activities] RETRY athlete_id={athlete_id} using token={STRAVA_ACCESS_TOKEN[:8]}... status={r.status_code}")
        else:
            print("[get_activities] Token refresh failed.")
            return []
    print(f"[get_activities] Fetching activities for athlete {athlete_id}, status: {r.status_code}")
    if r.status_code == 200:
        activities = r.json()
        print(f"[get_activities] Returned {len(activities)} activities for athlete {athlete_id}")
        # Print the first and last activity dates if present
        if activities:
            print(f"[get_activities] First activity date: {activities[0]['start_date']}, Last: {activities[-1]['start_date']}")
        return activities
    else:
        print("[get_activities] Error:", r.text)
        return []

# Helper: format seconds to H:MM:SS or M:SS
def format_time(seconds):
    secs = int(seconds)
    m, s = divmod(secs, 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"

@app.route('/stats/<athlete_id>')
def stats(athlete_id):
    if athlete_id not in ATHLETE_IDS:
        return jsonify({"error": "Invalid athlete ID"}), 400
    activities = get_activities(athlete_id, STRAVA_ACCESS_TOKEN)
    total_km = sum(a['distance'] for a in activities) / 1000
    return jsonify({
        "athlete_id": athlete_id,
        "athlete_name": ATHLETE_MAP.get(athlete_id, athlete_id),
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
            'athlete_name': ATHLETE_MAP.get(athlete_id, athlete_id),
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
                'athlete_name': ATHLETE_MAP.get(athlete_id, athlete_id),
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
            'athlete_name': ATHLETE_MAP.get(athlete_id, athlete_id),
            'longest': {
                'id': longest['id'],
                'distance': longest.get('distance', 0),
                'polyline': longest.get('map', {}).get('summary_polyline'),
                'name': longest.get('name')
            },
            'fastest': {
                'id': fastest['id'],
                'distance': fastest.get('distance', 0),
                'speed': fastest.get('distance', 0)/fastest.get('moving_time', 1),
                'polyline': fastest.get('map', {}).get('summary_polyline'),
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
        data[athlete_id] = {
            'athlete_name': ATHLETE_MAP.get(athlete_id, athlete_id),
            'elevation_gains': [a.get('total_elevation_gain', 0) for a in acts]
        }
    return jsonify(data)

# New endpoint: Leaderboard
@app.route('/api/leaderboard')
def api_leaderboard():
    month = request.args.get('month', type=int)
    year = request.args.get('year', type=int)
    print(f"[api_leaderboard] month={month} year={year}")
    leaderboard = []
    from polyline_grid import route_grid_signature, routes_similar
    for athlete_id in ATHLETE_IDS:
        acts = get_activities(athlete_id, STRAVA_ACCESS_TOKEN)
        print(f"[api_leaderboard] athlete_id={athlete_id} fetched {len(acts)} activities")
        # Filter for selected month/year
        monthly_acts = []
        for a in acts:
            try:
                dt = datetime.strptime(a['start_date'][:10], '%Y-%m-%d')
                if dt.month == month and dt.year == year:
                    monthly_acts.append(a)
            except Exception as ex:
                print(f"[api_leaderboard] Error parsing date for activity {a.get('id')}: {ex}")
                continue
        print(f"[api_leaderboard] athlete_id={athlete_id} monthly_acts count: {len(monthly_acts)}")
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
        # Count medals for this athlete in this month
        gold = silver = bronze = 0
        route_records = 0
        for a in monthly_acts:
            for effort in a.get('segment_efforts', []):
                pr_rank = effort.get('pr_rank')
                if pr_rank == 1:
                    gold += 1
                    route_records += 1
                elif pr_rank == 2:
                    silver += 1
                elif pr_rank == 3:
                    bronze += 1
        # Metrics: pace, elevation, GAP, moving time, splits
        total_distance = sum(a.get('distance', 0) for a in monthly_acts)
        total_moving_time = sum(a.get('moving_time', 0) for a in monthly_acts)
        avg_pace_sec = (total_moving_time / (total_distance/1000)) if total_distance > 0 else 0
        total_elev_gain = sum(a.get('total_elevation_gain', 0) for a in monthly_acts)
        avg_elev_gain = (total_elev_gain / len(monthly_acts)) if monthly_acts else 0
        grade = (total_elev_gain / total_distance) if total_distance > 0 else 0
        gap_sec = avg_pace_sec * (1 + grade)
        # Splits
        one_km = [a['moving_time']/a['distance']*1000 for a in monthly_acts if a.get('distance',0)>0]
        five_km = [a['moving_time']/a['distance']*5000 for a in monthly_acts if a.get('distance',0)>=5000]
        ten_km = [a['moving_time']/a['distance']*10000 for a in monthly_acts if a.get('distance',0)>=10000]
        fastest_1km = min(one_km) if one_km else 0
        fastest_5km = min(five_km) if five_km else 0
        fastest_10km = min(ten_km) if ten_km else 0
        # --- Diversity: Grid-based route uniqueness ---
        route_signatures = []
        for a in monthly_acts:
            polyline = a.get('map', {}).get('summary_polyline')
            if not polyline:
                continue
            sig = route_grid_signature(polyline, precision=4)
            # Check if similar route already exists
            found_similar = False
            for existing in route_signatures:
                if routes_similar(sig, existing, jaccard_threshold=0.7):
                    found_similar = True
                    break
            if not found_similar:
                route_signatures.append(sig)
        unique_routes = len(route_signatures)
        diversity = round(unique_routes / len(monthly_acts), 2) if monthly_acts else 0
        leaderboard.append({
            'athlete_id': athlete_id,
            'athlete_name': ATHLETE_MAP.get(athlete_id, athlete_id),
            'cum': cum,
            'gold': gold, 'silver': silver, 'bronze': bronze, 'route_records': route_records,
            'avg_pace': format_time(avg_pace_sec),
            'total_elev_gain': total_elev_gain,
            'avg_elev_gain': round(avg_elev_gain, 2),
            'gap': format_time(gap_sec),
            'total_moving_time': format_time(total_moving_time),
            'fastest_1km': format_time(fastest_1km),
            'fastest_5km': format_time(fastest_5km),
            'fastest_10km': format_time(fastest_10km),
            'diversity': diversity,
            'total_km': round(total_distance/1000, 2),
            'activity_count': len(monthly_acts),
            'activities': [
                {
                    'id': a.get('id'),
                    'start_date': a.get('start_date'),
                    'distance': a.get('distance'),
                    'type': a.get('type'),
                    'moving_time': a.get('moving_time'),
                    'total_elevation_gain': a.get('total_elevation_gain', a.get('elevation_gain', 0)),
                } for a in monthly_acts
            ]
        })
    return jsonify(leaderboard)

if __name__ == '__main__':
    app.run(debug=True)
