"""
健康数据仓库
"""
import sqlite3
import os
from datetime import datetime
from typing import List, Dict, Any, Optional

from .connection import get_db_path, get_connection
from core.health_data import HealthRecord, METRIC_KEYS, StatTracker


class HealthRepository:
    """健康数据仓库"""
    
    def __init__(self, db_file: str = 'history.db'):
        self.db_path = get_db_path(db_file)
    
    def save(self, record: HealthRecord) -> bool:
        """保存健康数据记录"""
        columns = ['created_at'] + METRIC_KEYS
        placeholders = ', '.join(['?'] * len(columns))
        insert_sql = f"INSERT INTO health_data ({', '.join(columns)}) VALUES ({placeholders})"
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(insert_sql, [record.created_at] + record.to_list())
            conn.commit()
            conn.close()
            print(f"健康数据已保存 (时间: {record.created_at})")
            return True
        except sqlite3.Error as e:
            print(f"保存健康数据失败: {e}")
            return False
    
    def save_from_list(self, full_data: list) -> bool:
        """从列表保存健康数据（兼容旧接口）"""
        ts = full_data[-1]
        try:
            created_at = datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
        except (OSError, ValueError):
            created_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        columns = ['created_at'] + METRIC_KEYS
        placeholders = ', '.join(['?'] * len(columns))
        insert_sql = f"INSERT INTO health_data ({', '.join(columns)}) VALUES ({placeholders})"
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(insert_sql, [created_at] + full_data)
            conn.commit()
            conn.close()
            print(f"健康数据已保存 (时间: {created_at})")
            return True
        except sqlite3.Error as e:
            print(f"保存健康数据失败: {e}")
            return False
    
    def get_last_timestamp(self) -> int:
        """获取最后一条记录的时间戳"""
        if not os.path.exists(self.db_path):
            return 0
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT timestamp FROM health_data ORDER BY id DESC LIMIT 1")
            row = cursor.fetchone()
            conn.close()
            return row[0] if row and row[0] else 0
        except sqlite3.Error as e:
            print(f"获取最后时间戳失败: {e}")
            return 0
    
    def get_recent(self, count: int = 50) -> List[Dict[str, Any]]:
        """获取最近的记录"""
        if not os.path.exists(self.db_path):
            return []
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(f"""
                SELECT created_at, heartrate, spo2, bk, fatigue, systolic, diastolic,
                       cardiac, resistance, rr_interval, sdnn, rmssd, nn50, pnn50
                FROM health_data 
                WHERE heartrate > 0 AND spo2 > 0
                ORDER BY id DESC 
                LIMIT ?
            """, (count,))
            rows = cursor.fetchall()
            conn.close()
            
            columns = ['created_at', 'heartrate', 'spo2', 'bk', 'fatigue', 'systolic', 
                      'diastolic', 'cardiac', 'resistance', 'rr_interval', 'sdnn', 
                      'rmssd', 'nn50', 'pnn50']
            return [dict(zip(columns, row)) for row in rows]
        except sqlite3.Error as e:
            print(f"获取最近记录失败: {e}")
            return []
    
    def load_recent_averaged(self, count: int = 50) -> Optional[Dict[str, Any]]:
        """获取最近记录的去极值平均"""
        records = self.get_recent(count)
        
        if not records:
            print("数据库中无有效健康数据。")
            return None
        
        if len(records) < count:
            print(f"数据不足 {count} 条（当前 {len(records)} 条），暂显示为0")
            return {
                'created_at': records[0]['created_at'] if records else None,
                'heartrate': 0, 'spo2': 0, 'bk': 0, 'fatigue': 0,
                'systolic': 0, 'diastolic': 0, 'cardiac': 0, 'resistance': 0,
                'rr_interval': 0, 'sdnn': 0, 'rmssd': 0, 'nn50': 0, 'pnn50': 0,
                '_valid_count': len(records)
            }
        
        # 计算去极值平均
        sum_heartrate, cnt_heartrate = 0, 0
        sum_spo2, cnt_spo2 = 0, 0
        st_bk = StatTracker()
        st_fatigue = StatTracker()
        st_systolic = StatTracker()
        st_diastolic = StatTracker()
        st_cardiac = StatTracker()
        st_resistance = StatTracker()
        st_rr_interval = StatTracker()
        st_sdnn = StatTracker()
        st_rmssd = StatTracker()
        st_nn50 = StatTracker()
        st_pnn50 = StatTracker()
        max_timestamp = None
        valid_count = 0
        
        for row in records:
            if max_timestamp is None:
                max_timestamp = row['created_at']
            
            valid_count += 1
            sum_heartrate += row['heartrate']
            cnt_heartrate += 1
            sum_spo2 += row['spo2']
            cnt_spo2 += 1
            
            st_bk.add(row['bk'])
            st_fatigue.add(row['fatigue'])
            st_systolic.add(row['systolic'])
            st_diastolic.add(row['diastolic'])
            st_cardiac.add(row['cardiac'])
            st_resistance.add(row['resistance'])
            st_rr_interval.add(row['rr_interval'])
            st_sdnn.add(row['sdnn'])
            st_rmssd.add(row['rmssd'])
            st_nn50.add(row['nn50'])
            st_pnn50.add(row['pnn50'])
        
        if valid_count == 0:
            return None
        
        result = {
            'created_at': max_timestamp,
            'heartrate': sum_heartrate // cnt_heartrate if cnt_heartrate else 0,
            'spo2': sum_spo2 // cnt_spo2 if cnt_spo2 else 0,
            'bk': st_bk.get_avg(),
            'fatigue': st_fatigue.get_avg(),
            'systolic': st_systolic.get_avg(),
            'diastolic': st_diastolic.get_avg(),
            'cardiac': st_cardiac.get_avg(),
            'resistance': st_resistance.get_avg(),
            'rr_interval': st_rr_interval.get_avg(),
            'sdnn': st_sdnn.get_avg(),
            'rmssd': st_rmssd.get_avg(),
            'nn50': st_nn50.get_avg(),
            'pnn50': st_pnn50.get_avg(),
            '_valid_count': valid_count
        }
        
        print(f"健康数据加载完成，有效记录 {valid_count} 条")
        return result
    
    def load_aggregated_for_analysis(self, interval_minutes: int = 10, max_records: int = 50) -> List[Dict]:
        """按时间间隔分组汇聚数据（用于 AI 分析）"""
        if not os.path.exists(self.db_path):
            return []
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT created_at, heartrate, spo2, bk, fatigue, systolic, diastolic,
                       cardiac, resistance, rr_interval, sdnn, rmssd, nn50, pnn50, timestamp
                FROM health_data 
                WHERE heartrate > 0 AND spo2 > 0
                ORDER BY timestamp ASC
            """)
            rows = cursor.fetchall()
            conn.close()
            
            if not rows:
                return []
            
            def aggregate_group(group_rows):
                if not group_rows:
                    return None
                
                sum_heartrate, cnt_heartrate = 0, 0
                sum_spo2, cnt_spo2 = 0, 0
                st_bk = StatTracker()
                st_fatigue = StatTracker()
                st_systolic = StatTracker()
                st_diastolic = StatTracker()
                st_cardiac = StatTracker()
                st_resistance = StatTracker()
                st_rr_interval = StatTracker()
                st_sdnn = StatTracker()
                st_rmssd = StatTracker()
                st_nn50 = StatTracker()
                st_pnn50 = StatTracker()
                
                first_timestamp = group_rows[0][0]
                
                for row in group_rows:
                    (created_at, heartrate, spo2, bk, fatigue, systolic, diastolic,
                     cardiac, resistance, rr_interval, sdnn, rmssd, nn50, pnn50, ts) = row
                    
                    sum_heartrate += heartrate
                    cnt_heartrate += 1
                    sum_spo2 += spo2
                    cnt_spo2 += 1
                    
                    st_bk.add(bk)
                    st_fatigue.add(fatigue)
                    st_systolic.add(systolic)
                    st_diastolic.add(diastolic)
                    st_cardiac.add(cardiac)
                    st_resistance.add(resistance)
                    st_rr_interval.add(rr_interval)
                    st_sdnn.add(sdnn)
                    st_rmssd.add(rmssd)
                    st_nn50.add(nn50)
                    st_pnn50.add(pnn50)
                
                return {
                    'created_at': first_timestamp,
                    'heartrate': sum_heartrate // cnt_heartrate if cnt_heartrate else 0,
                    'spo2': sum_spo2 // cnt_spo2 if cnt_spo2 else 0,
                    'bk': st_bk.get_avg(),
                    'fatigue': st_fatigue.get_avg(),
                    'systolic': st_systolic.get_avg(),
                    'diastolic': st_diastolic.get_avg(),
                    'cardiac': st_cardiac.get_avg(),
                    'resistance': st_resistance.get_avg(),
                    'rr_interval': st_rr_interval.get_avg(),
                    'sdnn': st_sdnn.get_avg(),
                    'rmssd': st_rmssd.get_avg(),
                    'nn50': st_nn50.get_avg(),
                    'pnn50': st_pnn50.get_avg()
                }
            
            interval_seconds = interval_minutes * 60
            groups = []
            current_group = []
            group_start_ts = None
            
            for row in rows:
                ts = row[14]
                if group_start_ts is None:
                    group_start_ts = ts
                
                if ts < group_start_ts + interval_seconds:
                    current_group.append(row)
                else:
                    if current_group:
                        groups.append(current_group)
                    current_group = [row]
                    group_start_ts = ts
            
            if current_group:
                groups.append(current_group)
            
            aggregated = []
            for group in groups:
                record = aggregate_group(group)
                if record:
                    aggregated.append(record)
            
            if len(aggregated) > max_records:
                aggregated = aggregated[-max_records:]
            
            print(f"数据汇聚完成：{len(rows)} 条 -> {len(aggregated)} 条（每 {interval_minutes} 分钟）")
            return aggregated
            
        except sqlite3.Error as e:
            print(f"汇聚数据失败: {e}")
            return []
