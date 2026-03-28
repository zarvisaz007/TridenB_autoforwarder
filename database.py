import sqlite3
import os
import time
from dotenv import load_dotenv

load_dotenv()

class DatabaseHandler:
    def __init__(self, db_path="autoforwarder.db"):
        self.db_path = db_path
        self._init_sqlite()

    def _init_sqlite(self):
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.cursor = self.conn.cursor()
        
        # Create Tables
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER,
                source_channel_id INTEGER,
                source_message_id INTEGER,
                dest_channel_id INTEGER,
                dest_message_id INTEGER,
                has_image BOOLEAN DEFAULT 0,
                text_content TEXT,
                timestamp INTEGER,
                reply_to_dest_id INTEGER
            )
        ''')
        
        try:
            self.cursor.execute('ALTER TABLE messages ADD COLUMN reply_to_dest_id INTEGER')
        except sqlite3.OperationalError:
            pass

        
        self.cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_src 
            ON messages(source_channel_id, source_message_id)
        ''')
        self.cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_src_msg_only 
            ON messages(source_message_id)
        ''')
        
        self.conn.commit()

    def log_message(self, task_id, source_channel_id, source_message_id, dest_channel_id, dest_message_id, 
                    has_image=False, text_content="", reply_to_dest_id=None):
        timestamp = int(time.time())
        self.cursor.execute('''
            INSERT INTO messages (
                task_id, source_channel_id, source_message_id, dest_channel_id, dest_message_id, 
                has_image, text_content, timestamp, reply_to_dest_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (task_id, source_channel_id, source_message_id, dest_channel_id, dest_message_id, 
              int(has_image), text_content, timestamp, reply_to_dest_id))
        self.conn.commit()
        db_id = self.cursor.lastrowid
        return db_id

    def get_dest_messages(self, source_channel_id, source_message_id):
        self.cursor.execute('''
            SELECT task_id, dest_channel_id, dest_message_id FROM messages 
            WHERE source_channel_id = ? AND source_message_id = ?
        ''', (source_channel_id, source_message_id))
        return [dict(row) for row in self.cursor.fetchall()]

    def get_dest_messages_by_msg_id(self, source_message_id):
        """Used as a fallback when source_channel_id is unknown during deletion."""
        self.cursor.execute('''
            SELECT task_id, dest_channel_id, dest_message_id FROM messages 
            WHERE source_message_id = ?
        ''', (source_message_id,))
        return [dict(row) for row in self.cursor.fetchall()]

    def get_reply_to_dest_id(self, task_id, source_channel_id, reply_to_src_id, dest_channel_id):
        self.cursor.execute('''
            SELECT dest_message_id FROM messages 
            WHERE task_id = ? AND source_channel_id = ? AND source_message_id = ? AND dest_channel_id = ?
            ORDER BY timestamp DESC LIMIT 1
        ''', (task_id, source_channel_id, reply_to_src_id, dest_channel_id))
        row = self.cursor.fetchone()
        if row:
            return row['dest_message_id']
        return None

    def remove_messages(self, source_channel_id, source_message_id):
        """Returns the list of matching rows before removing them."""
        if source_channel_id:
            rows = self.get_dest_messages(source_channel_id, source_message_id)
            self.cursor.execute('''
                DELETE FROM messages 
                WHERE source_channel_id = ? AND source_message_id = ?
            ''', (source_channel_id, source_message_id))
        else:
            rows = self.get_dest_messages_by_msg_id(source_message_id)
            self.cursor.execute('''
                DELETE FROM messages 
                WHERE source_message_id = ?
            ''', (source_message_id,))
            
        self.conn.commit()
        return rows

    def get_old_image_messages(self, task_id, age_seconds):
        cutoff_time = int(time.time()) - age_seconds
        self.cursor.execute('''
            SELECT dest_channel_id, dest_message_id FROM messages 
            WHERE task_id = ? AND has_image = 1 AND timestamp < ?
        ''', (task_id, cutoff_time))
        return [dict(row) for row in self.cursor.fetchall()]

    def delete_message_record(self, dest_channel_id, dest_message_id):
        self.cursor.execute('''
            DELETE FROM messages 
            WHERE dest_channel_id = ? AND dest_message_id = ?
        ''', (dest_channel_id, dest_message_id))
        self.conn.commit()

    def get_statistics(self):
        self.cursor.execute('''
            SELECT task_id, count(id) as total_messages, sum(has_image) as total_images, max(timestamp) as last_active
            FROM messages
            GROUP BY task_id
        ''')
        return [dict(row) for row in self.cursor.fetchall()]

    def get_threads(self, limit=50):
        self.cursor.execute('''
            SELECT a.task_id, a.dest_channel_id, a.dest_message_id, a.text_content, a.timestamp as parent_time,
                   COUNT(b.id) as reply_count,
                   MAX(b.timestamp) as latest_reply_time
            FROM messages a
            JOIN messages b ON a.dest_message_id = b.reply_to_dest_id AND a.dest_channel_id = b.dest_channel_id
            GROUP BY a.id
            ORDER BY parent_time DESC
            LIMIT ?
        ''', (limit,))
        return [dict(row) for row in self.cursor.fetchall()]

    def close(self):
        self.conn.close()

db = DatabaseHandler()
