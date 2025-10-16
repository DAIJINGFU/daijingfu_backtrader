"""策略编译器：执行用户脚本并构建聚宽兼容的 Backtrader 策略类。"""

from __future__ import annotations

import sys
import types
from typing import Callable

import backtrader as bt

from backend.modules.s_1_strategy_compile.jq_environment import (
	ALLOWED_GLOBALS,
	build_jq_compat_env,
	limited_import,
)

from . import jq_api as _jq_api

__all__ = ["compile_user_strategy"]


ALLOWED_GLOBALS["__builtins__"]["__import__"] = limited_import


def compile_user_strategy(code: str):
	"""执行用户策略代码，支持两种模式：
	1) 标准 backtrader 模式: 用户提供 UserStrategy 类。
	2) 聚宽兼容模式: 提供 initialize(context), handle_data(context, data) 函数与可选 g.security。
	"""

	sanitized = []
	for line in code.splitlines():
		if line.strip().startswith("import jqdata"):
			continue
		sanitized.append(line)
	code = "\n".join(sanitized)

	module_name = "user_module"
	sys.modules.pop(module_name, None)
	module = types.ModuleType(module_name)
	sys.modules[module_name] = module
	exec_env = dict(ALLOWED_GLOBALS)
	jq_state = build_jq_compat_env(exec_env)

	for key, value in exec_env.items():
		if key not in module.__dict__:
			module.__dict__[key] = value

	exec(code, module.__dict__, module.__dict__)

	exec_env = module.__dict__

	if "UserStrategy" in module.__dict__:
		return module.__dict__["UserStrategy"], jq_state

	if "initialize" in module.__dict__:
		init_func: Callable = module.__dict__["initialize"]
		handle_func: Callable = module.__dict__.get("handle_data")
		if handle_func is None:

			def _noop_handle(context, data):
				return None

			module.__dict__["handle_data"] = _noop_handle
			handle_func = _noop_handle
			try:
				jq_state.setdefault("log", []).append(
					"[compat] missing handle_data -> injected no-op for scheduler/lifecycle-only strategy"
				)
			except Exception:
				pass

		class UserStrategy(bt.Strategy):  # type: ignore
			def __init__(self):

				class _Portfolio:
					@property
					def available_cash(inner_self):
						return self.broker.getcash()

					@property
					def positions(inner_self):
						total_amount = int(self.position.size)
						current_date = jq_state.get("current_dt", "").split(" ")[0]
						today_bought = jq_state.get("_daily_bought", {}).get(current_date, 0)
						closeable = max(0, total_amount - today_bought)

						return {
							getattr(jq_state["g"], "security", "data0"): types.SimpleNamespace(
								closeable_amount=closeable,
								total_amount=total_amount,
							)
						}

				class _Context:
					portfolio = _Portfolio()

					@property
					def current_dt(inner_self):
						try:
							import datetime as dt_module

							current_dt_str = jq_state.get("current_dt", "")
							if current_dt_str:
								return dt_module.datetime.strptime(current_dt_str, "%Y-%m-%d %H:%M:%S")
							return bt.num2date(self.data.datetime[0])
						except Exception:
							return bt.num2date(self.data.datetime[0])

				self._jq_context = _Context()
				try:
					self._exec_env = globals().get("exec_env") or exec_env
				except Exception:
					self._exec_env = {"jq_state": jq_state}
				try:
					jq_state["_strategy_instance"] = self
				except Exception:
					pass
				init_func(self._jq_context)

			def prenext(self):
				self.next()

			def _run_handle(self):
				exec_env = getattr(self, "_exec_env", None) or {}
				jq_state_local = exec_env.get("jq_state", {}) if isinstance(exec_env, dict) else {}
				if isinstance(jq_state_local, dict):
					jq_state_local["_strategy_instance"] = self

				if isinstance(exec_env, dict) and "get_price" not in exec_env:

					def get_price(
						security,
						start_date=None,
						end_date=None,
						*,
						frequency: str = "daily",
						fields=None,
						count=None,
						skip_paused: bool = False,
						fq: str = "pre",
						panel: bool = False,
						fill_paused: bool = True,
					):
						jqst_local = exec_env.get("jq_state") if isinstance(exec_env, dict) else None
						return _jq_api.get_price(
							security,
							start_date=start_date,
							end_date=end_date,
							frequency=frequency,
							fields=fields,
							count=count,
							skip_paused=skip_paused,
							fq=fq,
							panel=panel,
							fill_paused=fill_paused,
							jq_state=jqst_local,
						)

					exec_env["get_price"] = get_price

				if isinstance(exec_env, dict) and "history" not in exec_env:

					def history(
						count: int,
						unit: str = "1d",
						field: str = "avg",
						security_list=None,
						df: bool = True,
						skip_paused: bool = False,
						fq: str = "pre",
					):
						jqst_local = exec_env.get("jq_state") if isinstance(exec_env, dict) else None
						return _jq_api.history(
							count=count,
							unit=unit,
							field=field,
							security_list=security_list,
							df=df,
							skip_paused=skip_paused,
							fq=fq,
							jq_state=jqst_local,
						)

					exec_env["history"] = history

				try:
					if jq_state_local.get("corporate_actions"):
						cur_dt = bt.num2date(self.data.datetime[0]).date().isoformat()
						todays = [e for e in jq_state_local["corporate_actions"] if e.date == cur_dt]
						if todays:
							logger = jq_state_local.get("logger")
							for ev in todays:
								from backend.modules.utils.corporate_actions import apply_event as _apply_ca

								manual_override = getattr(ev, "_manual_shares", None)
								if manual_override not in (None, 0):
									delta = int(manual_override)
									try:
										if logger:
											logger.info(
												f"[ca_manual_apply] date={ev.date} type={ev.action_type} delta={delta}"
											)
									except Exception:
										pass
									if delta > 0:
										self.buy(size=delta)
									elif delta < 0:
										self.sell(size=abs(delta))
								else:
									res = _apply_ca(ev, self.position, self.broker, logger=logger)
									if res and isinstance(res, tuple):
										tag, payload = res
										if tag in ("BONUS_SHARES", "SPLIT_ADJ") and isinstance(payload, int) and payload != 0:
											if payload > 0:
												self.buy(size=payload)
											else:
												self.sell(size=abs(payload))
				except Exception:
					pass

				def attribute_history(security, count, unit="1d", fields=None, skip_paused=True, df=True, fq="pre"):
					jqst_local = exec_env.get("jq_state") if isinstance(exec_env, dict) else None
					return _jq_api.attribute_history(
						security,
						count=count,
						unit=unit,
						fields=fields,
						skip_paused=skip_paused,
						df=df,
						fq=fq,
						jq_state=jqst_local,
					)

				def order_value(security: str, value: float):
					jqst_local = exec_env.get("jq_state") if isinstance(exec_env, dict) else None
					return _jq_api.order_value(
						security,
						value,
						jq_state=jqst_local,
						bt_strategy=self,
					)

				def order_target(security: str, target: float):
					jqst_local = exec_env.get("jq_state") if isinstance(exec_env, dict) else None
					return _jq_api.order_target(
						security,
						target,
						jq_state=jqst_local,
						bt_strategy=self,
					)

				def order(security: str, amount: int):
					jqst_local = exec_env.get("jq_state") if isinstance(exec_env, dict) else None
					return _jq_api.order(
						security,
						amount,
						jq_state=jqst_local,
						bt_strategy=self,
					)

				def order_target_value(security: str, value: float):
					jqst_local = exec_env.get("jq_state") if isinstance(exec_env, dict) else None
					return _jq_api.order_target_value(
						security,
						value,
						jq_state=jqst_local,
						bt_strategy=self,
					)

				def order_target_percent(security: str, percent: float):
					jqst_local = exec_env.get("jq_state") if isinstance(exec_env, dict) else None
					return _jq_api.order_target_percent(
						security,
						percent,
						jq_state=jqst_local,
						bt_strategy=self,
					)

				try:
					exec_env["attribute_history"] = attribute_history
					exec_env["order"] = order
					exec_env["order_value"] = order_value
					exec_env["order_target"] = order_target
					exec_env["order_target_value"] = order_target_value
					exec_env["order_target_percent"] = order_target_percent
				except Exception:
					pass

				try:
					fp_mode = str(exec_env.get("jq_state", {}).get("options", {}).get("fill_price", "open")).lower()
				except Exception:
					fp_mode = "open"
				self._fill_price_mode = fp_mode
				self._run_on_open = fp_mode != "close"
				self._handled_today = False
				try:
					if exec_env.get("jq_state", {}).get("options", {}).get("flow_debug"):
						exec_env["jq_state"]["log"].append(
							f"[exec_mode] run_on_open={self._run_on_open} fill_price={fp_mode}"
						)
				except Exception:
					pass
				try:
					handle_func(self._jq_context, None)
				except Exception as _e:
					try:
						exec_env["log"].info(f"[handle_data_error] {type(_e).__name__}:{_e}")
					except Exception:
						pass

			def next_open(self):  # type: ignore
				if not getattr(self, "_run_on_open", True):
					return
				try:
					jq_state_local = self._exec_env.get("jq_state") if hasattr(self, "_exec_env") else None
					if isinstance(jq_state_local, dict):
						try:
							if jq_state_local.get("options", {}).get("flow_debug"):
								jq_state_local.setdefault("log", []).append("[debug] next_open: enter")
						except Exception:
							pass
						cur_dt_dt = bt.num2date(self.data.datetime[0])
						cur_date_obj = cur_dt_dt.date()
						cur_dt = cur_date_obj.isoformat()
						freq_str = str(jq_state_local.get("options", {}).get("api_frequency") or "").lower()
						if freq_str in {"1min", "minute", "1m", "intraday"}:
							jq_state_local["current_dt"] = cur_dt_dt.strftime("%Y-%m-%d %H:%M:%S")
						else:
							jq_state_local["current_dt"] = f"{cur_dt} 09:30:00"
						try:
							if jq_state_local.get("options", {}).get("flow_debug"):
								jq_state_local.setdefault("log", []).append(
									f"[debug] next_open: set current_dt={jq_state_local['current_dt']}"
								)
						except Exception:
							pass
						user_start = jq_state_local.get("user_start")
						in_warmup_before = jq_state_local.get("in_warmup")
						if isinstance(user_start, str):
							try:
								from datetime import date as _d

								start_date_obj = _d.fromisoformat(user_start)
								jq_state_local["in_warmup"] = cur_date_obj < start_date_obj
							except Exception:
								jq_state_local["in_warmup"] = cur_dt < user_start
						else:
							jq_state_local["in_warmup"] = False
						if jq_state_local["in_warmup"] and not in_warmup_before:
							try:
								jq_state_local["log"].append(
									f"[warmup] enter_warmup cur={cur_dt} start={user_start}"
								)
							except Exception:
								pass
						if (not jq_state_local["in_warmup"]) and in_warmup_before:
							try:
								jq_state_local["log"].append(
									f"[warmup] leave_warmup cur={cur_dt} start={user_start}"
								)
							except Exception:
								pass
						if jq_state_local["in_warmup"]:
							return
				except Exception:
					pass
				try:
					try:
						from backend.modules.s_3_backtest_engine.scheduler.lifecycle import trigger_lifecycle_tasks

						jq_state_local = self._exec_env.get("jq_state") if hasattr(self, "_exec_env") else None
						if jq_state_local:
							trigger_lifecycle_tasks(jq_state_local, "before_trading_start", self._jq_context)
					except Exception:
						pass
					try:
						from backend.modules.s_3_backtest_engine.scheduler.executor import execute_pending_tasks

						jq_state_local = self._exec_env.get("jq_state") if hasattr(self, "_exec_env") else None
						if jq_state_local:
							execute_pending_tasks(jq_state_local, self._jq_context, self.data)
					except Exception:
						pass
					self._run_handle()
					self._handled_today = True
				except Exception:
					pass

			def next(self):
				if getattr(self, "_run_on_open", True) and getattr(self, "_handled_today", False):
					try:
						jq_state_local = self._exec_env.get("jq_state") if hasattr(self, "_exec_env") else None
						if isinstance(jq_state_local, dict):
							cur_dt_dt = bt.num2date(self.data.datetime[0])
							cur_date_obj = cur_dt_dt.date()
							cur_dt = cur_date_obj.isoformat()
							freq_str = str(jq_state_local.get("options", {}).get("api_frequency") or "").lower()
							if freq_str in {"1min", "minute", "1m", "intraday"}:
								jq_state_local["current_dt"] = cur_dt_dt.strftime("%Y-%m-%d %H:%M:%S")
							else:
								jq_state_local["current_dt"] = f"{cur_dt} 09:30:00"
							last_after = jq_state_local.get("_after_fired_date")
							if last_after != cur_dt:
								try:
									from backend.modules.s_3_backtest_engine.scheduler.lifecycle import trigger_lifecycle_tasks

									trigger_lifecycle_tasks(jq_state_local, "after_trading_end", self._jq_context)
								except Exception:
									pass
								jq_state_local["_after_fired_date"] = cur_dt
					except Exception:
						pass
					return
				try:
					jq_state_local = self._exec_env.get("jq_state") if hasattr(self, "_exec_env") else None
					if isinstance(jq_state_local, dict):
						try:
							if jq_state_local.get("options", {}).get("flow_debug"):
								jq_state_local.setdefault("log", []).append("[debug] next: enter")
						except Exception:
							pass
						cur_dt_dt = bt.num2date(self.data.datetime[0])
						cur_date_obj = cur_dt_dt.date()
						cur_dt = cur_date_obj.isoformat()
						freq_str = str(jq_state_local.get("options", {}).get("api_frequency") or "").lower()
						if freq_str in {"1min", "minute", "1m", "intraday"}:
							jq_state_local["current_dt"] = cur_dt_dt.strftime("%Y-%m-%d %H:%M:%S")
						else:
							jq_state_local["current_dt"] = f"{cur_dt} 09:30:00"
						if "_daily_bought" in jq_state_local:
							try:
								from datetime import datetime, timedelta

								current_date_obj = datetime.strptime(cur_dt, "%Y-%m-%d")
								cutoff_date = (current_date_obj - timedelta(days=2)).strftime("%Y-%m-%d")
								keys_to_delete = [
									k for k in jq_state_local["_daily_bought"].keys() if k < cutoff_date
								]
								for k in keys_to_delete:
									del jq_state_local["_daily_bought"][k]
							except Exception:
								pass
						user_start = jq_state_local.get("user_start")
						in_warmup_before = jq_state_local.get("in_warmup")
						if isinstance(user_start, str):
							try:
								from datetime import date as _d

								start_date_obj = _d.fromisoformat(user_start)
								jq_state_local["in_warmup"] = cur_date_obj < start_date_obj
							except Exception:
								jq_state_local["in_warmup"] = cur_dt < user_start
						else:
							jq_state_local["in_warmup"] = False
						if jq_state_local["in_warmup"] and not in_warmup_before:
							try:
								jq_state_local["log"].append(
									f"[warmup] enter_warmup cur={cur_dt} start={user_start}"
								)
							except Exception:
								pass
						if (not jq_state_local["in_warmup"]) and in_warmup_before:
							try:
								jq_state_local["log"].append(
									f"[warmup] leave_warmup cur={cur_dt} start={user_start}"
								)
							except Exception:
								pass
						if jq_state_local["in_warmup"]:
							return
				except Exception:
					pass
				try:
					try:
						from backend.modules.s_3_backtest_engine.scheduler.lifecycle import trigger_lifecycle_tasks

						jq_state_local = self._exec_env.get("jq_state") if hasattr(self, "_exec_env") else None
						if jq_state_local:
							trigger_lifecycle_tasks(jq_state_local, "after_trading_end", self._jq_context)
					except Exception:
						pass
					try:
						from backend.modules.s_3_backtest_engine.scheduler.executor import execute_pending_tasks

						jq_state_local = self._exec_env.get("jq_state") if hasattr(self, "_exec_env") else None
						if jq_state_local:
							execute_pending_tasks(jq_state_local, self._jq_context, self.data)
					except Exception:
						pass
					self._run_handle()
				except Exception:
					pass

		return UserStrategy, jq_state

	return None, jq_state
