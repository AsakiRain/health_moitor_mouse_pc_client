"""
状态栏 Mixin

提供状态栏初始化、连接状态显示、状态图标点击事件等功能。
"""
from PySide6.QtWidgets import QLabel
from PySide6.QtCore import QTimer

import constants as const


# ACK 超时时间，单位毫秒
ACK_TIMEOUT_MS = 3000


class StatusBarMixin:
    """
    状态栏功能 Mixin
    
    需要宿主类提供：
    - self: QMainWindow 实例
    - self._log_to_ui(msg): 日志输出方法
    - self.serial_worker: SerialWorker 实例
    - self._send_with_ack_check(cmd, payload): 发送命令方法
    """
    
    def _init_status_bar(self):
        """初始化状态栏"""
        self.statusBar().setStyleSheet("QStatusBar::item { border: none; }")
        self.status_icon = QLabel()
        self.status_label = QLabel("未连接")
        self.statusBar().addWidget(self.status_icon)
        self.statusBar().addWidget(self.status_label)
        self._update_status_disconnected()

        # 为 status_icon 绑定点击事件
        self.status_icon.mouseReleaseEvent = self._on_status_icon_clicked
        
        # ACK 超时定时器
        self.ack_timeout_timer = QTimer(self)
        self.ack_timeout_timer.setSingleShot(True)
        self.ack_timeout_timer.setInterval(ACK_TIMEOUT_MS)
        self.ack_timeout_timer.timeout.connect(self._on_ack_timeout)
    
    def _on_status_icon_clicked(self, event):
        """
        处理状态图标点击事件
        
        设备已连接时：发送强制时间同步 + 设备状态检测
        设备未连接时：提示无法发送
        """
        if self.status_label.text() == "已连接":
            self._log_to_ui("手动发送强制时间同步指令...")
            self.serial_worker.send_timestamp(force=True)
            self.ack_timeout_timer.start()
            
            self._log_to_ui("手动发送设备状态检测指令...")
            self._send_with_ack_check(const.CMD_DEVICE_STATUS_CHECK)
        else:
            self._log_to_ui("设备未连接，无法发送指令。")
    
    def _on_ack_timeout(self):
        """发送指令后未在规定时间内收到 ACK，认为设备断开"""
        self._log_to_ui("警告: 未收到设备 ACK 响应，设备可能已断开")
        self._update_status_disconnected()
    
    def _on_device_response(self):
        """收到设备任何有效响应时调用，取消 ACK 超时并更新连接状态"""
        if self.ack_timeout_timer.isActive():
            self.ack_timeout_timer.stop()
        self._update_status_connected()
    
    def _update_status_connected(self):
        """更新状态为已连接"""
        self.status_icon.setText("🟢")
        self.status_label.setText("已连接")
    
    def _update_status_disconnected(self):
        """更新状态为未连接"""
        self.status_icon.setText("🔴")
        self.status_label.setText("未连接")
