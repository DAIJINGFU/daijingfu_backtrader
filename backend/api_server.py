"""
简化的REST API服务器
用于独立开发环境
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime
from pathlib import Path
import uvicorn
import os
from dotenv import load_dotenv

# 加载.env文件
load_dotenv()

# 导入回测模块
from backend.jq_backtest.engine import JQBacktestEngine
from backend.data_provider import SimpleCSVDataProvider

# 初始化数据提供者
# 优先使用环境变量中的DATA_ROOT，否则使用默认测试数据
DATA_DIR = os.getenv('DATA_ROOT') or str(Path(__file__).parent.parent / "data" / "sample")
data_provider = SimpleCSVDataProvider(DATA_DIR)

# 初始化回测引擎
engine = JQBacktestEngine(csv_provider=data_provider)

# 存储回测结果
backtest_results: Dict[str, Any] = {}

app = FastAPI(title="JQ Backtest API")

# CORS配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class JQBacktestRequest(BaseModel):
    """回测请求"""
    strategy_code: str
    start_date: str
    end_date: str
    securities: Optional[List[str]] = None
    initial_cash: float = 1000000
    freq: str = 'daily'
    fq: str = 'pre'


class JQBacktestResponse(BaseModel):
    """回测响应"""
    backtest_id: str
    status: str
    total_return: Optional[float] = None
    sharpe_ratio: Optional[float] = None
    # ... 其他字段


@app.post("/api/jq-backtest/run")
async def run_backtest(request: JQBacktestRequest):
    """运行回测"""
    try:
        # 转换日期格式
        start_date = datetime.strptime(request.start_date, "%Y-%m-%d")
        end_date = datetime.strptime(request.end_date, "%Y-%m-%d")
        
        # 如果没有指定证券，使用数据目录中的所有证券
        securities = request.securities
        if not securities:
            securities = data_provider.list_securities()[:5]  # 限制数量
        
        # 运行回测
        result = engine.run_backtest(
            strategy_code=request.strategy_code,
            start_date=start_date,
            end_date=end_date,
            initial_cash=request.initial_cash,
            securities=securities,
            freq=request.freq,
            fq=request.fq
        )
        
        # 存储结果
        backtest_id = result['backtest_id']
        backtest_results[backtest_id] = result
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/jq-backtest/{backtest_id}")
async def get_backtest(backtest_id: str):
    """获取回测结果"""
    if backtest_id not in backtest_results:
        raise HTTPException(status_code=404, detail="Backtest not found")
    
    return backtest_results[backtest_id]


@app.get("/api/jq-backtest/")
async def list_backtests(limit: int = 20):
    """列出所有回测"""
    backtests = [
        {
            'backtest_id': bid,
            'status': result.get('status'),
            'start_date': result.get('start_date'),
            'end_date': result.get('end_date'),
            'total_return': result.get('total_return'),
        }
        for bid, result in list(backtest_results.items())[-limit:]
    ]
    return {"backtests": backtests}


@app.get("/health")
async def health():
    """健康检查"""
    return {"status": "ok"}


if __name__ == "__main__":
    print("🚀 启动JQ回测API服务器...")
    print("📡 API地址: http://localhost:8000")
    print("📚 文档地址: http://localhost:8000/docs")
    print(f"📁 数据目录: {DATA_DIR}")
    
    uvicorn.run(app, host="0.0.0.0", port=8000)
