import sqlite3

def initialize_database():
    conn = None
    try:
        conn = sqlite3.connect('foxhunt.db')
        cursor = conn.cursor()

        # Enable foreign key support
        cursor.execute("PRAGMA foreign_keys = ON;")

        # Define users table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('admin', 'moderator'))
        )
        ''')

        # Define vossenjachten table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS vossenjachten (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            creation_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            creator_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'completed')),
            type TEXT NOT NULL CHECK (type IN ('kilometers', 'time', 'both')),
            FOREIGN KEY (creator_id) REFERENCES users (id)
        )
        ''')

        # Modify entries table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            start_km REAL NOT NULL,
            end_km REAL NOT NULL,
            arrival_time_last_fox TEXT NOT NULL,
            calculated_km REAL NOT NULL,
            duration_minutes INTEGER NOT NULL,
            vossenjacht_id INTEGER,
            user_id INTEGER,
            FOREIGN KEY (vossenjacht_id) REFERENCES vossenjachten (id),
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        ''')
        conn.commit()
        print("Database 'foxhunt.db' initialized successfully with 'users', 'vossenjachten', and 'entries' tables.")
    except sqlite3.Error as e:
        print(f"Database initialization error: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == '__main__':
    initialize_database()
