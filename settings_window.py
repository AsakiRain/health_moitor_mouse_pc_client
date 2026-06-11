import struct

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QMessageBox, QPushButton, QSlider, QSpinBox, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget
)
from PySide6.QtGui import QColor

import constants as const


SETTINGS_PAYLOAD_LEN = 38
MAX_DPI_LEVELS = 10


def parse_settings_payload(payload: bytes) -> dict:
    if len(payload) != SETTINGS_PAYLOAD_LEN:
        raise ValueError(f"设置 payload 长度不正确: {len(payload)}")
    dpi_count = payload[0]
    current_idx = payload[1]
    if dpi_count < 1 or dpi_count > MAX_DPI_LEVELS:
        raise ValueError(f"DPI 档位数量不正确: {dpi_count}")
    dpi_values = list(struct.unpack('<10H', payload[2:22]))[:dpi_count]
    wheel_rate = payload[22]
    sedentary_minutes, rest_idle_seconds = struct.unpack('<HH', payload[23:27])
    vibration_level = payload[27]
    led_enabled = payload[28] != 0
    led_mode = payload[29]
    led_period_seconds, auto_sleep_minutes = struct.unpack('<HH', payload[30:34])
    led_color = tuple(payload[34:37])
    led_brightness = payload[37]
    return {
        'dpi_values': dpi_values,
        'current_idx': current_idx,
        'wheel_rate': wheel_rate,
        'sedentary_minutes': sedentary_minutes,
        'rest_idle_seconds': rest_idle_seconds,
        'vibration_level': vibration_level,
        'led_enabled': led_enabled,
        'led_mode': led_mode,
        'led_period_seconds': led_period_seconds,
        'led_color': led_color,
        'led_brightness': led_brightness,
        'auto_sleep_minutes': auto_sleep_minutes,
    }


def build_settings_payload(settings: dict) -> bytes:
    dpi_values = settings['dpi_values']
    dpi_count = len(dpi_values)
    if dpi_count < 1 or dpi_count > MAX_DPI_LEVELS:
        raise ValueError("DPI 档位数量必须是 1-10")
    current_idx = settings['current_idx']
    if current_idx < 0 or current_idx >= dpi_count:
        raise ValueError("当前 DPI 档位超出范围")
    padded = dpi_values + [0] * (MAX_DPI_LEVELS - dpi_count)
    return struct.pack(
        '<BB10HBHHBBBHHBBBB',
        dpi_count,
        current_idx,
        *padded,
        settings['wheel_rate'],
        settings['sedentary_minutes'],
        settings['rest_idle_seconds'],
        settings['vibration_level'],
        1 if settings['led_enabled'] else 0,
        settings['led_mode'],
        settings['led_period_seconds'],
        settings['auto_sleep_minutes'],
        *settings['led_color'],
        settings['led_brightness'],
    )


