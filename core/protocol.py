"""
协议解析模块
- CRC16-XMODEM 校验
- 数据帧构建与解析
"""
import struct
from constants import PROTO_VER


def crc16_xmodem(data: bytes) -> int:
    """CRC-16/XMODEM 校验算法"""
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


def build_frame(cmd: int, payload: bytes = b'') -> bytes:
    """
    构建数据帧
    帧格式: AA 55 | VER | CMD | LEN(2B) | PAYLOAD | CRC(2B)
    """
    len_payload = len(payload)
    header = b'\xAA\x55'
    data_for_crc = struct.pack('<BBH', PROTO_VER, cmd, len_payload) + payload
    crc = crc16_xmodem(data_for_crc)
    return header + data_for_crc + struct.pack('<H', crc)


def parse_frame(buffer: bytes):
    """
    从缓冲区解析一帧数据
    
    Returns:
        tuple: (new_buffer, result)
        - new_buffer: 更新后的缓冲区
        - result: 
            None: 数据不足
            False: CRC校验失败
            dict: {'cmd': int, 'payload': bytes, 'ver': int}
    """
    # 查找帧头
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
    
    # CRC 校验
    data_to_check = frame[2:6+payload_len]
    received_crc = struct.unpack('<H', frame[6+payload_len:])[0]
    calculated_crc = crc16_xmodem(data_to_check)
    
    if received_crc != calculated_crc:
        return new_buffer, False
        
    proto_ver, cmd, _ = struct.unpack('<BBH', frame[2:6])
    payload = frame[6:6+payload_len]
    
    return new_buffer, {'cmd': cmd, 'payload': payload, 'ver': proto_ver}
