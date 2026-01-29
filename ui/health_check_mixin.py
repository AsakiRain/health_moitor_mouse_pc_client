"""
健康检测流程 Mixin

提供健康检测的倒计时、超时处理、状态重置等功能。
"""
import struct

from PySide6.QtCore import QTimer

import constants as const


# 检测时长（秒）
COLLTIMES = 100


class HealthCheckMixin:
    """
    健康检测流程 Mixin
    
    需要宿主类提供：
    - self._log_to_ui(msg): 日志输出方法
    - self.start_button: QPushButton 实例
    - self._start_blinking(): 开始闪烁
    - self._stop_blinking(): 停止闪烁
    - self._send_with_ack_check(cmd, payload): 发送命令方法
    - self.serial_worker: SerialWorker 实例
    - self.serial_thread: QThread 实例
    - self.config_handler: ConfigHandler 实例
    """
    
    def _init_health_check(self):
        """初始化健康检测相关定时器"""
        # 检测超时定时器
        self.detection_timeout_timer = QTimer(self)
        self.detection_timeout_timer.setSingleShot(True)
        self.detection_timeout_timer.setInterval(100 * 1000)  # 100秒超时
        self.detection_timeout_timer.timeout.connect(self.on_detection_timeout)
        
        # 倒计时定时器
        self.countdown_timer = QTimer(self)
        self.countdown_timer.setInterval(1000)
        self.countdown_timer.timeout.connect(self._on_countdown_tick)
        self.countdown_remaining = 0
        
        # 保存检测时长
        self.health_check_duration = COLLTIMES
    
    def on_start_button_clicked(self):
        """处理开始按钮点击事件"""
        self._log_to_ui("点击了开始按钮...")
        self._start_blinking()
        self.detection_timeout_timer.start()
        
        if self.start_button:
            self.start_button.setEnabled(False)
            self.start_button.setText("体检中...")
        
        try:
            com_port = self.config_handler.get_com_port()
            if not self.serial_worker.serial_port or not self.serial_worker.serial_port.is_open:
                self.serial_worker.connect_serial(com_port)
                if self.serial_worker.is_running and not self.serial_thread.isRunning():
                    self.serial_thread.start()
                QTimer.singleShot(100, self._send_health_check_with_duration)
            else:
                self._send_health_check_with_duration()
        except Exception as e:
            self._show_error(f"开始体检失败: {e}")
            if self.start_button:
                self.start_button.setEnabled(True)
                self.start_button.setText("开始体检")
    
    def _send_health_check_with_duration(self, duration: int = COLLTIMES):
        """发送检测时长和开始检测命令"""
        duration = max(1, min(255, duration))
        self.health_check_duration = duration
        
        # 发送检测时长
        payload = struct.pack('<B', duration)
        self._send_with_ack_check(const.CMD_SET_HEALTH_CHECK_DURATION, payload)
        self._log_to_ui(f"设置检测时长: {duration} 秒")
        
        # 延迟 50ms 后发送开始命令
        QTimer.singleShot(50, lambda: self._send_with_ack_check(const.CMD_START_HEALTH_CHECK))
    
    def on_detection_timeout(self):
        """健康检测超时处理"""
        self._log_to_ui(f"错误: 健康监测超时 ({COLLTIMES} 秒)，请重试。")
        self._reset_detection_state()
    
    def _on_countdown_tick(self):
        """倒计时定时器回调"""
        if self.countdown_remaining > 0:
            self.countdown_remaining -= 1
        
        if self.start_button:
            if self.countdown_remaining > 0:
                self.start_button.setText(f"{self.countdown_remaining}秒")
            else:
                self.start_button.setText("处理中...")
        
        if self.countdown_remaining <= 0 and self.countdown_timer.isActive():
            self.countdown_timer.stop()
            QTimer.singleShot(2000, self._on_countdown_finished)
    
    def _stop_countdown(self):
        """停止倒计时"""
        if self.countdown_timer.isActive():
            self.countdown_timer.stop()
        self.countdown_remaining = 0
    
    def _on_countdown_finished(self):
        """倒计时结束后的处理"""
        if self.start_button and self.start_button.text() == "处理中...":
            self._log_to_ui("检测完成，重置状态。")
            self._reset_detection_state()
    
    def _is_detection_in_progress(self) -> bool:
        """检查是否正在进行健康检测"""
        return (self.detection_timeout_timer.isActive() or
                (hasattr(self, 'countdown_timer') and self.countdown_timer.isActive()))
    
    def _reset_detection_state(self):
        """重置健康检测状态"""
        self._stop_blinking()
        self._stop_countdown()
        
        if self.detection_timeout_timer.isActive():
            self.detection_timeout_timer.stop()
        
        if self.start_button:
            self.start_button.setEnabled(True)
            self.start_button.setText("开始体检")
    
    def _start_countdown(self, duration: int):
        """启动倒计时"""
        self.countdown_remaining = duration
        if self.start_button:
            self.start_button.setEnabled(False)
            self.start_button.setText(f"{self.countdown_remaining}秒")
        if not self.countdown_timer.isActive():
            self.countdown_timer.start()
