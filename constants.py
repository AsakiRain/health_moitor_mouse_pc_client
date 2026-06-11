# --- Protocol Constants ---
PROTO_VER = 2
# PC to Device
CMD_PING = 0x01
CMD_SYNC_TIME = 0x10
CMD_START_HEALTH_CHECK = 0x20
CMD_GET_LAST_HEALTH_DATA = 0x21
CMD_GET_MOUSE_DATA = 0x22
CMD_DEVICE_STATUS_CHECK = 0x23
CMD_SET_HEALTH_CHECK_DURATION = 0x24  # 设置健康检测时长(秒)
CMD_GET_MOUSE_SETTINGS = 0x25
CMD_SET_MOUSE_SETTINGS = 0x26
CMD_TEST_VIBRATION = 0x27
CMD_SET_HEALTH_PUSH = 0x28
# Device to PC
CMD_ACK = 0x7F
CMD_NOTIFY_HEALTH_DATA_READY = 0x80
CMD_SYNC_DATA_START = 0x81
CMD_SYNC_DATA_BATCH = 0x82
CMD_SYNC_DATA_END = 0x83
CMD_DEVICE_LOG = 0x84

# Sync Protocol
CMD_SYNC_HEALTH_DATA = 0x30

# ACK Status Codes
ACK_SUCCESS = 0
ACK_UNKNOWN_CMD = 1
ACK_DEVICE_BUSY = 2

# --- UI Tooltips ---
HEALTH_METRICS_TOOLTIPS = {
    'heartrate': '成人静息心率正常值为60-100 bpm（每分钟心跳次数），但受年龄、活动状态影响，专业运动员的静止心率可能会较低。',
    'spo2': '血氧饱和度，单位为百分比（%）。健康成人的正常血氧饱和度应介于 95% 至 100% 之间，低于90%可能表示缺氧。',
    'bk': '指血液在最微小的血管（如微动脉、微静脉、毛细血管）中的流动状态。它对于组织的氧气与养分输送、废物移除至关重要。',
    'fatigue': '疲劳指数通常为0-100（越高越疲劳）。',
    'systolic': '血压读数中的较高值，代表心脏收缩将血液泵出时，动脉内所承受的最大压力。成人的正常收缩压通常应低于 120 mmHg。',
    'diastolic': '血压读数中的较低值，代表心脏在两次跳动之间处于舒张状态时，动脉内所承受的压力。成人的正常舒张压通常应低于 80 mmHg。',
    'cardiac': '指心脏每分钟泵出的血液总量，是衡量心脏泵血效率的关键指标。成人在休息状态下，正常心输出量约为每分钟 4 至 8 升。',
    'resistance': '指血液在循环系统中流动时必须克服的阻力，主要受到血管收缩或扩张的影响。'
}
