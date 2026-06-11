import sqlite3
import os
import csv
from datetime import datetime
from utils import user_data_path

class DatabaseHandler:
    """
    用于处理 SQLite 数据库操作的类。
    """
    def __init__(self, db_file='history.db', metric_keys=None):
        """
        初始化数据库处理器。
        
        Args:
            db_file (str): 数据库文件名。
            metric_keys (list): 健康数据指标的键列表（不含 created_at）。
        """
        self.db_file = user_data_path(db_file)
        self.metric_keys = metric_keys if metric_keys is not None else []
        self._init_db()

    def _init_db(self):
        """检查并初始化数据库和表。"""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            # 根据字段名确定类型：acdata 和 rra 使用 BLOB，其他使用 INTEGER
            column_defs = []
            for key in self.metric_keys:
                if key in ('acdata', 'rra'):
                    column_defs.append(f'"{key}" BLOB')
                else:
                    column_defs.append(f'"{key}" INTEGER')
            
            columns_sql = ", ".join(column_defs)
            if columns_sql:
                columns_sql = ", " + columns_sql
            
            create_table_sql = f"""
            CREATE TABLE IF NOT EXISTS health_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL{columns_sql}
            );
            """
            cursor.execute(create_table_sql)
            
            # 鼠标累计数据表：仅维护一行（id 固定为 1），保存最新累计值
            create_mouse_sql = """
            CREATE TABLE IF NOT EXISTS mouse_data (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                created_at TEXT NOT NULL,
                distance INTEGER NOT NULL DEFAULT 0,
                left_click INTEGER NOT NULL DEFAULT 0,
                mid_click INTEGER NOT NULL DEFAULT 0,
                right_click INTEGER NOT NULL DEFAULT 0,
                back_click INTEGER NOT NULL DEFAULT 0,
                forward_click INTEGER NOT NULL DEFAULT 0
            );
            """
            cursor.execute(create_mouse_sql)
            self._migrate_health_data(cursor)
            self._migrate_mouse_data(cursor)
            self._ensure_health_indexes(cursor)
            
            # 报告数据表
            create_reports_sql = """
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                report_json TEXT,
                images_data TEXT
            );
            """
            cursor.execute(create_reports_sql)

            conn.commit()
            conn.close()
            print(f"数据库 '{self.db_file}' 初始化成功。")
        except sqlite3.Error as e:
            print(f"数据库初始化失败: {e}")
            raise # 向上抛出异常，让主程序知道

    def load_last_record(self) -> dict | None:
        """从数据库读取并返回最后一条历史数据"""
        if not os.path.exists(self.db_file):
            print(f"未找到数据库文件 '{self.db_file}'。")
            return None
            
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            columns_to_select = ['created_at'] + self.metric_keys
            cursor.execute(f"SELECT {', '.join(columns_to_select)} FROM health_data ORDER BY id DESC LIMIT 1")
            last_row = cursor.fetchone()
            conn.close()
            
            if last_row:
                # 将结果打包成字典
                all_keys = ['created_at'] + self.metric_keys
                return dict(zip(all_keys, last_row))
            else:
                return None
                
        except sqlite3.Error as e:
            print(f"从数据库读取失败: {e}")
            return None

    def load_recent_averaged(self, count: int = 50) -> dict | None:
        """
        从数据库读取最近 count 条有效记录，计算去极值平均后返回。
        跳过 heartrate 或 spo2 为 0 的记录。
        
        Args:
            count: 最多读取的记录数，默认 50
        
        Returns:
            包含计算后健康指标的字典，或 None（无有效数据）
        """
        if not os.path.exists(self.db_file):
            print(f"未找到数据库文件 '{self.db_file}'。")
            return None
        
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            # 查询最近 count 条记录（只查询需要的字段）
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
            
            if not rows:
                print("数据库中无有效健康数据。")
                return None
            
            # 如果不足 count 条，返回全0结果
            if len(rows) < count:
                print(f"数据不足 {count} 条（当前 {len(rows)} 条），暂显示为0")
                return {
                    'created_at': rows[0][0] if rows else None,
                    'heartrate': 0, 'spo2': 0, 'bk': 0, 'fatigue': 0,
                    'systolic': 0, 'diastolic': 0, 'cardiac': 0, 'resistance': 0,
                    'rr_interval': 0, 'sdnn': 0, 'rmssd': 0, 'nn50': 0, 'pnn50': 0,
                    '_valid_count': len(rows)
                }
            
            # 统计器类
            class StatTracker:
                def __init__(self):
                    self.sum = 0
                    self.count = 0
                    self.min_val = float('inf')
                    self.max_val = 0
                
                def add(self, val):
                    if val == 0:
                        return
                    self.sum += val
                    self.count += 1
                    if val < self.min_val:
                        self.min_val = val
                    if val > self.max_val:
                        self.max_val = val
                
                def get_avg(self):
                    if self.count == 0:
                        return 0
                    if self.count <= 2:
                        return self.sum // self.count
                    return (self.sum - self.max_val - int(self.min_val)) // (self.count - 2)
            
            # 初始化统计器
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
            
            for row in rows:
                (created_at, heartrate, spo2, bk, fatigue, systolic, diastolic,
                 cardiac, resistance, rr_interval, sdnn, rmssd, nn50, pnn50) = row
                
                # 记录最新时间戳
                if max_timestamp is None:
                    max_timestamp = created_at
                
                valid_count += 1
                
                # 心率和血氧直接平均
                sum_heartrate += heartrate
                cnt_heartrate += 1
                sum_spo2 += spo2
                cnt_spo2 += 1
                
                # 其他指标使用去极值平均
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
            
            if valid_count == 0:
                print("无有效健康数据记录")
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
                '_valid_count': valid_count  # 附加信息
            }
            
            return result
            
        except sqlite3.Error as e:
            print(f"从数据库读取失败: {e}")
            return None

    def load_aggregated_for_analysis(self, interval_minutes: int = 10, max_records: int = 50) -> list:
        """
        从数据库读取健康数据，按时间间隔分组汇聚。
        用于 AI 分析，将秒级数据按时间段汇聚为更少的数据点。
        
        Args:
            interval_minutes: 汇聚时间间隔（分钟），默认 10 分钟
            max_records: 最多返回的汇聚记录数，默认 50
        
        Returns:
            汇聚后的记录列表，每条记录是一个字典
        """
        if not os.path.exists(self.db_file):
            print(f"未找到数据库文件 '{self.db_file}'。")
            return []
        
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            # 查询所有有效记录（按时间正序）
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
                print("数据库中无有效健康数据。")
                return []
            
            # 统计器类（与 load_recent_averaged 相同）
            class StatTracker:
                def __init__(self):
                    self.sum = 0
                    self.count = 0
                    self.min_val = float('inf')
                    self.max_val = 0
                
                def add(self, val):
                    if val == 0:
                        return
                    self.sum += val
                    self.count += 1
                    if val < self.min_val:
                        self.min_val = val
                    if val > self.max_val:
                        self.max_val = val
                
                def get_avg(self):
                    if self.count == 0:
                        return 0
                    if self.count <= 2:
                        return self.sum // self.count
                    return (self.sum - self.max_val - int(self.min_val)) // (self.count - 2)
            
            def aggregate_group(group_rows):
                """汇聚一组记录"""
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
                
                first_timestamp = group_rows[0][0]  # 使用组内第一条的时间
                
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
            
            # 按时间间隔分组
            interval_seconds = interval_minutes * 60
            groups = []
            current_group = []
            group_start_ts = None
            
            for row in rows:
                ts = row[14]  # timestamp 字段
                
                if group_start_ts is None:
                    group_start_ts = ts
                
                # 检查是否在当前时间段内
                if ts < group_start_ts + interval_seconds:
                    current_group.append(row)
                else:
                    # 保存当前组，开始新组
                    if current_group:
                        groups.append(current_group)
                    current_group = [row]
                    group_start_ts = ts
            
            # 别忘了最后一组
            if current_group:
                groups.append(current_group)
            
            # 汇聚每组数据
            aggregated_records = []
            for group in groups:
                record = aggregate_group(group)
                if record:
                    aggregated_records.append(record)
            
            # 只取最近的 max_records 条
            if len(aggregated_records) > max_records:
                aggregated_records = aggregated_records[-max_records:]

            #汇聚后的记录输出csv用于调试
            
            # debug_csv_path = "./tmp/aggregated_records_debug.csv"
            # with open(debug_csv_path, mode='w', newline='', encoding='utf-8') as csvfile:
            #     fieldnames = ['created_at', 'heartrate', 'spo2', 'bk', 'fatigue', 'systolic', 'diastolic',
            #                   'cardiac', 'resistance', 'rr_interval', 'sdnn', 'rmssd', 'nn50', 'pnn50']
            #     writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            #     writer.writeheader()
            #     for record in aggregated_records:
            #         writer.writerow(record)

            
            print(f"数据汇聚完成：{len(rows)} 条原始记录 -> {len(aggregated_records)} 条汇聚记录（每 {interval_minutes} 分钟）")
            return aggregated_records
            
        except sqlite3.Error as e:
            print(f"从数据库读取失败: {e}")
            return []

    def get_last_timestamp(self) -> int:
        """
        获取数据库中最后一条记录的 timestamp 字段值。
        
        Returns:
            最后一条记录的 timestamp，如果没有记录则返回 0
        """
        if not os.path.exists(self.db_file):
            return 0
        
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            cursor.execute("SELECT timestamp FROM health_data ORDER BY id DESC LIMIT 1")
            row = cursor.fetchone()
            conn.close()
            
            if row and row[0]:
                return row[0]
            return 0
            
        except sqlite3.Error as e:
            print(f"获取最后时间戳失败: {e}")
            return 0

    def get_last_record_id(self) -> int:
        """获取数据库中已保存的最大设备 record_id。"""
        if not os.path.exists(self.db_file):
            return 0

        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute("SELECT COALESCE(MAX(record_id), 0) FROM health_data")
            row = cursor.fetchone()
            conn.close()
            return int(row[0]) if row and row[0] else 0
        except sqlite3.Error as e:
            print(f"获取最后 record_id 失败: {e}")
            return 0

    def save_health_record(self, full_data: list) -> bool:
        """
        保存完整的 HealthDataRecord 到数据库。
        
        Args:
            full_data: 包含所有字段的列表，顺序与 metric_keys 对应：
                [acdata, hr, spo2, bk, fatigue, rsv1, rsv2,
                 systolic, diastolic, cardiac, resistance,
                 rr_interval, sdnn, rmssd, nn50, pnn50,
                 rra, rsv3, state, timestamp, record_id]
        """
        # 使用设备时间戳作为 created_at；设备无 RTC 时 timestamp 为 0，回退到 PC 当前时间
        ts_index = self.metric_keys.index('timestamp') if 'timestamp' in self.metric_keys else -1
        ts = full_data[ts_index] if ts_index >= 0 else 0
        try:
            created_at = datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S') if ts else datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        except (OSError, ValueError):
            created_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        columns = ['created_at'] + self.metric_keys
        placeholders = ', '.join(['?'] * len(columns))
        insert_sql = f"INSERT OR IGNORE INTO health_data ({', '.join(columns)}) VALUES ({placeholders})"
        
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            if 'record_id' in self.metric_keys:
                record_id_index = self.metric_keys.index('record_id')
                record_id = full_data[record_id_index]
                if record_id:
                    cursor.execute("SELECT 1 FROM health_data WHERE record_id = ? LIMIT 1", (record_id,))
                    if cursor.fetchone():
                        conn.close()
                        return False
            cursor.execute(insert_sql, [created_at] + full_data)
            conn.commit()
            conn.close()
            return True
        except sqlite3.Error as e:
            print(f"保存健康数据到数据库失败: {e}")
            return False

    # --- 鼠标数据相关 ---
    def _migrate_health_data(self, cursor: sqlite3.Cursor) -> None:
        """为历史 health_data 表补充新增字段。"""
        cursor.execute("PRAGMA table_info(health_data)")
        existing = {row[1] for row in cursor.fetchall()}
        if "record_id" not in existing:
            cursor.execute("ALTER TABLE health_data ADD COLUMN record_id INTEGER NOT NULL DEFAULT 0")

    def _ensure_health_indexes(self, cursor: sqlite3.Cursor) -> None:
        """创建设备记录 ID 的唯一索引，避免实时上报和历史同步重复入库。"""
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

    def _migrate_mouse_data(self, cursor: sqlite3.Cursor) -> None:
        """为历史 mouse_data 表补充新增的侧键统计列。"""
        cursor.execute("PRAGMA table_info(mouse_data)")
        existing = {row[1] for row in cursor.fetchall()}
        for column in ("back_click", "forward_click"):
            if column not in existing:
                cursor.execute(f"ALTER TABLE mouse_data ADD COLUMN {column} INTEGER NOT NULL DEFAULT 0")

    def save_or_update_mouse_data(
        self,
        distance: int,
        left_click: int,
        mid_click: int,
        right_click: int,
        back_click: int = 0,
        forward_click: int = 0
    ) -> None:
        """
        保存或更新鼠标累计数据（设备侧为累计值，这里只需同步最新值）。
        表设计为仅一行（id=1）。
        """
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO mouse_data (
                    id, created_at, distance, left_click, mid_click, right_click,
                    back_click, forward_click
                )
                VALUES (1, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    created_at=excluded.created_at,
                    distance=excluded.distance,
                    left_click=excluded.left_click,
                    mid_click=excluded.mid_click,
                    right_click=excluded.right_click,
                    back_click=excluded.back_click,
                    forward_click=excluded.forward_click
                """,
                [now, distance, left_click, mid_click, right_click, back_click, forward_click]
            )
            conn.commit()
            conn.close()
            print("鼠标累计数据已更新到数据库。")
        except sqlite3.Error as e:
            print(f"保存鼠标数据失败: {e}")

    def save_mouse_data(
        self,
        distance: int,
        left_click: int,
        mid_click: int,
        right_click: int,
        back_click: int = 0,
        forward_click: int = 0
    ) -> None:
        """兼容模块化 MouseDataProcessor 的保存接口。"""
        self.save_or_update_mouse_data(
            distance, left_click, mid_click, right_click, back_click, forward_click
        )

    def load_mouse_data(self) -> dict | None:
        """读取并返回保存的鼠标累计数据（单行）。"""
        if not os.path.exists(self.db_file):
            print(f"未找到数据库文件 '{self.db_file}'。")
            return None
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT created_at, distance, left_click, mid_click, right_click, back_click, forward_click
                FROM mouse_data WHERE id = 1
                """
            )
            row = cursor.fetchone()
            conn.close()
            if row:
                created_at, distance, left_click, mid_click, right_click, back_click, forward_click = row
                return {
                    'created_at': created_at,
                    'distance': distance,
                    'left_click': left_click,
                    'mid_click': mid_click,
                    'right_click': right_click,
                    'back_click': back_click,
                    'forward_click': forward_click,
                }
            return None
        except sqlite3.Error as e:
            print(f"读取鼠标数据失败: {e}")
            return None
