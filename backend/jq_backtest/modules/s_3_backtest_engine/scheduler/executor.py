"""
调度执行器：遍历队列并执行到期任务
"""

def execute_pending_tasks(jq_state, context, data):
    """遍历队列并执行到期任务
    Args:
        jq_state: 全局状态字典
        context: 策略上下文
        data: 数据对象
    """
    tasks = jq_state.get('_scheduler', {}).get('tasks', [])
    current_dt = jq_state.get('current_dt')
    # 轻量日志，便于确认当前时间与任务数
    try:
        if jq_state.get('options', {}).get('scheduler_debug'):
            jq_state.setdefault('log', []).append(f"[Scheduler] tick dt={current_dt} tasks={len(tasks)}")
    except Exception:
        pass
    from .matcher import should_trigger
    for task in tasks:
        try:
            match = should_trigger(current_dt, task)
        except Exception as e:
            match = False
            if 'log' in jq_state:
                jq_state['log'].append(f"[Scheduler] matcher error: {e}")
        if match:
            # 避免重复触发
            if task.get('last_trigger') == current_dt:
                continue
            try:
                task['func'](context)
                task['last_trigger'] = current_dt
                try:
                    if jq_state.get('options', {}).get('scheduler_debug'):
                        jq_state.setdefault('log', []).append(f"[Scheduler] fired {task.get('freq')}@{task.get('time')} -> last={task.get('last_trigger')}")
                except Exception:
                    pass
            except Exception as e:
                if 'log' in jq_state:
                    jq_state['log'].append(f"[Scheduler] Task error: {e}")
                else:
                    print(f"[Scheduler] Task error: {e}")

