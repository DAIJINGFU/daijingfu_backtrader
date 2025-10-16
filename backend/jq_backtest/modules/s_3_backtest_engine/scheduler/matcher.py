"""
时间匹配引擎：判断任务是否应在当前时间触发
"""

def should_trigger(current_dt_str, task):
    """判断任务是否应在当前时间触发
    Args:
        current_dt_str: "YYYY-MM-DD HH:MM:SS"
        task: 任务字典
    Returns:
        bool
    """
    from datetime import datetime
    current_dt = datetime.strptime(current_dt_str, '%Y-%m-%d %H:%M:%S')
    target_time = task['time']  # "09:30"
    hour, minute = map(int, target_time.split(':'))
    if current_dt.hour != hour or current_dt.minute != minute:
        return False
    if task['freq'] == 'daily':
        return True
    elif task['freq'] == 'weekly':
        return current_dt.weekday() == 0  # 周一
    elif task['freq'] == 'monthly':
        return current_dt.day == 1  # 每月1日
    return False

