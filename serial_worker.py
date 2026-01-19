import struct
import serial
import time
from serial.tools import list_ports

from PySide6.QtCore import QObject, Signal, QThread

from constants import (
    PROTO_VER, CMD_ACK, CMD_NOTIFY_HEALTH_DATA_READY, CMD_GET_LAST_HEALTH_DATA,
    CMD_GET_MOUSE_DATA, CMD_PING, CMD_SYNC_TIME, ACK_SUCCESS,
    CMD_SYNC_DATA_START, CMD_SYNC_DATA_BATCH, CMD_SYNC_DATA_END
)


def crc16_xmodem(data: bytes) -> int:
    """
    A simple, correct, bit-by-bit CRC-16/XMODEM implementation.
    """
    crc = 0x0000
    poly = 0x1021
    for byte in data:
        crc ^= (byte << 8)
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ poly
            else:
                crc <<= 1
    return crc & 0xFFFF


class SerialWorker(QObject):
    """
    串口通信工作线程
    - 在独立线程中运行，避免阻塞 UI
    - 通过信号与主线程通信
    """
    # --- Signals ---
    connected = Signal()
    disconnected = Signal()
    error_occurred = Signal(str)
    log_message = Signal(str)
    
    # 业务信号
    ack_received = Signal(int, int)  # original_cmd, status_code
    health_data_received = Signal(bytes)
    mouse_data_received = Signal(bytes)
    
    # 同步信号
    sync_start = Signal(int)  # estimated_total
    sync_batch = Signal(int, bytes) # sent_count, records
    sync_end = Signal(int, int) # actual_total, flag

    def __init__(self):
        super().__init__()
        self.serial_port = None
        self.is_running = False
        self.read_buffer = b''
        
        # --- 用于自动重连 ---
        self.port_name = ""
        self.baudrate = 0
        self.auto_reconnect = True
        
        self.command_handlers = {
            CMD_ACK: self._handle_ack,
            CMD_NOTIFY_HEALTH_DATA_READY: self._handle_health_data,
            CMD_GET_LAST_HEALTH_DATA: self._handle_health_data,
            CMD_GET_MOUSE_DATA: self._handle_mouse_data,
            CMD_SYNC_DATA_START: self._handle_sync_start,
            CMD_SYNC_DATA_BATCH: self._handle_sync_batch,
            CMD_SYNC_DATA_END: self._handle_sync_end,
        }

    def get_port_info(self, port_name):
            """
            根据端口名获取详细信息和类型
            返回: (description, hwid, port_type)
            """
            # 遍历所有可用串口找到当前连接的这个
            for port in list_ports.comports():
                if port.device == port_name:
                    description = port.description
                    hwid = port.hwid
                    
                    # --- 类型识别逻辑 ---
                    port_type = "未知类型"
                    type_id = -1
                    
                    # 转换为大写以方便匹配
                    upper_desc = description.upper()
                    upper_hwid = hwid.upper()

                    if "BTHENUM" in upper_hwid or "BLUETOOTH" in upper_desc:
                        port_type = "蓝牙串口 (Bluetooth)"
                        type_id = 1
                    elif "USB" in upper_hwid:
                        port_type = "USB转串口 (USB-Serial)"
                        type_id = 2
                    elif "ACPI" in upper_hwid or "PNP" in upper_hwid:
                        port_type = "原生硬件串口 (Native)"
                        type_id = 3
                    elif "VIRTUAL" in upper_desc:
                        port_type = "虚拟串口 (Virtual)"
                        type_id = 4
                    
                    return description, hwid, port_type, type_id
            
            return "未知描述", "未知ID", "未知类型", -1


    def _read_one_frame(self, buffer: bytes):
        """
        尝试从缓冲区读取一个帧。
        
        Returns:
            tuple: (new_buffer, result)
            - new_buffer: 更新后的缓冲区
            - result: 
                None: 数据不足，无法解析
                False: 解析了帧但校验失败（CRC错误等），已丢弃
                dict: {'cmd': int, 'payload': bytes, 'ver': int} 解析成功
        """
        # 1. Find header
        start_index = buffer.find(b'\xAA\x55')
        if start_index == -1:
            if len(buffer) > 1:
                return buffer[-1:], None
            return buffer, None
            
        if start_index > 0:
            buffer = buffer[start_index:]
            
        if len(buffer) < 8:
            return buffer, None
            
        _, _, payload_len = struct.unpack('<BBH', buffer[2:6])
        frame_len = 8 + payload_len
        
        if len(buffer) < frame_len:
            return buffer, None
            
        frame = buffer[:frame_len]
        new_buffer = buffer[frame_len:]
        
        # Validate
        data_to_check = frame[2:6+payload_len]
        received_crc = struct.unpack('<H', frame[6+payload_len:])[0]
        calculated_crc = crc16_xmodem(data_to_check)
        
        if received_crc != calculated_crc:
            self.log_message.emit(f"警告: CRC 校验失败 (收到 {received_crc}, 计算为 {calculated_crc}) Frame: {frame.hex(' ').upper()}")
            return new_buffer, False
            
        proto_ver, cmd, _ = struct.unpack('<BBH', frame[2:6])
        payload = frame[6:6+payload_len]
        
        return new_buffer, {'cmd': cmd, 'payload': payload, 'ver': proto_ver}

    def connect_serial(self, port_name: str, baudrate: int = 115200):
        """连接到串口"""
        self.port_name = port_name
        self.baudrate = baudrate
        
        try:
            desc, hwid, p_type, type_id = self.get_port_info(self.port_name)
            self.log_message.emit(f"尝试连接到串口 {self.port_name} ({desc}, {hwid}, 类型: {p_type})，类型ID {type_id}，波特率 {self.baudrate}...")

            self.serial_port = serial.Serial()
            self.serial_port.port = self.port_name
            self.serial_port.baudrate = self.baudrate
            self.serial_port.timeout = 0.1
            self.serial_port.write_timeout = 1.0  # 设置写超时为1秒
            self.serial_port.dtr = False
            self.serial_port.rts = False
            self.serial_port.open()

            if self.serial_port.is_open:
                # 打开串口，验证设备是否正确响应
                self.log_message.emit("正在验证设备响应...")
                
                # 发送 PING 命令
                self.send_frame(CMD_PING)
                
                # 等待 ACK 响应
                start_time = time.time()
                local_buffer = b''
                verified = False
                
                while time.time() - start_time < 2.0: # 2秒超时
                    if self.serial_port.in_waiting > 0:
                        local_buffer += self.serial_port.read(self.serial_port.in_waiting)
                        
                        # 循环处理 buffer 中的数据
                        while True:
                            local_buffer, result = self._read_one_frame(local_buffer)
                            
                            if result is None:
                                break
                            
                            if result is False:
                                continue
                                
                            # Valid frame
                            cmd = result['cmd']
                            payload = result['payload']
                            
                            if cmd == CMD_ACK and len(payload) >= 2:
                                orig_cmd, status = struct.unpack('<BB', payload)
                                if orig_cmd == CMD_PING and status == ACK_SUCCESS:
                                    verified = True
                                    break
                        
                        if verified:
                            break
                    
                    time.sleep(0.05)
                
                if not verified:
                    self.log_message.emit("设备验证失败：未收到正确的 ACK 响应或超时。")
                    self.serial_port.close()
                    return False
                
                # 将剩余数据放入类成员 buffer，供 run 循环使用
                self.read_buffer = local_buffer
                
                self.is_running = True
                self.log_message.emit(f"串口 {self.port_name} 已连接且设备响应正常。")
                self.connected.emit()
                return True # 指示连接成功
            else:
                raise IOError("无法打开串口。")
        except serial.SerialException as e:
            available_ports = [p.device for p in list_ports.comports()]
            if available_ports:
                ports_str = ", ".join(available_ports)
                error_msg = f"连接串口 {self.port_name} 失败: {e}\n\n当前可用串口: {ports_str}"
            else:
                error_msg = f"连接串口 {self.port_name} 失败: {e}\n\n系统上未找到任何可用串口。"
            self.error_occurred.emit(error_msg)
            return False # 指示连接失败

    def disconnect_serial(self):
        """断开串口连接"""
        self.auto_reconnect = False # 用户主动断开，禁用自动重连
        self.is_running = False
        if self.serial_port and self.serial_port.is_open:
            port_name = self.serial_port.name
            self.serial_port.close()
            self.log_message.emit(f"串口 {port_name} 已断开。")
            self.disconnected.emit()

    def send_frame(self, cmd: int, payload: bytes = b''):
        """构建并发送一个数据帧"""
        if not self.serial_port or not self.serial_port.is_open:
            self.error_occurred.emit("发送失败：串口未连接。")
            return

        len_payload = len(payload)
        header = b'\xAA\x55'
        
        # 帧头之后的数据，用于 CRC 计算
        data_for_crc = struct.pack('<BBH', PROTO_VER, cmd, len_payload) + payload
        crc = crc16_xmodem(data_for_crc)
        
        frame = header + data_for_crc + struct.pack('<H', crc)

        try:
            self.serial_port.write(frame)
            self.log_message.emit(f"发送: {frame.hex(' ').upper()}")
        except serial.SerialTimeoutException:
            self.error_occurred.emit("发送数据超时。")
        except serial.SerialException as e:
            self.error_occurred.emit(f"发送数据失败: {e}")
    
    def send_timestamp(self):
        """发送当前时间戳给设备用于时间校准（包含时区信息）"""
        # 获取当前Unix时间戳（秒，双精度浮点）
        timestamp = time.time()
        
        # 获取本地时区偏移量（秒）
        # time.timezone 是 UTC 与本地标准时间的偏移（秒），为正表示西时区
        # time.altzone 是 UTC 与本地夏令时的偏移
        # time.daylight 表示是否使用夏令时
        if time.daylight and time.localtime().tm_isdst:
            timezone_offset = -time.altzone  # 转换为东正西负
        else:
            timezone_offset = -time.timezone
        
        # 打包：8字节 timestamp + 4字节 timezone_offset（秒）
        payload = struct.pack('<di', timestamp, timezone_offset)
        
        # 格式化时区显示
        offset_hours = timezone_offset // 3600
        offset_minutes = abs(timezone_offset % 3600) // 60
        tz_str = f"UTC{offset_hours:+03d}:{offset_minutes:02d}"
        
        self.log_message.emit(f"发送时间戳: {timestamp} ({time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(timestamp))}) 时区: {tz_str}")
        self.send_frame(CMD_SYNC_TIME, payload)

    def run(self):
        """持续读取串口数据，包含自动重连逻辑"""
        while self.is_running:
            if self.serial_port and self.serial_port.is_open:
                try:
                    # 1. 如果串口有数据，全部读入缓冲区
                    if self.serial_port.in_waiting > 0:
                        data = self.serial_port.read(self.serial_port.in_waiting)
                        self.read_buffer += data
                    
                    # 2. 处理缓冲区中的数据，解析数据帧
                    self._process_read_data()

                except serial.SerialException as e:
                    self.error_occurred.emit(f"读取串口时出错: {e}。")
                    self.serial_port.close()
                    self.disconnected.emit()
                    # 连接丢失，进入重连逻辑
                    if self.auto_reconnect:
                        self.log_message.emit("连接已断开，将在5秒后尝试自动重连...")
                        QThread.sleep(5)
                        self._attempt_reconnect()

            QThread.msleep(20) # 适当增加延时，降低 CPU 占用

    def _attempt_reconnect(self):
        """尝试重新连接串口"""
        while self.auto_reconnect and self.is_running:
            self.log_message.emit(f"正在尝试重新连接到 {self.port_name}...")
            if self.connect_serial(self.port_name, self.baudrate):
                self.log_message.emit("重新连接成功！")
                break # 成功则退出重连循环
            else:
                self.log_message.emit("重新连接失败，将在5秒后重试...")
                QThread.sleep(5)

    def _process_read_data(self):
        """在缓冲区中循环查找并处理所有完整的数据帧"""
        while True:
            self.read_buffer, result = self._read_one_frame(self.read_buffer)
            
            if result is None: # 数据不足
                return
            
            if result is False: # CRC 校验失败
                continue
                
            # 校验通过，处理帧
            cmd = result['cmd']
            payload = result['payload']
            proto_ver = result['ver']
            
            if proto_ver != PROTO_VER:
                self.log_message.emit(f"警告: 协议版本不匹配 (收到 {proto_ver}, 需要 {PROTO_VER})。")
                continue 
                
            self.log_message.emit(f"接收: CMD={hex(cmd)}, Payload={payload.hex(' ').upper()}")
            self._handle_valid_frame(cmd, payload)

    def _handle_valid_frame(self, cmd: int, payload: bytes):
        """处理校验通过的帧，并根据命令分发"""
        handler = self.command_handlers.get(cmd)
        if handler:
            handler(payload)
        else:
            self.log_message.emit(f"警告: 未知的命令 {hex(cmd)}。")

    def _handle_ack(self, payload: bytes):
        """处理 ACK 命令"""
        if len(payload) == 2:
            original_cmd, status_code = struct.unpack('<BB', payload)
            self.ack_received.emit(original_cmd, status_code)
        else:
            self.log_message.emit("警告: ACK 帧的 payload 长度不正确。")

    def _handle_health_data(self, payload: bytes):
        """处理健康数据"""
        self.health_data_received.emit(payload)

    def _handle_mouse_data(self, payload: bytes):
        """处理鼠标数据"""
        self.mouse_data_received.emit(payload)

    def _handle_sync_start(self, payload: bytes):
        if len(payload) >= 4:
            estimated_total = struct.unpack('<I', payload[:4])[0]
            self.sync_start.emit(estimated_total)

    def _handle_sync_batch(self, payload: bytes):
        if len(payload) >= 4:
            sent_count = struct.unpack('<I', payload[:4])[0]
            records = payload[4:]
            self.sync_batch.emit(sent_count, records)

    def _handle_sync_end(self, payload: bytes):
        if len(payload) >= 5:
            total, flag = struct.unpack('<IB', payload[:5])
            self.sync_end.emit(total, flag)
