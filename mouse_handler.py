import struct


class MouseDataProcessor:
    """
    负责解析设备鼠标数据 payload，并持久化累计值。
    设备发送的距离单位为微米，界面展示转换为米，保留三位小数。
    
    设备数据结构 (MouseStatistics):
    - totalDistance: uint64_t (8字节) - 总移动距离（微米）
    - leftClickCount: uint32_t (4字节) - 左键点击次数
    - rightClickCount: uint32_t (4字节) - 右键点击次数
    - middleClickCount: uint32_t (4字节) - 中键点击次数
    - backClickCount: uint32_t (4字节) - 后退侧键点击次数
    - forwardClickCount: uint32_t (4字节) - 前进侧键点击次数
    - sessionTime: uint32_t (4字节) - 会话时间（秒）
    - lastSaveTime: uint32_t (4字节) - 上次保存时间戳
    """

    def __init__(self, db_handler):
        self.db_handler = db_handler

    def parse_payload(self, payload: bytes) -> dict:
        """
        解析设备发送的鼠标统计数据。
        格式: <QIIIIIII> (36字节)
        - Q: totalDistance (uint64_t, 微米)
        - I: leftClickCount (uint32_t)
        - I: rightClickCount (uint32_t)
        - I: middleClickCount (uint32_t)
        - I: sessionTime (uint32_t, 秒)
        - I: lastSaveTime (uint32_t, 时间戳)
        """
        expected_len = 36
        if len(payload) != expected_len:
            raise ValueError(f"鼠标数据 payload 长度不正确: {len(payload)}，期望 {expected_len} 字节")
        
        total_distance_um, left, right, mid, back, forward, session_time, last_save_time = struct.unpack(
            '<QIIIIIII', payload
        )
        
        return {
            'total_distance_um': int(total_distance_um),  # 微米
            'left_click': int(left),
            'right_click': int(right),
            'mid_click': int(mid),
            'back_click': int(back),
            'forward_click': int(forward),
            'session_time': int(session_time),  # 秒
            'last_save_time': int(last_save_time),  # 时间戳
        }

    def micrometers_to_meters(self, micrometers: int) -> float:
        """将微米转换为米"""
        return float(micrometers) / 1_000_000.0

    def distance_to_meters_str(self, micrometers: int) -> str:
        """将微米距离转换为米的字符串表示"""
        meters = self.micrometers_to_meters(micrometers)
        return f"{meters:.3f} 米"

    def session_time_to_str(self, seconds: int) -> str:
        """将会话时间（秒）转换为可读字符串"""
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        if hours > 0:
            return f"{hours}时{minutes}分{secs}秒"
        elif minutes > 0:
            return f"{minutes}分{secs}秒"
        else:
            return f"{secs}秒"

    def process_payload(self, payload: bytes) -> dict:
        """处理设备发送的鼠标数据，保存到数据库并返回处理结果"""
        data = self.parse_payload(payload)
        
        # 落库（使用微米作为距离单位）
        self.db_handler.save_or_update_mouse_data(
            data['total_distance_um'],
            data['left_click'],
            data['mid_click'],
            data['right_click'],
            data['back_click'],
            data['forward_click']
        )
        
        return {
            'distance_um': data['total_distance_um'],
            'left_click': data['left_click'],
            'mid_click': data['mid_click'],
            'right_click': data['right_click'],
            'back_click': data['back_click'],
            'forward_click': data['forward_click'],
            'session_time': data['session_time'],
            'last_save_time': data['last_save_time'],
            'distance_m_str': self.distance_to_meters_str(data['total_distance_um']),
            'session_time_str': self.session_time_to_str(data['session_time']),
        }


