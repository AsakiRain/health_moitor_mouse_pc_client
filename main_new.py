"""
CyMouse Monitor 应用入口

初始化数据库、配置文件，并启动主窗口。
"""
import sys
import ctypes
from PySide6.QtWidgets import QApplication

from config_handler import ConfigHandler
from db.connection import init_database


def main():
    # Windows: 设置 AppUserModelID 以确保任务栏图标正确显示
    if sys.platform == 'win32':
        myappid = 'cynix.cymouse.monitor.1.0'
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    
    # 初始化配置文件
    ConfigHandler()
    
    # 初始化数据库
    init_database()
    
    # 创建主窗口（延迟导入以确保数据库已初始化）
    from main_window_new import MainWindow
    main_window = MainWindow()
    
    # 启动时是否显示主窗口（默认隐藏到托盘）
    # main_window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
