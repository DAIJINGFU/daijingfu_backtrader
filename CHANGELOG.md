# 变更日志 (CHANGELOG)

## [2.0.0] - 2025-10-16

### ✨ 新增功能

#### 回测引擎
- ✅ 实现完整的 `JQBacktestEngine` 类
- ✅ 集成 backtrader 框架
- ✅ 支持动态策略代码执行
- ✅ 基础性能指标计算（收益率、最终资产）
- ✅ 回测结果持久化存储

#### 策略适配器
- ✅ 实现 `JQStrategy` Backtrader 适配器
- ✅ 支持 `initialize()` 函数
- ✅ 支持 `handle_data()` 函数
- ✅ Context 对象注入
- ✅ 全局变量 g 支持
- ✅ 数据代理对象构建

#### 数据适配器
- ✅ 实现 `CSVDataFeedAdapter` 类
- ✅ 集成 `SimpleCSVDataProvider`
- ✅ 参数映射（fq → adjust）
- ✅ 支持前复权、后复权、不复权

#### API 服务
- ✅ 实现 `POST /api/jq-backtest/run` 端点
- ✅ 实现 `GET /api/jq-backtest/{id}` 端点
- ✅ 实现 `GET /api/jq-backtest/` 列表端点
- ✅ 回测结果存储和查询
- ✅ 自动证券列表获取

#### 前端改进
- ✅ 配置 QueryClientProvider
- ✅ 修复 React Query 集成问题
- ✅ 支持完整的回测流程

### 🔧 修复

#### 导入路径
- 🔧 修复 `backend.services.jq_backtest` → `backend.jq_backtest`
- 🔧 更新 3 个文件的导入语句：
  - `backend/jq_backtest/context.py`
  - `backend/jq_backtest/trading_api.py`
  - `backend/jq_backtest/__init__.py`

#### 前端错误
- 🔧 修复 `No QueryClient set` 错误
- 🔧 添加 QueryClientProvider 配置

#### API 错误
- 🔧 修复 501 Not Implemented 错误
- 🔧 实现完整的回测端点逻辑

#### 参数兼容性
- 🔧 修复 `fq` 参数传递错误
- 🔧 添加 fq → adjust 参数映射

### 📚 文档更新

- 📝 更新 README.md - 项目状态和开发任务
- 📝 创建 IMPLEMENTATION_REPORT.md - 详细实现报告
- 📝 更新 QUICK_TEST_GUIDE.md - 测试指南
- 📝 创建 CHANGELOG.md - 本文件

### 🏗️ 架构改进

- 重构回测引擎为模块化设计
- 清晰的关注点分离（引擎、策略、数据）
- 标准化的错误处理
- 日志记录改进

### 🧪 测试

- ✅ 引擎初始化测试
- ✅ 数据加载测试
- ✅ API 健康检查测试
- ✅ 端到端回测测试

### 📊 性能

- 基本回测功能运行正常
- 数据加载优化
- API 响应速度良好

---

## [1.0.0] - 2025-10-13

### 初始版本

- ✅ 项目结构搭建
- ✅ 数据提供者实现 (`SimpleCSVDataProvider`)
- ✅ 前端界面实现 (`JQBacktestWorkbench`)
- ✅ 测试数据生成脚本
- ✅ API 服务器框架
- ✅ 基础文档

### 待实现功能

- ⏳ 回测引擎
- ⏳ 策略适配器
- ⏳ 数据适配器
- ⏳ API 端点实现

---

## 版本说明

### 版本号规则
- **主版本号**: 重大架构变更或不兼容更新
- **次版本号**: 新功能添加
- **修订号**: Bug修复和小改进

### 图标说明
- ✨ 新功能
- 🔧 修复
- 📚 文档
- 🏗️ 架构
- 🧪 测试
- 📊 性能
- ⏳ 待实现
- ✅ 已完成
