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

                # Create user_stats table
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS user_stats (
                        user_id BIGINT PRIMARY KEY,
                        first_use_date DATE NOT NULL,
                        last_donation_prompt DATE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
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

    def save_user_first_use(self, user_id):
        """Save user's first use date"""
        conn = None
        try:
            conn = self.pool.getconn()
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO user_stats (user_id, first_use_date)
                    VALUES (%s, CURRENT_DATE)
                    ON CONFLICT (user_id) DO NOTHING
                """, (user_id,))
                conn.commit()
                logger.info(f"First use date saved for user {user_id}")
        except Exception as e:
            logger.error(f"Error saving first use date: {e}")
            if conn:
                conn.rollback()
            raise
        finally:
            if conn:
                self.pool.putconn(conn)

    def get_user_first_use(self, user_id):
        """Get user's first use date"""
        conn = None
        try:
            conn = self.pool.getconn()
            with conn.cursor() as cur:
                cur.execute("SELECT first_use_date FROM user_stats WHERE user_id = %s", (user_id,))
                result = cur.fetchone()
                return result[0] if result else None
        except Exception as e:
            logger.error(f"Error getting first use date: {e}")
            raise
        finally:
            if conn:
                self.pool.putconn(conn)

    def update_last_donation_prompt(self, user_id):
        """Update user's last donation prompt date"""
        conn = None
        try:
            conn = self.pool.getconn()
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE user_stats 
                    SET last_donation_prompt = CURRENT_DATE
                    WHERE user_id = %s
                """, (user_id,))
                conn.commit()
                logger.info(f"Last donation prompt updated for user {user_id}")
        except Exception as e:
            logger.error(f"Error updating last donation prompt: {e}")
            if conn:
                conn.rollback()
            raise
        finally:
            if conn:
                self.pool.putconn(conn)

    def get_last_donation_prompt(self, user_id):
        """Get user's last donation prompt date"""
        conn = None
        try:
            conn = self.pool.getconn()
            with conn.cursor() as cur:
                cur.execute("SELECT last_donation_prompt FROM user_stats WHERE user_id = %s", (user_id,))
                result = cur.fetchone()
                return result[0] if result else None
        except Exception as e:
            logger.error(f"Error getting last donation prompt: {e}")
            raise
        finally:
            if conn:
                self.pool.putconn(conn)

    def should_show_donation_prompt(self, user_id):
        """Check if donation prompt should be shown to user"""
        try:
            first_use = self.get_user_first_use(user_id)
            if not first_use:
                return False

            days_since_first_use = (datetime.now().date() - first_use).days

            if days_since_first_use == 1:
                return True
            elif days_since_first_use > 7:
                last_prompt = self.get_last_donation_prompt(user_id)
                if not last_prompt or (datetime.now().date() - last_prompt).days >= 7:
                    return True
            return False
        except Exception as e:
            logger.error(f"Error checking donation prompt status: {e}")
            return False

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