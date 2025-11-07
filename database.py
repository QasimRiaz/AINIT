import os
import psycopg2
from dotenv import load_dotenv

# Load environment variables from the .env file
load_dotenv()

def get_db_connection():
    """Establishes and returns a connection to the database."""
    try:
        # Read the database URL from the environment variable
        db_url = os.getenv("DATABASE_URL")
        if not db_url:
            raise ValueError("DATABASE_URL is not set in the .env file")

        # Establish the connection
        conn = psycopg2.connect(db_url)
        print("✅ Database connection successful!")
        return conn
    except psycopg2.OperationalError as e:
        print(f"❌ Could not connect to the database. Error: {e}")
        return None
    except Exception as e:
        print(f"❌ An unexpected error occurred: {e}")
        return None

def test_connection():
    """Tests the database connection and closes it."""
    conn = get_db_connection()
    if conn:
        # If connection is successful, close it to free up resources
        conn.close()
        print("✅ Connection closed.")

# --- Main execution block ---
if __name__ == "__main__":
    print("Attempting to connect to the database...")
    test_connection()