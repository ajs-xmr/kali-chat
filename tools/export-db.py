#!/usr/bin/env python3
"""
Extracts chat history from SQLite database and exports to CSV
"""

import sqlite3
import csv
from pathlib import Path

# Configuration
DB_PATH = Path('data/chat.db')
CSV_OUTPUT = Path('chat_history.csv')

def extract_chat_data(db_path: Path) -> list[dict]:
    """Extracts all messages from the database"""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row  # Enable column name access
    
    try:
        # Get all tables for debugging
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        print(f"Found tables: {[t['name'] for t in tables]}")

        # Fetch all messages (modify query based on your schema)
        cursor = conn.execute("""
            SELECT * FROM messages 
            ORDER BY timestamp ASC
        """)
        
        return [dict(row) for row in cursor]
    
    finally:
        conn.close()

def save_to_csv(data: list[dict], output_path: Path):
    """Saves extracted data to CSV"""
    if not data:
        print("⚠️ No data to export")
        return

    with open(output_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=data[0].keys())
        writer.writeheader()
        writer.writerows(data)
    print(f"✅ Saved {len(data)} messages to {output_path}")

if __name__ == '__main__':
    # Create output directory if needed
    CSV_OUTPUT.parent.mkdir(exist_ok=True)
    
    # Verify database exists
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found at {DB_PATH}")
    
    # Extract and export data
    chat_data = extract_chat_data(DB_PATH)
    save_to_csv(chat_data, CSV_OUTPUT)
