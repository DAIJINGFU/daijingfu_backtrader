/**
 * 简化的API客户端
 * 用于独立开发
 */
import axios from 'axios';

const api = axios.create({
  baseURL: '/api',
  timeout: 60000,
});

export { api };

// JQ回测相关API
export const runJQBacktest = (payload: any) => {
  return api.post('/jq-backtest/run', payload);
};

export const getJQBacktest = (backtestId: string) => {
  return api.get(`/jq-backtest/${backtestId}`);
};

export const listJQBacktests = () => {
  return api.get('/jq-backtest/');
};

// 策略管理相关接口类型
export interface JQStrategySummary {
  id: string;
  name: string;
  description?: string;
  created_at: string;
  updated_at: string;
}

// JoinQuant验证接口（独立开发模式下的模拟实现）
export const validateBacktestOnJoinQuant = async (strategyCode: string) => {
  // 独立开发模式下返回模拟响应
  return Promise.resolve({
    data: {
      valid: true,
      message: '独立开发模式：跳过JoinQuant验证'
    }
  });
};

// 策略管理接口（独立开发模式下的模拟实现）
export const fetchJQStrategies = async () => {
  // 独立开发模式下返回空列表
  return Promise.resolve({
    data: []
  });
};

export const createJQStrategy = async (strategy: Partial<JQStrategySummary>) => {
  // 独立开发模式下返回模拟创建的策略
  return Promise.resolve({
    data: {
      id: Date.now().toString(),
      name: strategy.name || '未命名策略',
      description: strategy.description || '',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString()
    }
  });
};

export const getJQStrategy = async (id: string) => {
  // 独立开发模式下返回模拟策略
  return Promise.resolve({
    data: {
      id,
      name: '模拟策略',
      description: '独立开发模式',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString()
    }
  });
};

export const deleteJQStrategy = async (id: string) => {
  // 独立开发模式下返回成功
  return Promise.resolve({
    data: { success: true }
  });
};
