"""
CyMouse Monitor 主窗口

使用 Mixin 模式组织功能模块：
- TrayMixin: 系统托盘
- StatusBarMixin: 状态栏
- HealthCheckMixin: 健康检测流程
- SyncMixin: 数据同步
"""
import struct
from datetime import datetime

from PySide6.QtWidgets import (
    QMainWindow, QPushButton, QLabel, QTextEdit, QApplication
)
from PySide6.QtCore import Qt, QTimer, QFile, QThread
from PySide6.QtUiTools import QUiLoader

# 业务模块
from serial_comm.worker import SerialWorker
from config_handler import ConfigHandler
from database_handler import DatabaseHandler
from device_log_window import DeviceLogWindow
from history_window import HistoryWindow
from mouse_handler import MouseDataProcessor
from utils import resource_path
import constants as const

# UI Mixins
from ui import TrayMixin, StatusBarMixin, HealthCheckMixin, SyncMixin


# 全局配置
LOGGING_ENABLED = True
TIME_SYNC_INTERVAL = 10  # 时间同步间隔（分钟）


class MainWindow(TrayMixin, StatusBarMixin, HealthCheckMixin, SyncMixin, QMainWindow):
    """
    主窗口类
    
    继承多个 Mixin 实现功能模块化：
    - TrayMixin: 托盘图标、闪烁、托盘菜单
    - StatusBarMixin: 状态栏、连接状态、ACK 超时
    - HealthCheckMixin: 健康检测流程、倒计时
    - SyncMixin: 数据同步、进度显示
    """
    
    def __init__(self):
        super().__init__()
        
        # === 加载 UI ===
        self._load_ui(resource_path("main.ui"))
        self.setFixedSize(self.size())
        self._center_window()
        self.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose, True)
        self.setWindowFlags(Qt.WindowMinimizeButtonHint | Qt.WindowCloseButtonHint)
        
        # === 初始化业务组件 ===
        self.config_handler = ConfigHandler()
        self.metric_keys = self._get_metric_keys()
        self.db_handler = DatabaseHandler(metric_keys=self.metric_keys)
        self.mouse_processor = MouseDataProcessor(self.db_handler)
        self.history_window_instance = None
        self.device_log_window_instance = None
        
        # === 初始化 Mixins ===
        self._init_tray()
        self._init_status_bar()
        self._init_health_check()
        self._init_sync()
        
        # === 绑定 UI 控件 ===
        self._bind_ui_controls()
        
        # === 初始化串口 ===
        self._init_serial()
        
        # === 时间同步定时器 ===
        self.time_sync_timer = QTimer(self)
        self.time_sync_timer.timeout.connect(self._on_time_sync)
        
        # === 启动序列 ===
        self.startup_sequence()
    
    # ========================
    #  UI 初始化
    # ========================
    
    def _get_metric_keys(self) -> list:
        """获取 HealthData 字段列表"""
        return [
            'acdata',       # 64字节 BLOB
            'heartrate', 'spo2', 'bk', 'fatigue',
            'rsv1', 'rsv2',
            'systolic', 'diastolic', 'cardiac', 'resistance',
            'rr_interval', 'sdnn', 'rmssd', 'nn50', 'pnn50',
            'rra',          # 6字节 BLOB
            'rsv3', 'state',
            'timestamp'
        ]
    
    def _bind_ui_controls(self):
        """绑定 UI 控件和事件"""
        # 开始按钮
        self.start_button = self.findChild(QPushButton, "btn_start")
        if self.start_button:
            self.start_button.clicked.connect(self.on_start_button_clicked)
        
        # 历史数据按钮
        self.history_button = self.findChild(QPushButton, "btn_history")
        if self.history_button:
            self.history_button.clicked.connect(self.show_history_window)

        self.device_log_button = self.findChild(QPushButton, "btn_device_log")
        if self.device_log_button:
            self.device_log_button.clicked.connect(self.show_device_log_window)
        
        # 刷新鼠标数据按钮
        self.mousedata_button = self.findChild(QPushButton, "btn_mousedata")
        if self.mousedata_button:
            self.mousedata_button.clicked.connect(self.on_mousedata_button_clicked)
        
        # 健康数据标签
        ui_label_names = {
            'heartrate': 'label_hr_value', 'spo2': 'label_spo2_value',
            'bk': 'label_mc_value', 'fatigue': 'label_fi_value',
            'systolic': 'label_sbp_value', 'diastolic': 'label_dbp_value',
            'cardiac': 'label_co_value', 'resistance': 'label_pr_value'
        }
        
        self.value_labels = {}
        for key, name in ui_label_names.items():
            label = self.findChild(QLabel, name)
            if label:
                self.value_labels[key] = label
                if key in const.HEALTH_METRICS_TOOLTIPS:
                    label.setToolTip(const.HEALTH_METRICS_TOOLTIPS[key])
        
        # 鼠标数据标签
        self.label_distance = self.findChild(QLabel, "label_distance")
        self.label_leftclick = self.findChild(QLabel, "label_leftclick")
        self.label_midclick = self.findChild(QLabel, "label_midclick")
        self.label_rightclick = self.findChild(QLabel, "label_rightclick")
        
        # 日志输出
        self.log_output = self.findChild(QTextEdit, "log_output")
        if self.log_output:
            self.log_output.setReadOnly(True)
    
    def _load_ui(self, ui_path: str):
        """加载 UI 文件"""
        loader = QUiLoader()
        ui_file = QFile(ui_path)
        if not ui_file.exists():
            raise FileNotFoundError(f"UI 文件未找到: {ui_path}")
        if not ui_file.open(QFile.ReadOnly):
            raise IOError(f"无法打开 UI 文件: {ui_path}")
        
        loaded = loader.load(ui_file)
        ui_file.close()
        
        if loaded is None:
            raise RuntimeError(f"加载 UI 失败: {ui_path}")
        
        # 提取样式表并应用到全局
        app_style = loaded.styleSheet()
        if app_style:
            QApplication.instance().setStyleSheet(app_style)
            loaded.setStyleSheet("")
        
        if isinstance(loaded, QMainWindow):
            self.setCentralWidget(loaded.takeCentralWidget())
            self.setWindowTitle(loaded.windowTitle())
            self.resize(loaded.size())
            loaded.deleteLater()
        else:
            self.setWindowTitle(loaded.windowTitle())
            self.resize(loaded.size())
            self.setCentralWidget(loaded)
    
    def _center_window(self):
        """窗口居中"""
        screen = QApplication.primaryScreen()
        if screen:
            rect = screen.availableGeometry()
            x = (rect.width() - self.width()) // 2
            y = (rect.height() - self.height()) // 2
            self.move(x, y)
    
    # ========================
    #  串口初始化
    # ========================
    
    def _init_serial(self):
        """初始化串口工作线程"""
        self.serial_thread = QThread()
        self.serial_worker = SerialWorker()
        self.serial_worker.moveToThread(self.serial_thread)
        
        # 连接信号
        self.serial_worker.error_occurred.connect(self._show_error)
        self.serial_worker.log_message.connect(self._log_to_ui)
        self.serial_worker.ack_received.connect(self.on_ack_received)
        self.serial_worker.health_data_received.connect(self.on_health_data_received)
        self.serial_worker.mouse_data_received.connect(self.on_mouse_data_received)
        self.serial_worker.device_log_received.connect(self.on_device_log_received)
        self.serial_worker.connected.connect(self._update_status_connected)
        self.serial_worker.disconnected.connect(self._update_status_disconnected)
        
        self.serial_thread.started.connect(self.serial_worker.run)
    
    # ========================
    #  启动流程
    # ========================
    
    def startup_sequence(self):
        """应用启动时的操作序列"""
        self._log_to_ui("应用启动... 优先从设备获取最新数据。")
        
        try:
            com_port = self.config_handler.get_com_port()
            self.serial_worker.connect_serial(com_port)
            
            if self.serial_worker.is_running and not self.serial_thread.isRunning():
                self.serial_thread.start()
            
            # 时间同步
            QTimer.singleShot(50, self._on_time_sync)
            self.time_sync_timer.setInterval(TIME_SYNC_INTERVAL * 60 * 1000)
            self.time_sync_timer.start()
            self._log_to_ui(f"已启动时间同步定时器，间隔 {TIME_SYNC_INTERVAL} 分钟。")
            
            # 数据同步
            QTimer.singleShot(100, self._startup_sync_data)
            
            # 获取鼠标数据
            QTimer.singleShot(150, lambda: self._send_with_ack_check(const.CMD_GET_MOUSE_DATA))
            
        except Exception as e:
            self._log_to_ui(f"启动时连接串口失败: {e}。尝试从本地文件加载...")
            self._load_history_from_db()
            self._load_mouse_from_db()
    
    # ========================
    #  数据加载
    # ========================
    
    def _load_history_from_db(self):
        """从数据库加载健康数据"""
        avg_record = self.db_handler.load_recent_averaged(50)
        if avg_record:
            timestamp = avg_record.pop('created_at')
            valid_count = avg_record.pop('_valid_count', 0)
            self._log_to_ui(f"从数据库加载健康数据（{valid_count}条平均, 最新: {timestamp}）")
            self._update_data_labels(avg_record)
        else:
            self._log_to_ui("数据库中无历史数据。")
    
    def _load_mouse_from_db(self):
        """从数据库加载鼠标数据"""
        mouse = self.db_handler.load_mouse_data()
        if mouse:
            distance_m = None
            try:
                distance_m = self.mouse_processor.distance_to_meters_str(mouse['distance'])
            except Exception:
                pass
            
            self._log_to_ui(
                f"从数据库加载鼠标数据 ({mouse['created_at']}): "
                f"距离={distance_m or str(mouse['distance'])+'μm'}, "
                f"L={mouse['left_click']}, M={mouse['mid_click']}, R={mouse['right_click']}"
            )
            self._update_mouse_labels(
                mouse['distance'], mouse['left_click'],
                mouse['mid_click'], mouse['right_click']
            )
        else:
            self._log_to_ui("数据库中无鼠标数据。")
    
    # ========================
    #  事件处理
    # ========================
    
    def on_mousedata_button_clicked(self):
        """刷新鼠标数据"""
        self._log_to_ui("刷新鼠标数据...")
        try:
            com_port = self.config_handler.get_com_port()
            if not self.serial_worker.serial_port or not self.serial_worker.serial_port.is_open:
                self.serial_worker.connect_serial(com_port)
                if self.serial_worker.is_running and not self.serial_thread.isRunning():
                    self.serial_thread.start()
            self._send_with_ack_check(const.CMD_GET_MOUSE_DATA)
        except Exception as e:
            self._show_error(f"刷新鼠标数据失败: {e}")
    
    def on_ack_received(self, original_cmd: int, status_code: int):
        """处理 ACK 响应"""
        self._on_device_response()
        self._log_to_ui(f"收到 ACK: 原始命令={hex(original_cmd)}, 状态码={status_code}")
        
        if original_cmd == const.CMD_START_HEALTH_CHECK:
            if status_code == const.ACK_SUCCESS:
                self._log_to_ui("设备已确认开始健康监测。等待数据...")
                duration = getattr(self, 'health_check_duration', 100)
                self._start_countdown(duration)
            elif status_code == const.ACK_DEVICE_BUSY:
                self._log_to_ui("设备正忙，请稍后再试。")
                self._reset_detection_state()
            elif status_code == const.ACK_UNKNOWN_CMD:
                self._log_to_ui("设备无法识别开始命令，请检查固件版本。")
                self._reset_detection_state()
            else:
                self._log_to_ui(f"设备返回未知状态码 {status_code}，操作失败。")
                self._reset_detection_state()
    
    def on_health_data_received(self, data: bytes):
        """处理健康数据"""
        self._log_to_ui(f"收到健康数据: {data.hex(' ').upper()}")
        
        if len(data) != 91:
            self._log_to_ui(f"警告: 健康数据长度不正确 (应为 91, 收到 {len(data)})")
            return
        
        try:
            acdata = data[0:64]
            metrics = data[64:79]
            rra = data[79:85]
            rsv3 = data[85]
            state = data[86]
            ts = struct.unpack('<I', data[87:91])[0]
            
            hr, spo2, bk, fatigue, rsv1, rsv2, systolic, diastolic, cardiac, \
            resistance, rr_interval, sdnn, rmssd, nn50, pnn50 = struct.unpack('<15B', metrics)
            
            full_data = [
                acdata, hr, spo2, bk, fatigue, rsv1, rsv2,
                systolic, diastolic, cardiac, resistance,
                rr_interval, sdnn, rmssd, nn50, pnn50,
                rra, rsv3, state, ts
            ]
            
            self.db_handler.save_health_record(full_data)
            self._load_history_from_db()
            
            if self.detection_timeout_timer.isActive():
                self.detection_timeout_timer.stop()
            
            if not self.countdown_timer.isActive():
                self._stop_blinking()
                self._reset_detection_state()
                
        except struct.error as e:
            self._log_to_ui(f"解析健康数据失败: {e}")
    
    def on_mouse_data_received(self, payload: bytes):
        """处理鼠标数据"""
        try:
            result = self.mouse_processor.process_payload(payload)
            self._log_to_ui(
                f"收到鼠标数据: 距离={result['distance_m_str']}, "
                f"L={result['left_click']}, M={result['mid_click']}, R={result['right_click']}, "
                f"会话时间={result['session_time_str']}"
            )
            self._update_mouse_labels(
                result['distance_um'],
                result['left_click'],
                result['mid_click'],
                result['right_click']
            )
        except Exception as e:
            self._log_to_ui(f"解析鼠标数据失败: {e}")

    def on_device_log_received(self, message: str):
        """处理设备推送日志"""
        if self.device_log_window_instance is None:
            self.device_log_window_instance = DeviceLogWindow(self)
        self.device_log_window_instance.append_log(message)
    
    def show_history_window(self):
        """显示历史数据窗口"""
        if self.history_window_instance is None or not self.history_window_instance.isVisible():
            if self.history_window_instance is not None:
                try:
                    self.history_window_instance.request_sync.disconnect(self.send_sync_command)
                    self.serial_worker.sync_start.disconnect(self.history_window_instance.on_sync_start)
                    self.serial_worker.sync_batch.disconnect(self.history_window_instance.on_sync_batch)
                    self.serial_worker.sync_end.disconnect(self.history_window_instance.on_sync_end)
                except (TypeError, RuntimeError):
                    pass
            
            self.history_window_instance = HistoryWindow(
                db_path=self.db_handler.db_file,
                parent=self
            )
            self.history_window_instance.request_sync.connect(self.send_sync_command)
            self.serial_worker.sync_start.connect(self.history_window_instance.on_sync_start)
            self.serial_worker.sync_batch.connect(self.history_window_instance.on_sync_batch)
            self.serial_worker.sync_end.connect(self.history_window_instance.on_sync_end)
        
        self.history_window_instance.show()
        self.history_window_instance.activateWindow()

    def show_device_log_window(self):
        """显示设备日志窗口"""
        if self.device_log_window_instance is None:
            self.device_log_window_instance = DeviceLogWindow(self)
        self.device_log_window_instance.show()
        self.device_log_window_instance.activateWindow()
    
    def send_sync_command(self, timestamp: int):
        """发送同步命令"""
        payload = struct.pack('<I', timestamp)
        self._send_with_ack_check(const.CMD_SYNC_HEALTH_DATA, payload)
        self._log_to_ui(f"已请求同步数据，Last Timestamp: {timestamp}")
    
    # ========================
    #  UI 更新
    # ========================
    
    def _update_data_labels(self, data_dict: dict):
        """更新健康数据标签"""
        for key, value in data_dict.items():
            if key in self.value_labels:
                display_value = value
                if key == 'cardiac':
                    try:
                        display_value = f"{float(value) / 10.0:.1f}"
                    except (ValueError, TypeError):
                        display_value = str(value)
                self.value_labels[key].setText(str(display_value))
        self._log_to_ui("界面数据已更新。")
    
    def _update_mouse_labels(self, distance_um: int, left: int, mid: int, right: int):
        """更新鼠标数据标签"""
        if self.label_distance:
            try:
                meters_text = self.mouse_processor.distance_to_meters_str(distance_um)
                self.label_distance.setText(meters_text or str(distance_um))
            except Exception:
                self.label_distance.setText(str(distance_um))
        
        if self.label_leftclick:
            self.label_leftclick.setText(str(left))
        if self.label_midclick:
            self.label_midclick.setText(str(mid))
        if self.label_rightclick:
            self.label_rightclick.setText(str(right))
        
        self._log_to_ui("鼠标数据已更新到界面。")
    
    # ========================
    #  通用方法
    # ========================
    
    def _log_to_ui(self, message: str):
        """输出日志到界面"""
        if not LOGGING_ENABLED:
            return
        if self.log_output:
            self.log_output.append(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")
        else:
            print(message)
    
    def _show_error(self, message: str):
        """显示错误信息"""
        self._log_to_ui(f"错误: {message}")
        self._reset_detection_state()
    
    def _send_with_ack_check(self, cmd: int, payload: bytes = b''):
        """发送命令并启动 ACK 超时检测"""
        self.serial_worker.send_frame(cmd, payload)
        self.ack_timeout_timer.start()
    
    def _on_time_sync(self):
        """定时发送时间同步命令"""
        if self.serial_worker and self.serial_worker.serial_port and self.serial_worker.serial_port.is_open:
            self.serial_worker.send_timestamp()
            self.ack_timeout_timer.start()
        else:
            self._log_to_ui("时间同步失败：串口未连接。")
            self._update_status_disconnected()
    
    # ========================
    #  窗口事件
    # ========================
    
    def closeEvent(self, event):
        """关闭窗口时最小化到托盘"""
        self._log_to_ui("已最小化到托盘。通过托盘图标可再次打开，或选择退出。")
        event.ignore()
        self.hide_window()
    
    def _shutdown_cleanup(self):
        """退出前资源清理"""
        try:
            self.serial_worker.disconnect_serial()
        except Exception:
            pass
        
        try:
            if self.serial_thread.isRunning():
                self.serial_thread.quit()
                if not self.serial_thread.wait(1000):
                    self._log_to_ui("警告: 串口线程未能正常停止。")
        except Exception:
            pass
