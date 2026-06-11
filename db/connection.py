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
                timestamp INTEGER,
                record_id INTEGER NOT NULL DEFAULT 0
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
                right_click INTEGER NOT NULL DEFAULT 0,
                back_click INTEGER NOT NULL DEFAULT 0,
                forward_click INTEGER NOT NULL DEFAULT 0
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
        
        # 迁移：补充 health_data 表中可能缺失的列
        _migrate_health_data(cursor)
        _ensure_health_indexes(cursor)
        _migrate_mouse_data(cursor)

        conn.commit()
        conn.close()
        print(f"数据库 '{db_path}' 初始化成功。")
        return True
        
    except sqlite3.Error as e:
        print(f"数据库初始化失败: {e}")
        raise


def _migrate_health_data(cursor: sqlite3.Cursor):
    """为 health_data 表补充历史版本中缺失的列"""
    # 获取当前列名
    cursor.execute("PRAGMA table_info(health_data)")
    existing = {row[1] for row in cursor.fetchall()}

    # 需要确保存在的列：(列名, 类型, 默认值)
    required_columns = [
        ('acdata',      'BLOB',    'NULL'),
        ('rsv1',        'INTEGER', '0'),
        ('rsv2',        'INTEGER', '0'),
        ('rra',         'BLOB',    'NULL'),
        ('rsv3',        'INTEGER', '0'),
        ('state',       'INTEGER', '0'),
        ('timestamp',   'INTEGER', '0'),
        ('record_id',   'INTEGER', '0'),
    ]

    for col_name, col_type, default in required_columns:
        if col_name not in existing:
            cursor.execute(
                f"ALTER TABLE health_data ADD COLUMN {col_name} {col_type} DEFAULT {default}"
            )
            print(f"数据库迁移: health_data 表新增列 '{col_name}'")


def _migrate_mouse_data(cursor: sqlite3.Cursor):
    """为 mouse_data 表补充历史版本中缺失的侧键统计列"""
    cursor.execute("PRAGMA table_info(mouse_data)")
    existing = {row[1] for row in cursor.fetchall()}

    for col_name in ("back_click", "forward_click"):
        if col_name not in existing:
            cursor.execute(
                f"ALTER TABLE mouse_data ADD COLUMN {col_name} INTEGER NOT NULL DEFAULT 0"
            )
            print(f"数据库迁移: mouse_data 表新增列 '{col_name}'")


def _ensure_health_indexes(cursor: sqlite3.Cursor):
    """为设备 record_id 建唯一索引，避免同步重复写入。"""
    cursor.execute("""
        DELETE FROM health_data
        WHERE record_id > 0
          AND id NOT IN (
              SELECT MIN(id)
              FROM health_data
              WHERE record_id > 0
              GROUP BY record_id
          )
    """)
    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_health_data_record_id
        ON health_data(record_id)
        WHERE record_id > 0
    """)
