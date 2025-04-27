import sqlite3

def init_db(db_path='activities.db'):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS activities (
            activity_id INTEGER PRIMARY KEY,
            athlete_id INTEGER,
            name TEXT,
            start_date TEXT,
            distance REAL,
            moving_time INTEGER,
            polyline TEXT,
            elevation_gain REAL,
            elevations TEXT
        )
    ''')
    conn.commit()
    conn.close()

if __name__ == '__main__':
    init_db()
    print('Database initialized.')
