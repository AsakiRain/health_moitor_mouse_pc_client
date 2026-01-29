"""
鼠标数据仓库
"""
import sqlite3
import os
from datetime import datetime
from typing import Optional, Dict, Any

from .connection import get_db_path


class MouseRepository:
    """鼠标数据仓库"""
    
    def __init__(self, db_file: str = 'history.db'):
        self.db_path = get_db_path(db_file)
    
    def save(self, distance: int, left_click: int, mid_click: int, right_click: int) -> bool:
        """保存或更新鼠标数据（仅一行，id=1）"""
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO mouse_data (id, created_at, distance, left_click, mid_click, right_click)
                VALUES (1, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    created_at=excluded.created_at,
                    distance=excluded.distance,
                    left_click=excluded.left_click,
                    mid_click=excluded.mid_click,
                    right_click=excluded.right_click
            """, [now, distance, left_click, mid_click, right_click])
            conn.commit()
            conn.close()
            print("鼠标数据已更新")
            return True
        except sqlite3.Error as e:
            print(f"保存鼠标数据失败: {e}")
            return False
    
    def load(self) -> Optional[Dict[str, Any]]:
        """读取鼠标数据"""
        if not os.path.exists(self.db_path):
            return None
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT created_at, distance, left_click, mid_click, right_click
                FROM mouse_data WHERE id = 1
            """)
            row = cursor.fetchone()
            conn.close()
            
            if row:
                return {
                    'created_at': row[0],
                    'distance': row[1],
                    'left_click': row[2],
                    'mid_click': row[3],
                    'right_click': row[4],
                }
            return None
        except sqlite3.Error as e:
            print(f"读取鼠标数据失败: {e}")
            return None
