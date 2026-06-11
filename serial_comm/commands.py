"""
串口命令构建器

提供命令帧构建的便捷方法。
注意：当前版本中 MainWindow 直接使用 SerialWorker.send_frame()，
此模块作为未来重构的基础设施保留。
"""
import struct
import time

from core.protocol import build_frame
from constants import (
    PROTO_VER, CMD_ACK,
    CMD_GET_LAST_HEALTH_DATA, CMD_GET_MOUSE_DATA,
    CMD_SYNC_TIME, CMD_PING, CMD_SYNC_HEALTH_DATA
)


class SerialCommands:
    """
    串口命令构建器
    
    封装所有发送到设备的命令，使用 core.protocol.build_frame 构建帧
    """
    
    @staticmethod
    def build_ack(cmd: int) -> bytes:
        """构建 ACK 帧"""
        return build_frame(CMD_ACK, struct.pack('<B', cmd))
    
    @staticmethod
    def build_ping() -> bytes:
        """构建 PING 帧"""
        return build_frame(CMD_PING, b'')
    
    @staticmethod
    def build_health_data_request() -> bytes:
        """构建健康数据请求帧"""
        return build_frame(CMD_GET_LAST_HEALTH_DATA, b'')
    
    @staticmethod
    def build_mouse_data_request() -> bytes:
        """构建鼠标数据请求帧"""
        return build_frame(CMD_GET_MOUSE_DATA, b'')
    
    @staticmethod
    def build_sync_request(last_record_id: int = 0) -> bytes:
        """
        构建数据同步请求帧
        
        Args:
            last_record_id: 已保存的最大设备记录 ID，设备返回该 ID 之后的数据
        """
        return build_frame(CMD_SYNC_HEALTH_DATA, struct.pack('<I', last_record_id))
    
    @staticmethod
    def build_time_sync(force: bool = False) -> bytes:
        """
        构建时间同步帧
        
        Args:
            force: 是否强制同步
        """
        timestamp = time.time()
        
        # 获取本地时区偏移量（秒）
        if time.daylight and time.localtime().tm_isdst:
            timezone_offset = -time.altzone
        else:
            timezone_offset = -time.timezone
        
        if force:
            payload = struct.pack('<diB', timestamp, timezone_offset, 1)
        else:
            payload = struct.pack('<di', timestamp, timezone_offset)
        
        return build_frame(CMD_SYNC_TIME, payload)
