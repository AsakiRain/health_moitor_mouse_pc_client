import math
import csv
import struct
from datetime import datetime
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QTableView, QHeaderView, 
    QHBoxLayout, QPushButton, QLabel, QStyledItemDelegate, QMenu, QApplication,
    QFileDialog, QMessageBox, QProgressDialog
)
from PySide6.QtSql import QSqlDatabase, QSqlQueryModel, QSqlQuery
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction

import constants as const

class CenteredDelegate(QStyledItemDelegate):
    """用于在 QTableView 中居中对齐所有文本的委托"""
    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        option.displayAlignment = Qt.AlignCenter

class HistoryWindow(QDialog):
    """
    一个用于显示数据库历史数据的窗口。
    - 使用 QSqlQueryModel 实现分页加载
    - 固定窗口大小
    - 表格列宽自适应
    - 隐藏了 ID 列和行号
    """
    request_sync = Signal(int)

    def __init__(self, db_path='history.db', parent=None):
        super().__init__(parent)
        self.setWindowTitle("历史数据")
        self.setFixedSize(900, 555) # 固定窗口大小，禁止拖动调整

        # --- 分页变量 ---
        self.current_page = 0
        self.page_size = 15  # 每页显示20条
        self.total_rows = 0
        self.total_pages = 0

        # --- 数据库连接 ---
        self.db = QSqlDatabase.addDatabase("QSQLITE", "history_connection")
        self.db.setDatabaseName(db_path)
        if not self.db.open():
            print(f"错误: 无法打开数据库 {db_path}")
            return
            
        self._get_total_rows()
        if self.total_rows > 0:
            self.total_pages = math.ceil(self.total_rows / self.page_size)
        
        # --- UI 初始化 ---
        self._setup_ui()
        self._go_to_page(1) # 跳转到第一页
        self._center_window()

    def _center_window(self):
        """将窗口移动到屏幕中心"""
        screen = QApplication.primaryScreen()
        if screen:
            rect = screen.availableGeometry()
            x = (rect.width() - self.width()) // 2
            y = (rect.height() - self.height()) // 2
            self.move(x, y)

    def _get_total_rows(self):
        """获取总记录数"""
        query = QSqlQuery("SELECT COUNT(*) FROM health_data", self.db)
        if query.exec() and query.next():
            self.total_rows = query.value(0)
        else:
            self.total_rows = 0

    def _setup_ui(self):
        """初始化界面控件"""
        # --- 模型和视图 ---
        self.model = QSqlQueryModel(self)
        self.view = QTableView()
        self.view.setModel(self.model)
        self.view.setEditTriggers(QTableView.NoEditTriggers)
        self.view.verticalHeader().setVisible(False)  # 1. 隐藏行号
        self.view.setItemDelegate(CenteredDelegate(self))
        
        # --- 样式优化：隔行变色 ---
        self.view.setAlternatingRowColors(True)
        self.view.setStyleSheet("""
            QTableView {
                background-color: #1e1e2e;
                alternate-background-color: #2a2b3c;
                selection-background-color: #45475a;
                color: #cdd6f4;
                gridline-color: #313244;
                border: none;
            }
            QHeaderView::section {
                background-color: #181825;
                color: #89b4fa;
                padding: 5px;
                border: 1px solid #313244;
                font-weight: bold;
            }
            QTableCornerButton::section {
                background-color: #181825;
                border: 1px solid #313244;
            }
        """)

        # 1. 设置为行选中
        self.view.setSelectionBehavior(QTableView.SelectRows)
        self.view.setSelectionMode(QTableView.SingleSelection) # 可选，单行或多行

        # 2. 添加右键菜单
        self.view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self._show_context_menu)

        # 设置表头为粗体
        self.view.horizontalHeader().setStyleSheet("QHeaderView::section { font-weight: bold; }")

        # --- 功能按钮 ---
        self.sync_button = QPushButton("同步数据")
        self.sync_button.clicked.connect(self.sync_data)

        self.extra_button = QPushButton("导出数据")
        self.extra_button.clicked.connect(self.export_data)

        self.ai_analysis_button = QPushButton("AI 分析")
        self.ai_analysis_button.clicked.connect(self.open_report_window)

        functions_layout = QHBoxLayout()
        functions_layout.addWidget(self.sync_button)
        functions_layout.addWidget(self.extra_button)
        functions_layout.addWidget(self.ai_analysis_button)
        functions_layout.addStretch()


        # --- 分页控件 ---
        self.prev_button = QPushButton("上一页")
        self.prev_button.clicked.connect(self.prev_page)
        self.next_button = QPushButton("下一页")
        self.next_button.clicked.connect(self.next_page)
        self.page_label = QLabel()

        pagination_layout = QHBoxLayout()
        pagination_layout.addStretch()
        pagination_layout.addWidget(self.prev_button)
        pagination_layout.addWidget(self.page_label)
        pagination_layout.addWidget(self.next_button)
        pagination_layout.addSpacing(20)

        # --- 主布局 ---
        main_layout = QVBoxLayout(self)
        main_layout.addWidget(self.view)
        # 创建底部控件容器
        bottom_layout = QHBoxLayout()
        bottom_layout.addLayout(functions_layout)   # 左侧：功能按钮
        bottom_layout.addLayout(pagination_layout)  # 右侧：翻页按钮

        # 添加到主布局
        main_layout.addLayout(bottom_layout)

        self.setLayout(main_layout)

    def _show_context_menu(self, pos):
        """显示右键菜单"""
        index = self.view.indexAt(pos)
        if not index.isValid():
            return

        menu = QMenu(self)
        delete_action = QAction("删除", self)
        delete_action.triggered.connect(self._delete_selected_row)
        menu.addAction(delete_action)
        
        # 在鼠标点击位置显示菜单
        menu.exec(self.view.viewport().mapToGlobal(pos))

    def _delete_selected_row(self):
        """删除选中的行"""
        selected_indexes = self.view.selectionModel().selectedRows()
        if not selected_indexes:
            return

        # 获取选中行的 ID
        row_to_delete = selected_indexes[0].row()
        id_col_index = self.model.record().indexOf('id')
        if id_col_index == -1:
            print("错误: 找不到 'id' 列")
            return
            
        record_id = self.model.index(row_to_delete, id_col_index).data()

        # 执行删除操作
        query = QSqlQuery(self.db)
        query.prepare("DELETE FROM health_data WHERE id = :id")
        query.bindValue(":id", record_id)
        
        if query.exec():
            print(f"成功删除记录 ID: {record_id}")
            # 刷新数据
            self._get_total_rows() # 重新获取总数
            self.total_pages = math.ceil(self.total_rows / self.page_size) if self.total_rows > 0 else 0
            
            # 如果当前页在删除后变成空的，且不是第一页，则返回上一页
            if self.current_page > 1 and self.model.rowCount() == 1:
                self._go_to_page(self.current_page - 1)
            else:
                self._go_to_page(self.current_page) # 留在当前页刷新
        else:
            print(f"删除失败: {query.lastError().text()}")


    def _go_to_page(self, page_num):
        """跳转到指定页"""
        if self.total_pages > 0 and not (1 <= page_num <= self.total_pages):
            return

        self.current_page = page_num
        offset = (self.current_page - 1) * self.page_size
        
        # 只查询需要的字段
        query_str = (
            "SELECT created_at, heartrate, spo2, bk, fatigue, systolic, "
            "diastolic, CAST(cardiac AS REAL) / 10.0 AS cardiac, resistance, id "
            "FROM health_data ORDER BY id DESC "
            f"LIMIT {self.page_size} OFFSET {offset}"
        )
        self.model.setQuery(query_str, self.db)

        # 每次查询后都需要重新设置表头和隐藏列
        self._set_headers()

        # 设置列宽：第一列根据内容调整，其他列自适应窗口
        header = self.view.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Stretch)
        created_at_col_index = self.model.record().indexOf('created_at')
        if created_at_col_index != -1:
            header.setSectionResizeMode(created_at_col_index, QHeaderView.ResizeToContents)
        
        id_col_index = self.model.record().indexOf('id')
        if id_col_index != -1:
            self.view.setColumnHidden(id_col_index, True) # 1. 隐藏ID列

        self._update_pagination_controls()

    def _update_pagination_controls(self):
        """更新分页按钮和标签的状态"""
        if self.total_pages > 0:
            self.page_label.setText(f"第 {self.current_page} / {self.total_pages} 页")
            self.prev_button.setEnabled(self.current_page > 1)
            self.next_button.setEnabled(self.current_page < self.total_pages)
        else:
            self.page_label.setText("无数据")
            self.prev_button.setEnabled(False)
            self.next_button.setEnabled(False)

    def prev_page(self):
        self._go_to_page(self.current_page - 1)

    def next_page(self):
        self._go_to_page(self.current_page + 1)

    def _set_headers(self):
        """将数据库字段名映射为中文表头，并添加详细的Tooltip"""
        header_map = {
            'created_at': '采集时间',
            'heartrate': '心率',
            'spo2': '血氧',
            'bk': '微循环',
            'fatigue': '疲劳指数',
            'systolic': '收缩压',
            'diastolic': '舒张压',
            'cardiac': '心输出',
            'resistance': '外周阻力',
        }
        
        record = self.model.record()
        for col in range(record.count()):
            field_name = record.fieldName(col)
            if field_name in header_map:
                self.model.setHeaderData(col, Qt.Horizontal, header_map[field_name])
            if field_name in const.HEALTH_METRICS_TOOLTIPS:
                tooltip = const.HEALTH_METRICS_TOOLTIPS[field_name]
                self.model.setHeaderData(col, Qt.Horizontal, tooltip, Qt.ToolTipRole)

    def sync_data(self):
        """将设备上的历史数据同步到本地数据库"""
        # 1. 查找本地最后一条数据的 timestamp
        last_ts = 0
        query = QSqlQuery("SELECT MAX(created_at) FROM health_data", self.db)
        if query.exec() and query.next():
            val = query.value(0)
            if val:
                try:
                    dt = datetime.strptime(val, "%Y-%m-%d %H:%M:%S")
                    last_ts = int(dt.timestamp())
                except Exception:
                    pass
        
        # 2. 显示进度条
        self.progress_dialog = QProgressDialog("正在请求同步...", "取消", 0, 100, self)
        self.progress_dialog.setWindowModality(Qt.WindowModal)
        self.progress_dialog.setMinimumDuration(0)
        self.progress_dialog.setValue(0)
        self.progress_dialog.canceled.connect(self._cancel_sync)
        self.progress_dialog.show()
        
        self.sync_received_count = 0
        self.sync_total = 0

        # 3. 发送请求信号
        self.request_sync.emit(last_ts)

    def _cancel_sync(self):
        self.sync_received_count = 0
        # 可以在此处发送停止同步的指令给设备，如果协议支持的话

    def on_sync_start(self, total):
        self.sync_total = total
        self.sync_received_count = 0
        self.progress_dialog.setLabelText(f"准备同步 {total} 条记录...")
        self.progress_dialog.setMaximum(total if total > 0 else 100)
        
        #开启事务以加速批量插入
        QSqlQuery("PRAGMA synchronous = OFF", self.db).exec()
        self.db.transaction()

    def on_sync_batch(self, sent_count, data):
        if self.progress_dialog.wasCanceled():
            return

        record_size = 17 # 13 bytes metrics + 4 bytes timestamp
        if len(data) % record_size != 0:
            print(f"Warning: Batch data length {len(data)} is not multiple of {record_size}")
        
        num_records = len(data) // record_size
        
        query = QSqlQuery(self.db)
        query.prepare("""
            INSERT INTO health_data (
                created_at, heartrate, spo2, bk, fatigue, systolic, diastolic, 
                cardiac, resistance, rr_interval, sdnn, rmssd, nn50, pnn50
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """)
        
        for i in range(num_records):
            chunk = data[i*record_size : (i+1)*record_size]
            try:
                # <13B I
                unpacked = struct.unpack('<BBBBBBBBBBBBBI', chunk)
                metrics = unpacked[:13]
                ts = unpacked[13]
                
                ts_str = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
                
                query.addBindValue(ts_str)
                for m in metrics:
                    query.addBindValue(m)
                
                if not query.exec():
                   print(f"Insert error: {query.lastError().text()}")
                
                self.sync_received_count += 1
            except struct.error:
                print("Error unpacking record in batch")
        
        self.progress_dialog.setValue(self.sync_received_count)
        self.progress_dialog.setLabelText(f"已同步 {self.sync_received_count}/{self.sync_total}...")

    def on_sync_end(self, total, flag):
        self.db.commit()
        QSqlQuery("PRAGMA synchronous = FULL", self.db).exec()
        
        self.progress_dialog.setValue(self.sync_total)
        self.progress_dialog.close()
        
        # 刷新界面
        self._get_total_rows()
        self.total_pages = math.ceil(self.total_rows / self.page_size) if self.page_size > 0 else 0
        self._go_to_page(1)
        
        # 防止重复弹窗，检查是否已取消
        if not self.progress_dialog.wasCanceled():
             QMessageBox.information(self, "同步完成", 
                f"同步结束。\n服务端总数: {total}\n接收条数: {self.sync_received_count}")

    def export_data(self):
        """导出所有历史数据到 CSV 文件"""
        if self.total_rows == 0:
            QMessageBox.information(self, "提示", "暂无数据可导出")
            return
        
        # 生成默认文件名：CyMouse_数据_日期时间.csv
        default_filename = f"CyMouse_健康数据_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        # 让用户选择保存位置
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "导出数据",
            default_filename,
            "CSV 文件 (*.csv);;所有文件 (*.*)"
        )
        
        if not file_path:
            return  # 用户取消
        
        try:
            # 查询所有数据（不分页）
            query = QSqlQuery(
                "SELECT created_at, heartrate, spo2, bk, fatigue, systolic, "
                "diastolic, CAST(cardiac AS REAL) / 10.0 AS cardiac, resistance "
                "FROM health_data ORDER BY id DESC",
                self.db
            )
            
            if not query.exec():
                QMessageBox.critical(self, "错误", f"查询数据失败: {query.lastError().text()}")
                return
            
            # 写入 CSV 文件
            with open(file_path, 'w', newline='', encoding='utf-8-sig') as csvfile:
                writer = csv.writer(csvfile)
                
                # 写入中文表头
                headers = ['采集时间', '心率', '血氧', '微循环', '疲劳指数', 
                          '收缩压', '舒张压', '心输出', '外周阻力']
                writer.writerow(headers)
                
                # 写入数据行
                row_count = 0
                while query.next():
                    row = [
                        query.value(0),  # created_at
                        query.value(1),  # heartrate
                        query.value(2),  # spo2
                        query.value(3),  # bk
                        query.value(4),  # fatigue
                        query.value(5),  # systolic
                        query.value(6),  # diastolic
                        query.value(7),  # cardiac (已除以10)
                        query.value(8),  # resistance
                    ]
                    writer.writerow(row)
                    row_count += 1
            
            QMessageBox.information(
                self, 
                "导出成功", 
                f"已成功导出 {row_count} 条记录到:\n{file_path}"
            )
            
        except Exception as e:
            QMessageBox.critical(self, "错误", f"导出失败: {str(e)}")

    def closeEvent(self, event):
        """重写 closeEvent，在窗口关闭时断开数据库连接"""
        # 1) 清空模型查询并解绑视图，确保不再持有连接引用
        try:
            if hasattr(self, 'model') and self.model is not None:
                self.model.setQuery(QSqlQuery())
        except Exception:
            pass
        try:
            if hasattr(self, 'view') and self.view is not None:
                self.view.setModel(None)
        except Exception:
            pass

        # 2) 关闭并释放数据库连接对象，再移除连接
        conn_name = None
        try:
            if hasattr(self, 'db') and self.db.isValid():
                conn_name = self.db.connectionName()
                if self.db.isOpen():
                    self.db.close()
                # 释放对连接的最后引用
                tmp_db = self.db
                self.db = QSqlDatabase()
                del tmp_db
        except Exception:
            pass

        if conn_name:
            QSqlDatabase.removeDatabase(conn_name)
        print("历史数据窗口的数据库连接已关闭。")
        super().closeEvent(event)

    def open_report_window(self):
        """打开 AI 分析报告窗口"""
        from report import ReportWindow
        self.report_window = ReportWindow()
        self.report_window.show()