class MouseSettingsWindow(QDialog):
    def __init__(self, serial_worker, parent=None):
        super().__init__(parent)
        self.serial_worker = serial_worker
        self.custom_color = QColor(0, 80, 180)
        self.setWindowTitle("鼠标设置")
        self.resize(560, 620)

        layout = QVBoxLayout(self)
        layout.addWidget(self._build_dpi_group())
        layout.addWidget(self._build_behavior_group())
        layout.addWidget(self._build_led_group())

        buttons = QDialogButtonBox(self)
        self.refresh_button = buttons.addButton("读取设备", QDialogButtonBox.ButtonRole.ActionRole)
        self.save_button = buttons.addButton("保存到设备", QDialogButtonBox.ButtonRole.AcceptRole)
        close_button = buttons.addButton(QDialogButtonBox.StandardButton.Close)
        self.refresh_button.clicked.connect(self.request_settings)
        self.save_button.clicked.connect(self.save_settings)
        close_button.clicked.connect(self.close)
        layout.addWidget(buttons)

        self.serial_worker.mouse_settings_received.connect(self.apply_payload)
        self.request_settings()

    def _build_dpi_group(self):
        group = QGroupBox("DPI 档位")
        layout = QVBoxLayout(group)
        self.dpi_table = QTableWidget(4, 1)
        self.dpi_table.setHorizontalHeaderLabels(["DPI"])
        self.dpi_table.verticalHeader().setVisible(True)
        self.dpi_table.horizontalHeader().setStretchLastSection(True)
        for row, value in enumerate([800, 1000, 1200, 1600]):
            self.dpi_table.setItem(row, 0, QTableWidgetItem(str(value)))
        layout.addWidget(self.dpi_table)

        controls = QHBoxLayout()
        add_btn = QPushButton("新增档位")
        remove_btn = QPushButton("删除档位")
        add_btn.clicked.connect(self.add_dpi_row)
        remove_btn.clicked.connect(self.remove_dpi_row)
        self.current_dpi = QComboBox()
        controls.addWidget(add_btn)
        controls.addWidget(remove_btn)
        controls.addWidget(QLabel("当前档位"))
        controls.addWidget(self.current_dpi)
        layout.addLayout(controls)
        self._refresh_dpi_combo(3)
        return group

    def _build_behavior_group(self):
        group = QGroupBox("行为设置")
        form = QFormLayout(group)
        self.wheel_rate = QComboBox()
        self.wheel_rate.addItems(["慢", "标准", "快"])
        self.wheel_rate.setCurrentIndex(1)
        self.vibration_level = QComboBox()
        self.vibration_level.addItems(["轻", "中", "强"])
        self.vibration_level.setCurrentIndex(1)
        self.vibration_level.currentIndexChanged.connect(lambda _: self.test_vibration())
        self.sedentary_minutes = self._spin(1, 360, 45)
        self.rest_idle_seconds = self._spin(1, 3600, 60)
        self.auto_sleep_minutes = self._spin(1, 1440, 30)
        form.addRow("滚轮速率", self.wheel_rate)
        form.addRow("久坐提醒时间(分钟)", self.sedentary_minutes)
        form.addRow("休息间隔判定(秒)", self.rest_idle_seconds)
        form.addRow("震动强度", self.vibration_level)
        form.addRow("自动睡眠时间(分钟)", self.auto_sleep_minutes)
        return group

    def _build_led_group(self):
        group = QGroupBox("LED 灯光")
        form = QFormLayout(group)
        self.led_enabled = QCheckBox("启用 LED")
        self.led_enabled.setChecked(True)
        self.led_mode = QComboBox()
        self.led_mode.addItems(["常亮蓝", "彩虹循环", "呼吸渐变", "追逐灯", "自定义颜色"])
        self.led_mode.setCurrentIndex(1)
        self.led_period_seconds = self._spin(1, 3600, 8)
        self.led_brightness = self._spin(1, 255, 180)
        self.led_brightness_slider = QSlider(Qt.Horizontal)
        self.led_brightness_slider.setRange(1, 255)
        self.led_brightness_slider.setValue(self.led_brightness.value())
        self.led_brightness_slider.valueChanged.connect(self.led_brightness.setValue)
        self.led_brightness.valueChanged.connect(self.led_brightness_slider.setValue)
        brightness_row = QWidget()
        brightness_layout = QHBoxLayout(brightness_row)
        brightness_layout.setContentsMargins(0, 0, 0, 0)
        brightness_layout.addWidget(self.led_brightness_slider)
        brightness_layout.addWidget(self.led_brightness)
        self.color_button = QPushButton()
        self.color_button.clicked.connect(self.pick_color)
        form.addRow("开关", self.led_enabled)
        form.addRow("光效模式", self.led_mode)
        form.addRow("循环周期(秒)", self.led_period_seconds)
        form.addRow("亮度比例", brightness_row)
        form.addRow("自定义颜色", self.color_button)
        self._update_color_button()
        return group

    def _spin(self, minimum, maximum, value):
        spin = QSpinBox()
        spin.setRange(minimum, maximum)
        spin.setValue(value)
        return spin

    def add_dpi_row(self):
        if self.dpi_table.rowCount() >= MAX_DPI_LEVELS:
            QMessageBox.information(self, "提示", "最多 10 组 DPI 档位。")
            return
        row = self.dpi_table.rowCount()
        self.dpi_table.insertRow(row)
        self.dpi_table.setItem(row, 0, QTableWidgetItem("1600"))
        self._refresh_dpi_combo(row)

    def remove_dpi_row(self):
        if self.dpi_table.rowCount() <= 1:
            QMessageBox.information(self, "提示", "至少保留 1 组 DPI 档位。")
            return
        row = self.dpi_table.currentRow()
        if row < 0:
            row = self.dpi_table.rowCount() - 1
        self.dpi_table.removeRow(row)
        self._refresh_dpi_combo(min(self.current_dpi.currentIndex(), self.dpi_table.rowCount() - 1))

    def _refresh_dpi_combo(self, selected=0):
        count = self.dpi_table.rowCount()
        self.current_dpi.clear()
        self.current_dpi.addItems([f"第 {i + 1} 档" for i in range(count)])
        self.current_dpi.setCurrentIndex(max(0, min(selected, count - 1)))

    def request_settings(self):
        self.serial_worker.send_frame(const.CMD_GET_MOUSE_SETTINGS)

    def apply_payload(self, payload: bytes):
        try:
            settings = parse_settings_payload(payload)
        except ValueError as exc:
            QMessageBox.warning(self, "设置读取失败", str(exc))
            return
        self.dpi_table.setRowCount(len(settings['dpi_values']))
        for row, value in enumerate(settings['dpi_values']):
            self.dpi_table.setItem(row, 0, QTableWidgetItem(str(value)))
        self._refresh_dpi_combo(settings['current_idx'])
        self.wheel_rate.setCurrentIndex(settings['wheel_rate'])
        self.sedentary_minutes.setValue(settings['sedentary_minutes'])
        self.rest_idle_seconds.setValue(settings['rest_idle_seconds'])
        self.vibration_level.blockSignals(True)
        self.vibration_level.setCurrentIndex(settings['vibration_level'])
        self.vibration_level.blockSignals(False)
        self.led_enabled.setChecked(settings['led_enabled'])
        self.led_mode.setCurrentIndex(settings['led_mode'])
        self.led_period_seconds.setValue(settings['led_period_seconds'])
        self.led_brightness.setValue(settings['led_brightness'])
        r, g, b = settings['led_color']
        self.custom_color = QColor(r, g, b)
        self._update_color_button()
        self.auto_sleep_minutes.setValue(settings['auto_sleep_minutes'])

    def _update_color_button(self):
        self.color_button.setText(self.custom_color.name().upper())
        self.color_button.setStyleSheet(
            f"background-color: {self.custom_color.name()}; color: #ffffff; font-weight: bold;"
        )

    def pick_color(self):
        color = QColorDialog.getColor(self.custom_color, self, "选择 LED 颜色")
        if color.isValid():
            self.custom_color = color
            self.led_mode.setCurrentIndex(4)
            self._update_color_button()

    def collect_settings(self) -> dict:
        dpi_values = []
        for row in range(self.dpi_table.rowCount()):
            item = self.dpi_table.item(row, 0)
            try:
                value = int(item.text().strip()) if item else 0
            except ValueError:
                value = 0
            if value < 100 or value > 26000:
                raise ValueError("DPI 必须在 100-26000 之间")
            dpi_values.append(value)
        return {
            'dpi_values': dpi_values,
            'current_idx': self.current_dpi.currentIndex(),
            'wheel_rate': self.wheel_rate.currentIndex(),
            'sedentary_minutes': self.sedentary_minutes.value(),
            'rest_idle_seconds': self.rest_idle_seconds.value(),
            'vibration_level': self.vibration_level.currentIndex(),
            'led_enabled': self.led_enabled.isChecked(),
            'led_mode': self.led_mode.currentIndex(),
            'led_period_seconds': self.led_period_seconds.value(),
            'led_brightness': self.led_brightness.value(),
            'led_color': (self.custom_color.red(), self.custom_color.green(), self.custom_color.blue()),
            'auto_sleep_minutes': self.auto_sleep_minutes.value(),
        }

    def save_settings(self):
        try:
            payload = build_settings_payload(self.collect_settings())
        except ValueError as exc:
            QMessageBox.warning(self, "设置无效", str(exc))
            return
        self.serial_worker.send_frame(const.CMD_SET_MOUSE_SETTINGS, payload)
        QMessageBox.information(self, "已发送", "设置已发送到设备。")

    def test_vibration(self):
        self.serial_worker.send_frame(
            const.CMD_TEST_VIBRATION,
            bytes([self.vibration_level.currentIndex()])
        )
