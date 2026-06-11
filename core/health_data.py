"""
健康数据模型
- HealthRecord: 健康数据记录
- 统一的数据解析逻辑
"""
import struct
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Dict, Any

# 健康数据记录大小：原始健康数据 91 bytes + record_id 4 bytes
HEALTH_RECORD_SIZE = 95

# 健康数据字段名列表（与设备端一致）
METRIC_KEYS = [
    'acdata',       # 心律波形 64字节 BLOB
    'heartrate', 'spo2', 'bk', 'fatigue',
    'rsv1', 'rsv2', # 协议保留
    'systolic', 'diastolic', 'cardiac', 'resistance',
    'rr_interval', 'sdnn', 'rmssd', 'nn50', 'pnn50',
    'rra',          # 最近RR间期 6字节 BLOB
    'rsv3', 'state',
    'timestamp',    # 设备端时间戳
    'record_id'     # 设备端单调自增记录 ID
]


@dataclass
class HealthRecord:
    """健康数据记录"""
    acdata: bytes           # 64 bytes 波形数据
    heartrate: int
    spo2: int
    bk: int                 # 微循环
    fatigue: int
    rsv1: int               # 协议保留
    rsv2: int               # 协议保留
    systolic: int           # 收缩压
    diastolic: int          # 舒张压
    cardiac: int            # 心输出
    resistance: int         # 外周阻力
    rr_interval: int
    sdnn: int
    rmssd: int
    nn50: int
    pnn50: int
    rra: bytes              # 6 bytes RR间期数组
    rsv3: int               # 协议保留
    state: int              # 模块状态
    timestamp: int          # Unix 时间戳
    record_id: int          # 设备端单调自增记录 ID
    
    @classmethod
    def from_bytes(cls, data: bytes) -> 'HealthRecord':
        """从 95 字节数据解析 HealthRecord"""
        if len(data) != HEALTH_RECORD_SIZE:
            raise ValueError(f"数据长度错误: 期望 {HEALTH_RECORD_SIZE}, 实际 {len(data)}")
        
        acdata = data[0:64]
        metrics = data[64:79]
        rra = data[79:85]
        rsv3 = data[85]
        state = data[86]
        timestamp = struct.unpack('<I', data[87:91])[0]
        record_id = struct.unpack('<I', data[91:95])[0]
        
        hr, spo2, bk, fatigue, rsv1, rsv2, systolic, diastolic, cardiac, \
        resistance, rr_interval, sdnn, rmssd, nn50, pnn50 = struct.unpack('<15B', metrics)
        
        return cls(
            acdata=acdata,
            heartrate=hr,
            spo2=spo2,
            bk=bk,
            fatigue=fatigue,
            rsv1=rsv1,
            rsv2=rsv2,
            systolic=systolic,
            diastolic=diastolic,
            cardiac=cardiac,
            resistance=resistance,
            rr_interval=rr_interval,
            sdnn=sdnn,
            rmssd=rmssd,
            nn50=nn50,
            pnn50=pnn50,
            rra=rra,
            rsv3=rsv3,
            state=state,
            timestamp=timestamp,
            record_id=record_id
        )
    
    def to_list(self) -> list:
        """转换为列表（用于数据库插入，顺序与 METRIC_KEYS 对应）"""
        return [
            self.acdata, self.heartrate, self.spo2, self.bk, self.fatigue,
            self.rsv1, self.rsv2, self.systolic, self.diastolic, self.cardiac,
            self.resistance, self.rr_interval, self.sdnn, self.rmssd,
            self.nn50, self.pnn50, self.rra, self.rsv3, self.state, self.timestamp,
            self.record_id
        ]
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            'acdata': self.acdata,
            'heartrate': self.heartrate,
            'spo2': self.spo2,
            'bk': self.bk,
            'fatigue': self.fatigue,
            'rsv1': self.rsv1,
            'rsv2': self.rsv2,
            'systolic': self.systolic,
            'diastolic': self.diastolic,
            'cardiac': self.cardiac,
            'resistance': self.resistance,
            'rr_interval': self.rr_interval,
            'sdnn': self.sdnn,
            'rmssd': self.rmssd,
            'nn50': self.nn50,
            'pnn50': self.pnn50,
            'rra': self.rra,
            'rsv3': self.rsv3,
            'state': self.state,
            'timestamp': self.timestamp,
            'record_id': self.record_id
        }
    
    @property
    def created_at(self) -> str:
        """获取格式化的时间字符串；设备无 RTC 时 timestamp 为 0，回退到 PC 当前时间"""
        if not self.timestamp:
            return datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        try:
            return datetime.fromtimestamp(self.timestamp).strftime('%Y-%m-%d %H:%M:%S')
        except (OSError, ValueError):
            return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


