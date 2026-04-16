# db.py
# This file handles the connection between our Flask app and MySQL database.
# Think of it like a phone line — every time we need data, we call through this file.

import mysql.connector  # Library that lets Python talk to MySQL

# These are the settings to connect to YOUR MySQL on your laptop
DB_CONFIG = {
    "host":     "localhost",       # MySQL is running on this same computer
    "user":     "root",            # Your MySQL username (default is root)
    "password": "Root@1234",   # YOUR MySQL password — change this!
    "database": "fraud_detection_db"  # The database we created earlier
}

def get_connection():
    """
    This function opens a fresh connection to MySQL and returns it.
    We call this every time we want to read or write data.
    """
    connection = mysql.connector.connect(**DB_CONFIG)
    return connection


def fetch_all(query, params=None):
    """
    Run a SELECT query and return ALL matching rows as a list.
    
    Example use:
        rows = fetch_all("SELECT * FROM users WHERE city = %s", ("Mumbai",))
    
    params: values to safely insert into the query (prevents SQL injection)
    """
    conn   = get_connection()          # Open connection
    cursor = conn.cursor(dictionary=True)  # dictionary=True means rows come as {column: value}
    cursor.execute(query, params or ())    # Run the query
    rows   = cursor.fetchall()             # Get all results
    cursor.close()                         # Close cursor
    conn.close()                           # Close connection
    return rows                            # Return the data


def fetch_one(query, params=None):
    """
    Run a SELECT query and return only the FIRST matching row.
    Useful when we expect exactly one result (like finding a user by ID).
    """
    conn   = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(query, params or ())
    row    = cursor.fetchone()   # Only fetch first row
    cursor.close()
    conn.close()
    return row


def execute_query(query, params=None):
    """
    Run an INSERT, UPDATE, or DELETE query.
    This changes data in the database.
    
    Returns the ID of the last inserted row (useful after INSERT).
    """
    conn   = get_connection()
    cursor = conn.cursor()
    cursor.execute(query, params or ())
    conn.commit()              # Save the changes permanently
    last_id = cursor.lastrowid # Get the auto-generated ID
    cursor.close()
    conn.close()
    return last_id
