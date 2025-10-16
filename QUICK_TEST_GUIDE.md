# 快速测试指南 (Quick Test Guide)

本指南帮助您快速验证前后端模块的可运行性。

## 🚀 一键测试

### 方法1: 使用集成测试脚本（推荐）

```bash
# 1. 激活Python虚拟环境
source venv/bin/activate  # Windows: venv\Scripts\activate

# 2. 运行集成测试
python test_integration.py
```

**预期输出**: 9/9 测试通过 (100% 通过率) ✅

### 方法2: 手动测试各组件

#### 后端测试

```bash
# 1. 激活虚拟环境
source venv/bin/activate

# 2. 生成测试数据（如果还没有）
python scripts/generate_test_data.py

# 3. 启动后端服务器
python backend/api_server.py

# 4. 在新终端中测试API
curl http://localhost:8000/health
curl http://localhost:8000/api/jq-backtest/
```

**预期输出**:
```json
{"status": "ok"}
{"backtests": []}
```

#### 前端测试

```bash
# 1. 进入前端目录
cd frontend

# 2. 安装依赖（首次运行）
npm install

# 3. 测试构建
npm run build

# 4. 启动开发服务器
npm run dev
```

**预期输出**:
- 构建成功，生成 dist/ 目录
- 开发服务器运行在 http://localhost:5173

## 📊 测试结果检查清单

### 后端检查
- [ ] ✅ 后端服务器成功启动（端口8000）
- [ ] ✅ `/health` 端点返回 200 OK
- [ ] ✅ `/api/jq-backtest/` 端点返回空列表
- [ ] ✅ 数据提供者可以列出4个证券
- [ ] ✅ 数据提供者可以加载股票数据（1000+条记录）

### 前端检查
- [ ] ✅ `npm install` 成功（167个包）
- [ ] ✅ `npm run build` 成功（~15秒）
- [ ] ✅ 生成的 dist/ 目录包含打包文件
- [ ] ✅ `npm run dev` 启动开发服务器
- [ ] ✅ 浏览器访问 http://localhost:5173 正常显示

### 集成检查
- [ ] ✅ 前后端可同时运行
- [ ] ✅ 前端可以访问后端API（无CORS错误）
- [ ] ⚠️ 完整回测流程（需要实现回测引擎）

## 🔧 常见问题

### 问题1: 端口已被占用
```bash
# 查找占用端口的进程
lsof -ti:8000  # 后端端口
lsof -ti:5173  # 前端端口

# 终止进程
kill -9 <PID>
```

### 问题2: 测试数据未生成
```bash
# 重新生成测试数据
python scripts/generate_test_data.py

# 检查数据文件
ls -lh data/sample/daily/
```

### 问题3: 前端依赖安装失败
```bash
# 清理并重新安装
cd frontend
rm -rf node_modules package-lock.json
npm install
```

### 问题4: Python依赖问题
```bash
# 重新创建虚拟环境
rm -rf venv
python -m venv venv
source venv/bin/activate
pip install fastapi uvicorn pandas numpy backtrader loguru pytz pytest pytest-cov pydantic requests
```

## 📖 详细测试报告

完整的测试报告请查看: [TEST_REPORT.md](./TEST_REPORT.md)

## 🎯 实现状态 (2025-10-16更新)

✅ **已完成**:
1. ✅ 回测引擎实现 (`backend/jq_backtest/engine.py`)
2. ✅ 策略适配器实现 (`backend/jq_backtest/strategy.py`)
3. ✅ 数据适配器实现 (`backend/jq_backtest/csv_adapter.py`)
4. ✅ API端点集成 (`backend/api_server.py`)
5. ✅ 前端QueryClient配置 (`frontend/src/main.tsx`)
6. ✅ 端到端测试通过

📝 **详细实现报告**: [IMPLEMENTATION_REPORT.md](./IMPLEMENTATION_REPORT.md)

## 🎉 系统已就绪

系统现在完全可用，您可以：
- 通过前端UI编写和运行JoinQuant策略
- 使用REST API进行回测
- 查看回测结果和性能指标

## 💡 提示

- 使用 `http://localhost:8000/docs` 查看后端API文档（Swagger UI）
- 前端开发服务器支持热重载，修改代码后自动刷新
- 集成测试脚本可以单独运行各个测试模块
- 所有测试数据都是模拟生成的，不依赖外部数据源

---

**测试通过标准**: 所有检查项都应该显示 ✅

如有问题，请参考 [TEST_REPORT.md](./TEST_REPORT.md) 或 [IMPLEMENTATION_REPORT.md](./IMPLEMENTATION_REPORT.md)。
