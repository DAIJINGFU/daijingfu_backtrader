"""
任务队列管理：注册与存储调度任务
"""

def register_task(jq_state, freq, time_str, func):
    """注册定时任务到队列
    Args:
        freq: 'daily' / 'weekly' / 'monthly'
        time_str: "HH:MM" 格式
        func: 用户回调函数
    """
    if '_scheduler' not in jq_state:
        jq_state['_scheduler'] = {'tasks': []}
    jq_state['_scheduler']['tasks'].append({
        'freq': freq,
        'time': time_str,
        'func': func,
        'last_trigger': None
    })
