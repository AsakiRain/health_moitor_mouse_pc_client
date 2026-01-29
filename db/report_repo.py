"""
报告数据仓库
"""
import sqlite3
import os
import json
from datetime import datetime
from typing import List, Dict, Any, Optional

from .connection import get_db_path


class ReportRepository:
    """报告数据仓库"""
    
    def __init__(self, db_file: str = 'history.db'):
        self.db_path = get_db_path(db_file)
    
    def save(self, report_json: dict, images_data: dict) -> int:
        """
        保存报告
        
        Returns:
            新报告的 ID，失败返回 -1
        """
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        report_json_str = json.dumps(report_json, ensure_ascii=False)
        images_data_str = json.dumps(images_data)
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO reports (created_at, report_json, images_data) VALUES (?, ?, ?)",
                (now, report_json_str, images_data_str)
            )
            report_id = cursor.lastrowid
            conn.commit()
            conn.close()
            print(f"报告已保存，ID: {report_id}")
            return report_id
        except sqlite3.Error as e:
            print(f"保存报告失败: {e}")
            return -1
    
    def get_all(self) -> List[Dict[str, Any]]:
        """获取所有报告（摘要）"""
        if not os.path.exists(self.db_path):
            return []
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT id, created_at, report_json FROM reports ORDER BY id DESC")
            rows = cursor.fetchall()
            conn.close()
            
            reports = []
            for row in rows:
                report = {
                    'id': row[0],
                    'created_at': row[1],
                    'is_error': False
                }
                # 检查是否有错误
                try:
                    data = json.loads(row[2])
                    if data.get('health_evaluation', {}).get('rating') == '配置错误':
                        report['is_error'] = True
                except:
                    pass
                reports.append(report)
            
            return reports
        except sqlite3.Error as e:
            print(f"获取报告列表失败: {e}")
            return []
    
    def get_by_id(self, report_id: int) -> Optional[Dict[str, Any]]:
        """根据 ID 获取报告详情"""
        if not os.path.exists(self.db_path):
            return None
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM reports WHERE id = ?", (report_id,))
            column_names = [desc[0] for desc in cursor.description]
            row = cursor.fetchone()
            conn.close()
            
            if row:
                return dict(zip(column_names, row))
            return None
        except sqlite3.Error as e:
            print(f"获取报告详情失败: {e}")
            return None
    
    def delete(self, report_id: int) -> bool:
        """删除报告"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM reports WHERE id = ?", (report_id,))
            conn.commit()
            conn.close()
            print(f"报告已删除，ID: {report_id}")
            return True
        except sqlite3.Error as e:
            print(f"删除报告失败: {e}")
            return False
    
    def get_last_report_time(self) -> Optional[str]:
        """获取最新报告的时间"""
        if not os.path.exists(self.db_path):
            return None
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT MAX(created_at) FROM reports")
            row = cursor.fetchone()
            conn.close()
            return row[0] if row else None
        except sqlite3.Error as e:
            print(f"获取最新报告时间失败: {e}")
            return None
    
    def get_last_data_time(self) -> Optional[str]:
        """获取最新健康数据的时间"""
        if not os.path.exists(self.db_path):
            return None
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT MAX(created_at) FROM health_data")
            row = cursor.fetchone()
            conn.close()
            return row[0] if row else None
        except sqlite3.Error as e:
            print(f"获取最新数据时间失败: {e}")
            return None
