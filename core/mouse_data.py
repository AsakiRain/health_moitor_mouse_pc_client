"""
鼠标数据处理模块
"""
import struct
from dataclasses import dataclass


@dataclass
class MouseStatistics:
    """鼠标统计数据"""
    total_distance_um: int  # 总移动距离（微米）
    left_click: int
    right_click: int
    mid_click: int
    session_time: int       # 会话时间（秒）
    last_save_time: int     # 上次保存时间戳
    back_click: int = 0
    forward_click: int = 0
    
    @classmethod
    def from_bytes(cls, payload: bytes) -> 'MouseStatistics':
        """
        从设备发送的 payload 解析鼠标统计数据
        格式: <QIIIIIII> (36字节)
        """
        expected_len = 36
        if len(payload) != expected_len:
            raise ValueError(f"鼠标数据长度不正确: {len(payload)}, 期望 {expected_len}")
        
        total_distance_um, left, right, mid, back, forward, session_time, last_save_time = struct.unpack(
            '<QIIIIIII', payload
        )
        
        return cls(
            total_distance_um=int(total_distance_um),
            left_click=int(left),
            right_click=int(right),
            mid_click=int(mid),
            back_click=int(back),
            forward_click=int(forward),
            session_time=int(session_time),
            last_save_time=int(last_save_time)
        )
    
    @property
    def distance_meters(self) -> float:
        """距离转换为米"""
        return float(self.total_distance_um) / 1_000_000.0
    
    @property
    def distance_str(self) -> str:
        """距离的字符串表示"""
        return f"{self.distance_meters:.3f} 米"
    
    @property
    def session_time_str(self) -> str:
        """会话时间的可读字符串"""
        hours = self.session_time // 3600
        minutes = (self.session_time % 3600) // 60
        secs = self.session_time % 60
        if hours > 0:
            return f"{hours}时{minutes}分{secs}秒"
        elif minutes > 0:
            return f"{minutes}分{secs}秒"
        else:
            return f"{secs}秒"


class MouseDataProcessor:
    """鼠标数据处理器"""
    
    def __init__(self, db_handler=None):
        self.db_handler = db_handler
    
    def parse_payload(self, payload: bytes) -> MouseStatistics:
        """解析设备发送的鼠标数据"""
        return MouseStatistics.from_bytes(payload)
    
    def distance_to_meters_str(self, micrometers: int) -> str:
        """将微米距离转换为米的字符串"""
        meters = float(micrometers) / 1_000_000.0
        return f"{meters:.3f} 米"
    
    def process_payload(self, payload: bytes) -> dict:
        """处理设备发送的鼠标数据，保存到数据库并返回结果"""
        stats = self.parse_payload(payload)
        
        # 保存到数据库
        if self.db_handler:
            self.db_handler.save_mouse_data(
                stats.total_distance_um,
                stats.left_click,
                stats.mid_click,
                stats.right_click,
                stats.back_click,
                stats.forward_click
            )
        
        return {
            'distance_um': stats.total_distance_um,
            'left_click': stats.left_click,
            'mid_click': stats.mid_click,
            'right_click': stats.right_click,
            'back_click': stats.back_click,
            'forward_click': stats.forward_click,
            'session_time': stats.session_time,
            'last_save_time': stats.last_save_time,
            'distance_m_str': stats.distance_str,
            'session_time_str': stats.session_time_str,
        }
