"""
生命周期钩子注册与触发
"""

def register_lifecycle_task(jq_state, hook, func):
    """
    注册生命周期钩子任务到队列
    hook: 'before_trading_start' | 'after_trading_end'
    func: 用户回调函数
    """
    if '_scheduler' not in jq_state:
        jq_state['_scheduler'] = {'tasks': [], 'lifecycle': {}}
    if 'lifecycle' not in jq_state['_scheduler']:
        jq_state['_scheduler']['lifecycle'] = {}
    if hook not in jq_state['_scheduler']['lifecycle']:
        jq_state['_scheduler']['lifecycle'][hook] = []
    jq_state['_scheduler']['lifecycle'][hook].append(func)

def trigger_lifecycle_tasks(jq_state, hook, context):
    """
    触发指定生命周期钩子上的所有任务
    hook: 'before_trading_start' | 'after_trading_end'
    """
    tasks = jq_state.get('_scheduler', {}).get('lifecycle', {}).get(hook, [])
    for func in tasks:
        try:
            func(context)
        except Exception as e:
            if 'log' in jq_state:
                jq_state['log'].append(f"[Lifecycle] {hook} error: {e}")
            else:
                print(f"[Lifecycle] {hook} error: {e}")
