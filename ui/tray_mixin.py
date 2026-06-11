"""
系统托盘 Mixin

提供系统托盘图标管理、闪烁效果、托盘菜单等功能。
"""
from PySide6.QtWidgets import QSystemTrayIcon, QMenu, QMessageBox, QApplication
from PySide6.QtGui import QAction, QPixmap, QPainter, QFont, QFontMetrics, QIcon
from PySide6.QtCore import Qt, QTimer


class TrayMixin:
    """
    系统托盘功能 Mixin
    
    需要宿主类提供：
    - self: QMainWindow 实例
    - self._log_to_ui(msg): 日志输出方法
    """
    
    def _init_tray(self):
        """初始化系统托盘图标和菜单"""
        # 创建图标
        self.icon_heart = self._create_emoji_icon('❤️')
        self.icon_white_heart = self._create_emoji_icon('🩶')
        self.is_heart_icon = False
        self.setWindowIcon(self.icon_heart)
        
        # 托盘图标
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(self.icon_heart)
        
        # 托盘菜单
        tray_menu = QMenu()
        show_action = QAction("显示主界面", self)
        about_action = QAction("关于", self)
        exit_action = QAction("退出", self)
        
        tray_menu.addAction(show_action)
        tray_menu.addAction(about_action)
        tray_menu.addSeparator()
        tray_menu.addAction(exit_action)
        
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self._handle_tray_activation)
        show_action.triggered.connect(self.show_window)
        about_action.triggered.connect(self._show_about_dialog)
        exit_action.triggered.connect(self.exit_app)
        self.tray_icon.show()
        
        # 闪烁定时器
        self.blink_timer = QTimer(self)
        self.blink_timer.setInterval(500)
        self.blink_timer.timeout.connect(self._toggle_icon)
    
    def _create_emoji_icon(self, emoji_char: str, size: int = 64) -> QIcon:
        """将 emoji 字符转换为 QIcon"""
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        
        font = QFont("Segoe UI Emoji", size - 10)
        font.setPixelSize(size - 10)
        painter.setFont(font)
        
        font_metrics = QFontMetrics(font)
        text_width = font_metrics.horizontalAdvance(emoji_char)
        text_rect = font_metrics.boundingRect(emoji_char)
        y_pos = (pixmap.height() - text_rect.height()) / 2 + font_metrics.ascent()
        x_pos = (pixmap.width() - text_width) / 2

        painter.drawText(int(x_pos), int(y_pos), emoji_char)
        painter.end()
        return QIcon(pixmap)
    
    def _toggle_icon(self):
        """切换图标（闪烁效果）"""
        if self.is_heart_icon:
            current_icon = self.icon_white_heart
        else:
            current_icon = self.icon_heart
        
        self.setWindowIcon(current_icon)
        self.tray_icon.setIcon(current_icon)
        self.is_heart_icon = not self.is_heart_icon
    
    def _start_blinking(self):
        """开始图标闪烁"""
        if hasattr(self, '_log_to_ui'):
            self._log_to_ui("开始闪烁...")
        if not self.blink_timer.isActive():
            self.blink_timer.start()
    
    def _stop_blinking(self):
        """停止图标闪烁"""
        if self.blink_timer.isActive():
            self.blink_timer.stop()
            self.setWindowIcon(self.icon_heart)
            self.tray_icon.setIcon(self.icon_heart)
            self.is_heart_icon = False
            if hasattr(self, '_log_to_ui'):
                self._log_to_ui("停止闪烁。")
    
    def _handle_tray_activation(self, reason):
        """处理托盘图标激活事件"""
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, 
                      QSystemTrayIcon.ActivationReason.DoubleClick):
            self.show_window()
    
    def _show_about_dialog(self):
        """显示关于对话框"""
        QMessageBox.about(
            self,
            "关于",
            "<p style='font-size: 1px;'>&nbsp;</p>"
            "<p style='font-size: 14px; font-weight: bold;'> 健康监控鼠标 数据查看工具 v1.0 &nbsp;</p>"
            "<p align='center'>Powered by <a href='https://cynix.cc' style='color: #89b4fa;'>Cynix.cc</a>&nbsp;&nbsp;&nbsp;</p>"
        )
    
    def show_window(self):
        """显示主窗口"""
        # 恢复窗口时，若仍在检测中则保持闪烁
        if hasattr(self, '_is_detection_in_progress') and not self._is_detection_in_progress():
            self._stop_blinking()
        self.show()
        self.activateWindow()
    
    def hide_window(self):
        """隐藏主窗口（最小化到托盘）"""
        self.hide()
    
    def exit_app(self):
        """退出应用"""
        self.tray_icon.hide()
        if hasattr(self, '_shutdown_cleanup'):
            self._shutdown_cleanup()
        QApplication.quit()