class StatTracker:
    """统计器：用于计算去极值平均"""
    def __init__(self):
        self.sum = 0
        self.count = 0
        self.min_val = float('inf')
        self.max_val = 0
    
    def add(self, val: int):
        if val == 0:
            return
        self.sum += val
        self.count += 1
        if val < self.min_val:
            self.min_val = val
        if val > self.max_val:
            self.max_val = val
    
    def get_avg(self) -> int:
        """获取去极值平均"""
        if self.count == 0:
            return 0
        if self.count <= 2:
            return self.sum // self.count
        return (self.sum - self.max_val - int(self.min_val)) // (self.count - 2)


def calculate_averaged_metrics(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    计算健康指标的去极值平均
    
    Args:
        records: 健康数据记录列表（字典格式）
    
    Returns:
        包含平均值的字典
    """
    if not records:
        return None
    
    sum_heartrate, cnt_heartrate = 0, 0
    sum_spo2, cnt_spo2 = 0, 0
    st_bk = StatTracker()
    st_fatigue = StatTracker()
    st_systolic = StatTracker()
    st_diastolic = StatTracker()
    st_cardiac = StatTracker()
    st_resistance = StatTracker()
    st_rr_interval = StatTracker()
    st_sdnn = StatTracker()
    st_rmssd = StatTracker()
    st_nn50 = StatTracker()
    st_pnn50 = StatTracker()
    max_timestamp = None
    valid_count = 0
    
    for row in records:
        heartrate = row.get('heartrate', 0)
        spo2 = row.get('spo2', 0)
        
        # 跳过无效记录
        if heartrate == 0 or spo2 == 0:
            continue
        
        if max_timestamp is None:
            max_timestamp = row.get('created_at')
        
        valid_count += 1
        
        sum_heartrate += heartrate
        cnt_heartrate += 1
        sum_spo2 += spo2
        cnt_spo2 += 1
        
        st_bk.add(row.get('bk', 0))
        st_fatigue.add(row.get('fatigue', 0))
        st_systolic.add(row.get('systolic', 0))
        st_diastolic.add(row.get('diastolic', 0))
        st_cardiac.add(row.get('cardiac', 0))
        st_resistance.add(row.get('resistance', 0))
        st_rr_interval.add(row.get('rr_interval', 0))
        st_sdnn.add(row.get('sdnn', 0))
        st_rmssd.add(row.get('rmssd', 0))
        st_nn50.add(row.get('nn50', 0))
        st_pnn50.add(row.get('pnn50', 0))
    
    if valid_count == 0:
        return None
    
    return {
        'created_at': max_timestamp,
        'heartrate': sum_heartrate // cnt_heartrate if cnt_heartrate else 0,
        'spo2': sum_spo2 // cnt_spo2 if cnt_spo2 else 0,
        'bk': st_bk.get_avg(),
        'fatigue': st_fatigue.get_avg(),
        'systolic': st_systolic.get_avg(),
        'diastolic': st_diastolic.get_avg(),
        'cardiac': st_cardiac.get_avg(),
        'resistance': st_resistance.get_avg(),
        'rr_interval': st_rr_interval.get_avg(),
        'sdnn': st_sdnn.get_avg(),
        'rmssd': st_rmssd.get_avg(),
        'nn50': st_nn50.get_avg(),
        'pnn50': st_pnn50.get_avg(),
        '_valid_count': valid_count
    }
