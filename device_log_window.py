from datetime import datetime

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)


class DeviceLogWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设备日志")
        self.resize(760, 420)

        self.log_output = QTextEdit(self)
        self.log_output.setReadOnly(True)
        self.log_output.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)

        self.clear_button = QPushButton("清空", self)
        self.clear_button.clicked.connect(self.log_output.clear)

        button_layout = QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(self.clear_button)

        layout = QVBoxLayout(self)
        layout.addWidget(self.log_output)
        layout.addLayout(button_layout)

    def append_log(self, message: str):
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        self.log_output.append(f"[{timestamp}] {message}")

    def closeEvent(self, event):
        parent = self.parent()
        if parent is not None and hasattr(parent, "_set_device_log_enabled"):
            parent._set_device_log_enabled(False)
        super().closeEvent(event)
