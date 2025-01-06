import os
import psycopg2
from psycopg2 import pool
from datetime import datetime
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DatabaseHandler:
    def __init__(self):
        self.database_url = os.environ.get('DATABASE_URL')
        if not self.database_url:
            raise ValueError("DATABASE_URL environment variable not set")

        try:
            self.pool = psycopg2.pool.SimpleConnectionPool(
                minconn=1,
                maxconn=10,
                dsn=self.database_url
            )
            logger.info("Database connection pool created successfully")
        except Exception as e:
            logger.error(f"Failed to create connection pool: {e}")
            raise

    def init_db(self):
        """Initialize database tables"""
        conn = None
        try:
            conn = self.pool.getconn()
            with conn.cursor() as cur:
                # Create users table
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS users (
                        user_id BIGINT PRIMARY KEY,
                        language VARCHAR(2)
                    )
                ''')

                # Create food_diary table with foreign key
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS food_diary (
                        id SERIAL PRIMARY KEY,
                        user_id BIGINT,
                        calories INTEGER,
                        date DATE,
                        time TIME,
                        FOREIGN KEY (user_id) REFERENCES users(user_id)
                            ON DELETE CASCADE
                    )
                ''')
                conn.commit()
                logger.info("Database tables initialized successfully")
        except Exception as e:
            logger.error(f"Database initialization error: {e}")
            if conn:
                conn.rollback()
            raise
        finally:
            if conn:
                self.pool.putconn(conn)

    def save_user_language(self, user_id: int, language: str):
        """Save or update user language preference"""
        conn = None
        try:
            conn = self.pool.getconn()
            with conn.cursor() as cur:
                cur.execute('''
                    INSERT INTO users (user_id, language)
                    VALUES (%s, %s)
                    ON CONFLICT (user_id) 
                    DO UPDATE SET language = EXCLUDED.language
                ''', (user_id, language))
                conn.commit()
                logger.info(f"Language preference saved for user {user_id}")
        except Exception as e:
            logger.error(f"Error saving user language: {e}")
            if conn:
                conn.rollback()
            raise
        finally:
            if conn:
                self.pool.putconn(conn)

    def get_user_language(self, user_id: int) -> str:
        """Get user's language preference"""
        conn = None
        try:
            conn = self.pool.getconn()
            with conn.cursor() as cur:
                cur.execute('SELECT language FROM users WHERE user_id = %s', (user_id,))
                result = cur.fetchone()
                return result[0] if result else 'en'
        except Exception as e:
            logger.error(f"Error getting user language: {e}")
            raise
        finally:
            if conn:
                self.pool.putconn(conn)

    def save_food_entry(self, user_id: int, calories: int):
        """Save food diary entry"""
        conn = None
        try:
            conn = self.pool.getconn()
            with conn.cursor() as cur:
                now = datetime.now()
                cur.execute('''
                    INSERT INTO food_diary (user_id, calories, date, time)
                    VALUES (%s, %s, %s, %s)
                ''', (user_id, calories, now.date(), now.time()))
                conn.commit()
                logger.info(f"Food entry saved for user {user_id}")
        except Exception as e:
            logger.error(f"Error saving food entry: {e}")
            if conn:
                conn.rollback()
            raise
        finally:
            if conn:
                self.pool.putconn(conn)

    def get_daily_summary(self, user_id: int) -> list:
        """Get user's food diary entries for current day"""
        conn = None
        try:
            conn = self.pool.getconn()
            with conn.cursor() as cur:
                cur.execute('''
                    SELECT calories, time 
                    FROM food_diary 
                    WHERE user_id = %s 
                    AND date = CURRENT_DATE 
                    ORDER BY time
                ''', (user_id,))
                return cur.fetchall()
        except Exception as e:
            logger.error(f"Error getting daily summary: {e}")
            raise
        finally:
            if conn:
                self.pool.putconn(conn)

    def get_all_daily_summaries(self) -> list:
        """Get all users' food diary entries for current day"""
        conn = None
        try:
            conn = self.pool.getconn()
            with conn.cursor() as cur:
                cur.execute('''
                    SELECT user_id, SUM(calories) as total_calories
                    FROM food_diary 
                    WHERE date = CURRENT_DATE 
                    GROUP BY user_id
                ''')
                return cur.fetchall()
        except Exception as e:
            logger.error(f"Error getting all daily summaries: {e}")
            raise
        finally:
            if conn:
                self.pool.putconn(conn)

    def close(self):
        """Close the connection pool"""
        try:
            if self.pool:
                self.pool.closeall()
                logger.info("Database connection pool closed")
        except Exception as e:
            logger.error(f"Error closing connection pool: {e}")
            raise

# Global database handler instance
db = None

def init_database():
    """Initialize global database handler"""
    global db
    try:
        db = DatabaseHandler()
        db.init_db()
        logger.info("Database initialized successfully")
        return db
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise