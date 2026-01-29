"""
数据库连接管理
"""
import sqlite3
import os
from utils import user_data_path

# 默认数据库文件名
DEFAULT_DB_FILE = 'history.db'


def get_db_path(db_file: str = DEFAULT_DB_FILE) -> str:
    """获取数据库文件完整路径"""
    return user_data_path(db_file)


def get_connection(db_file: str = DEFAULT_DB_FILE) -> sqlite3.Connection:
    """获取数据库连接"""
    return sqlite3.connect(get_db_path(db_file))


def init_database(db_file: str = DEFAULT_DB_FILE):
    """初始化数据库表结构"""
    db_path = get_db_path(db_file)
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 健康数据表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS health_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                acdata BLOB,
                heartrate INTEGER,
                spo2 INTEGER,
                bk INTEGER,
                fatigue INTEGER,
                rsv1 INTEGER,
                rsv2 INTEGER,
                systolic INTEGER,
                diastolic INTEGER,
                cardiac INTEGER,
                resistance INTEGER,
                rr_interval INTEGER,
                sdnn INTEGER,
                rmssd INTEGER,
                nn50 INTEGER,
                pnn50 INTEGER,
                rra BLOB,
                rsv3 INTEGER,
                state INTEGER,
                timestamp INTEGER
            )
        """)
        
        # 鼠标数据表（单行）
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS mouse_data (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                created_at TEXT NOT NULL,
                distance INTEGER NOT NULL DEFAULT 0,
                left_click INTEGER NOT NULL DEFAULT 0,
                mid_click INTEGER NOT NULL DEFAULT 0,
                right_click INTEGER NOT NULL DEFAULT 0
            )
        """)
        
        # 报告数据表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                report_json TEXT,
                images_data TEXT
            )
        """)
        
        conn.commit()
        conn.close()
        print(f"数据库 '{db_path}' 初始化成功。")
        return True
        
    except sqlite3.Error as e:
        print(f"数据库初始化失败: {e}")
        raise
