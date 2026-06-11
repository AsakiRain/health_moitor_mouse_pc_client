"""
数据同步 Mixin

提供启动时数据同步、批量数据处理、进度显示等功能。
"""
import struct
import sqlite3
from datetime import datetime

from PySide6.QtWidgets import QProgressDialog
from PySide6.QtCore import Qt, QTimer

import constants as const


class SyncMixin:
    """
    数据同步功能 Mixin
    
    需要宿主类提供：
    - self._log_to_ui(msg): 日志输出方法
    - self._send_with_ack_check(cmd, payload): 发送命令方法
    - self._on_device_response(): 更新设备连接状态
    - self._load_history_from_db(): 从数据库加载数据到界面
    - self.db_handler: DatabaseHandler 实例
    - self.serial_worker: SerialWorker 实例
    """
    
    def _init_sync(self):
        """初始化同步相关变量"""
        self._sync_in_progress = False
        self._sync_progress = None
        self._sync_total = 0
        self._sync_received = 0
        self._sync_db_conn = None
        self._sync_inserted = 0
        self._sync_max_record_id = 0
        self._sync_show_progress = False
        self._sync_signals_connected = False
        self.health_sync_timer = QTimer(self)
        self.health_sync_timer.setInterval(60 * 1000)
        self.health_sync_timer.timeout.connect(self._scheduled_sync_data)
    
    def start_health_sync_timer(self):
        """连接设备后启动历史健康数据定时同步。"""
        if not self.health_sync_timer.isActive():
            self.health_sync_timer.start()
        QTimer.singleShot(0, self._scheduled_sync_data)

    def stop_health_sync_timer(self):
        """断开设备后停止同步定时器并清理同步状态。"""
        if self.health_sync_timer.isActive():
            self.health_sync_timer.stop()
        self._sync_in_progress = False
        self._disconnect_sync_signals()
        if self._sync_db_conn:
            try:
                self._sync_db_conn.rollback()
                self._sync_db_conn.close()
            except Exception:
                pass
            self._sync_db_conn = None

    def _scheduled_sync_data(self):
        """定时静默同步。历史窗口打开时交给手动同步入口。"""
        if getattr(self, '_sync_in_progress', False):
            return
        if getattr(self, 'history_window_instance', None) is not None and self.history_window_instance.isVisible():
            return
        if not self.serial_worker or not self.serial_worker.serial_port or not self.serial_worker.serial_port.is_open:
            return
        self._startup_sync_data(show_progress=False)

    def _connect_sync_signals(self):
        if self._sync_signals_connected:
            return
        self.serial_worker.sync_start.connect(self._on_startup_sync_start)
        self.serial_worker.sync_batch.connect(self._on_startup_sync_batch)
        self.serial_worker.sync_end.connect(self._on_startup_sync_complete)
        self._sync_signals_connected = True

    def _disconnect_sync_signals(self):
        if not self._sync_signals_connected:
            return
        try:
            self.serial_worker.sync_start.disconnect(self._on_startup_sync_start)
            self.serial_worker.sync_batch.disconnect(self._on_startup_sync_batch)
            self.serial_worker.sync_end.disconnect(self._on_startup_sync_complete)
        except RuntimeError:
            pass
        self._sync_signals_connected = False

    def _startup_sync_data(self, show_progress: bool = False):
        """发起历史健康数据同步。"""
        if getattr(self, '_sync_in_progress', False):
            return
        self._sync_in_progress = True
        self._sync_progress = None
        self._sync_total = 0
        self._sync_received = 0
        self._sync_db_conn = None
        self._sync_inserted = 0
        self._sync_max_record_id = 0
        self._sync_show_progress = show_progress
        
        # 查找本地最后一条数据的 record_id
        last_record_id = self.db_handler.get_last_record_id()
        payload = struct.pack('<I', last_record_id)
        self._send_with_ack_check(const.CMD_SYNC_HEALTH_DATA, payload)
        self._log_to_ui(f"同步数据，Last Record ID: {last_record_id}")
        self._connect_sync_signals()
    
    def _on_startup_sync_start(self, total_count: int):
        """启动同步开始回调"""
        self._on_device_response()
        self._log_to_ui(f"开始同步，预计 {total_count} 条记录")
        
        self._sync_total = total_count
        self._sync_received = 0
        if self._sync_show_progress:
            self._sync_progress = QProgressDialog(
                "正在同步数据...", "取消",
                0, total_count if total_count > 0 else 100,
                self
            )
            self._sync_progress.setWindowTitle("数据同步")
            self._sync_progress.setWindowModality(Qt.WindowModal)
            self._sync_progress.setMinimumDuration(0)
            self._sync_progress.setMinimumWidth(400)
            self._sync_progress.setValue(0)
            self._sync_progress.setLabelText(f"准备同步 {total_count} 条记录...")
            self._sync_progress.show()
        
        # 开启数据库事务
        try:
            self._sync_db_conn = sqlite3.connect(self.db_handler.db_file)
            self._sync_db_conn.execute("PRAGMA synchronous = OFF")
            self._sync_db_conn.execute("BEGIN TRANSACTION")
        except Exception as e:
            self._log_to_ui(f"启动同步事务失败: {e}")
    
    def _on_startup_sync_batch(self, sent_count: int, data: bytes):
        """启动同步批量数据处理"""
        if not getattr(self, '_sync_in_progress', False):
            return
        
        if self._sync_db_conn is None:
            return
        
        if self._sync_progress is not None and self._sync_progress.wasCanceled():
            return
        
        record_size = 95
        if len(data) % record_size != 0:
            self._log_to_ui(f"警告: 批量数据长度 {len(data)} 不是 {record_size} 的倍数")
        
        num_records = len(data) // record_size
        cursor = self._sync_db_conn.cursor()
        
        for i in range(num_records):
            chunk = data[i*record_size : (i+1)*record_size]
            try:
                acdata = chunk[0:64]
                metrics = chunk[64:79]
                rra = chunk[79:85]
                rsv3 = chunk[85]
                state = chunk[86]
                ts = struct.unpack('<I', chunk[87:91])[0]
                record_id = struct.unpack('<I', chunk[91:95])[0]
                if record_id > self._sync_max_record_id:
                    self._sync_max_record_id = record_id
                
                hr, spo2, bk, fatigue, rsv1, rsv2, systolic, diastolic, cardiac, \
                resistance, rr_interval, sdnn, rmssd, nn50, pnn50 = struct.unpack('<15B', metrics)
                
                ts_str = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S") if ts else datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                cursor.execute("""
                    INSERT OR IGNORE INTO health_data (
                        created_at, acdata, heartrate, spo2, bk, fatigue,
                        rsv1, rsv2, systolic, diastolic, cardiac, resistance,
                        rr_interval, sdnn, rmssd, nn50, pnn50, rra, rsv3, state, timestamp, record_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (ts_str, acdata, hr, spo2, bk, fatigue, rsv1, rsv2,
                      systolic, diastolic, cardiac, resistance, rr_interval,
                      sdnn, rmssd, nn50, pnn50, rra, rsv3, state, ts, record_id))
                if cursor.rowcount > 0:
                    self._sync_inserted += 1
            except Exception as e:
                self._log_to_ui(f"解析/保存记录失败: {e}")
        
        # 更新进度条
        self._sync_received = sent_count
        try:
            if self._sync_progress is not None:
                self._sync_progress.setValue(sent_count)
                self._sync_progress.setLabelText(f"已同步 {sent_count}/{self._sync_total} 条记录...")
        except (AttributeError, RuntimeError):
            pass
    
    def _on_startup_sync_complete(self, total_received: int):
        """启动同步完成后的回调"""
        self._sync_in_progress = False
        
        # 关闭进度条
        if self._sync_progress is not None:
            self._sync_progress.setValue(self._sync_total)
            self._sync_progress.close()
            self._sync_progress = None
        
        self._disconnect_sync_signals()
        
        # 提交数据库事务
        if hasattr(self, '_sync_db_conn') and self._sync_db_conn:
            try:
                self._sync_db_conn.commit()
                self._sync_db_conn.close()
                self._log_to_ui(
                    f"同步数据已写入数据库：写入 {self._sync_inserted} 条，"
                    f"最大 Record ID={self._sync_max_record_id}"
                )
            except Exception as e:
                self._log_to_ui(f"提交数据库事务失败: {e}")
            self._sync_db_conn = None
        
        if total_received > 0:
            self._log_to_ui(f"同步完成，共接收 {total_received} 条记录")
        else:
            self._log_to_ui("同步完成，无新数据")
        
        # 从数据库加载并显示
        self._load_history_from_db()
