/**
 * JoinQuant-Compatible Backtest Workbench
 * 
 * Provides a user interface for creating and running JoinQuant-style strategies
 * with Monaco editor for code editing and real-time results visualization.
 */
import React, { useState, useEffect } from 'react';
import {
  Card,
  Button,
  Form,
  DatePicker,
  InputNumber,
  Select,
  Space,
  message,
  Row,
  Col,
  Spin,
  Typography,
  Table,
  Tabs,
  Tag,
  Statistic,
  Alert,
  Modal,
  Input,
  List,
  Popconfirm,
  Collapse,
} from 'antd';
import {
  PlayCircleOutlined,
  CodeOutlined,
  HistoryOutlined,
  LineChartOutlined,
  SaveOutlined,
  DownloadOutlined,
  FolderOutlined,
  DeleteOutlined,
  FileTextOutlined,
  CheckCircleOutlined,
  SyncOutlined,
} from '@ant-design/icons';
import Editor from '@monaco-editor/react';
import dayjs, { Dayjs } from 'dayjs';
import * as echarts from 'echarts';
import type { EChartsOption } from 'echarts';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  api,
  validateBacktestOnJoinQuant,
  fetchJQStrategies,
  createJQStrategy,
  getJQStrategy,
  deleteJQStrategy,
  JQStrategySummary,
} from '../lib/api';
import { useDatasource } from '../contexts/DatasourceContext';

const { Title, Text, Paragraph } = Typography;
const { RangePicker } = DatePicker;
const { Option } = Select;
const { TabPane } = Tabs;

// Equity Curve Chart Component
const EquityCurveChart: React.FC<{
  equity: Array<{datetime: string; value: number}>;
  benchmark?: Array<{datetime: string; value: number}>;
}> = ({ equity, benchmark }) => {
  const chartRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    if (!chartRef.current || !equity || equity.length === 0) return;

    const chart = echarts.init(chartRef.current);

    // Normalize both series to start at initial_cash
    const equityData = equity.map(p => [p.datetime, p.value]);
    const benchmarkData = benchmark ? benchmark.map(p => [p.datetime, p.value * equity[0].value]) : [];

    const series: any[] = [
      {
        name: '策略净值',
        type: 'line',
        data: equityData,
        smooth: true,
        lineStyle: { width: 2 },
        itemStyle: { color: '#1890ff' },
      }
    ];

    if (benchmarkData.length > 0) {
      series.push({
        name: '基准净值',
        type: 'line',
        data: benchmarkData,
        smooth: true,
        lineStyle: { width: 2, type: 'dashed' },
        itemStyle: { color: '#faad14' },
      });
    }

    const option: EChartsOption = {
      title: { text: '净值曲线', left: 'center' },
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'cross' }
      },
      legend: {
        data: benchmarkData.length > 0 ? ['策略净值', '基准净值'] : ['策略净值'],
        top: 30
      },
      grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
      xAxis: {
        type: 'time' as const,
        boundaryGap: false
      } as any,
      yAxis: {
        type: 'value',
        axisLabel: {
          formatter: (value: number) => {
            if (value >= 1000000) {
              return (value / 1000000).toFixed(1) + 'M';
            } else if (value >= 1000) {
              return (value / 1000).toFixed(1) + 'K';
            }
            return value.toFixed(0);
          }
        }
      },
      series: series
    };

    chart.setOption(option);

    const handleResize = () => chart.resize();
    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      chart.dispose();
    };
  }, [equity, benchmark]);

  return <div ref={chartRef} style={{ width: '100%', height: 400 }} />;
};

// Daily Returns Chart Component
const DailyReturnsChart: React.FC<{
  returns: Array<{datetime: string; value: number}>;
  benchmarkReturns?: Array<{datetime: string; value: number}>;
}> = ({ returns, benchmarkReturns }) => {
  const chartRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    if (!chartRef.current || !returns || returns.length === 0) return;

    const chart = echarts.init(chartRef.current);

    const returnsData = returns.map(p => [p.datetime, p.value * 100]); // Convert to percentage
    const benchmarkData = benchmarkReturns ? benchmarkReturns.map(p => [p.datetime, p.value * 100]) : [];

    const series: any[] = [
      {
        name: '策略日收益',
        type: 'bar',
        data: returnsData,
        itemStyle: {
          color: (params: any) => params.value[1] >= 0 ? '#f04864' : '#2fc25b'
        }
      }
    ];

    if (benchmarkData.length > 0) {
      series.push({
        name: '基准日收益',
        type: 'line',
        data: benchmarkData,
        smooth: true,
        lineStyle: { width: 1, type: 'dashed' },
        itemStyle: { color: '#faad14' },
        symbol: 'none'
      });
    }

    const option: EChartsOption = {
      title: { text: '日收益率', left: 'center' },
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'cross' },
        formatter: (params: any) => {
          let result = params[0].axisValueLabel + '<br/>';
          params.forEach((item: any) => {
            result += `${item.marker} ${item.seriesName}: ${item.value[1].toFixed(2)}%<br/>`;
          });
          return result;
        }
      },
      legend: {
        data: benchmarkData.length > 0 ? ['策略日收益', '基准日收益'] : ['策略日收益'],
        top: 30
      },
      grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
      xAxis: {
        type: 'time' as const,
        boundaryGap: false
      } as any,
      yAxis: {
        type: 'value',
        axisLabel: {
          formatter: '{value}%'
        }
      },
      series: series
    };

    chart.setOption(option);

    const handleResize = () => chart.resize();
    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      chart.dispose();
    };
  }, [returns, benchmarkReturns]);

  return <div ref={chartRef} style={{ width: '100%', height: 300 }} />;
};

// Drawdown Curve Chart Component
const DrawdownCurveChart: React.FC<{
  drawdown: Array<{datetime: string; value: number}>;
}> = ({ drawdown }) => {
  const chartRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    if (!chartRef.current || !drawdown || drawdown.length === 0) return;

    const chart = echarts.init(chartRef.current);

    const drawdownData = drawdown.map(p => [p.datetime, p.value * 100]); // Convert to percentage

    const option: EChartsOption = {
      title: { text: '回撤曲线', left: 'center' },
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'cross' },
        formatter: (params: any) => {
          const value = params[0].value[1];
          return `${params[0].axisValueLabel}<br/>${params[0].marker} 回撤: ${value.toFixed(2)}%`;
        }
      },
      grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
      xAxis: {
        type: 'time' as const,
        boundaryGap: false
      } as any,
      yAxis: {
        type: 'value',
        inverse: true,
        axisLabel: {
          formatter: '{value}%'
        }
      },
      series: [{
        name: '回撤',
        type: 'line',
        data: drawdownData,
        smooth: true,
        lineStyle: { width: 2, color: '#cf1322' },
        areaStyle: { 
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(207, 19, 34, 0.3)' },
            { offset: 1, color: 'rgba(207, 19, 34, 0.1)' }
          ])
        },
        itemStyle: { color: '#cf1322' }
      }]
    };

    chart.setOption(option);

    const handleResize = () => chart.resize();
    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      chart.dispose();
    };
  }, [drawdown]);

  return <div ref={chartRef} style={{ width: '100%', height: 300 }} />;
};

// Rolling Sharpe Ratio Chart Component
const RollingSharpeChart: React.FC<{
  rollingSharpe: Array<{datetime: string; value: number}>;
}> = ({ rollingSharpe }) => {
  const chartRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    if (!chartRef.current || !rollingSharpe || rollingSharpe.length === 0) return;

    const chart = echarts.init(chartRef.current);

    const sharpeData = rollingSharpe.map(p => [p.datetime, p.value]);

    const option: EChartsOption = {
      title: { text: '滚动夏普比率（30日）', left: 'center' },
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'cross' },
        formatter: (params: any) => {
          const value = params[0].value[1];
          return `${params[0].axisValueLabel}<br/>${params[0].marker} 夏普比率: ${value.toFixed(2)}`;
        }
      },
      grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
      xAxis: {
        type: 'time' as const,
        boundaryGap: false
      } as any,
      yAxis: {
        type: 'value',
        splitLine: {
          lineStyle: {
            type: 'dashed'
          }
        }
      },
      series: [{
        name: '滚动夏普',
        type: 'line',
        data: sharpeData,
        smooth: true,
        lineStyle: { width: 2, color: '#1890ff' },
        itemStyle: { color: '#1890ff' },
        markLine: {
          data: [
            { yAxis: 1, lineStyle: { color: '#52c41a', type: 'dashed' }, label: { formatter: '优秀线 (1.0)' } },
            { yAxis: 0, lineStyle: { color: '#faad14', type: 'dashed' }, label: { formatter: '基准线 (0.0)' } }
          ]
        }
      }]
    };

    chart.setOption(option);

    const handleResize = () => chart.resize();
    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      chart.dispose();
    };
  }, [rollingSharpe]);

  return <div ref={chartRef} style={{ width: '100%', height: 300 }} />;
};

interface BacktestResult {
  backtest_id: string;
  status: string;
  initial_cash: number;
  final_value?: number;
  total_return?: number;
  annualized_return?: number;
  annualized_volatility?: number;
  sharpe_ratio?: number;
  max_drawdown?: number;
  sortino_ratio?: number;
  calmar_ratio?: number;
  win_rate?: number;
  profit_factor?: number;
  total_trades?: number;
  winning_trades?: number;
  losing_trades?: number;
  start_date: string;
  end_date: string;
  created_at: string;
  benchmark?: string;
  equity_curve?: Array<{datetime: string; value: number}>;
  daily_returns?: Array<{datetime: string; value: number}>;
  drawdown_curve?: Array<{datetime: string; value: number}>;
  rolling_sharpe?: Array<{datetime: string; value: number}>;
  positions?: Array<{datetime: string; instrument: string; amount: number; price: number; value: number; weight: number}>;
  trades?: Array<{datetime: string; instrument: string; side: string; amount: number; price: number; commission: number; value: number}>;
  benchmark_curve?: Array<{datetime: string; value: number}>;
  benchmark_returns?: Array<{datetime: string; value: number}>;
  benchmark_total_return?: number;
  benchmark_annualized_return?: number;
  benchmark_sharpe?: number;
  benchmark_max_drawdown?: number;
  actual_start_date?: string;
  actual_end_date?: string;
  data_coverage?: Array<{
    instrument?: string;
    requested_start?: string;
    requested_end?: string;
    actual_start?: string | null;
    actual_end?: string | null;
    bars?: number | null;
  }>;
  bars_loaded?: number;
  error?: string;
  // JoinQuant validation fields
  joinquant_validation_status?: string;
  joinquant_backtest_id?: string;
  joinquant_backtest_url?: string;
  joinquant_results?: any;
  joinquant_error?: string;
}

interface BacktestSummary {
  backtest_id: string;
  status: string;
  start_date?: string;
  end_date?: string;
  total_return?: number;
  sharpe_ratio?: number;
  created_at?: string;
  joinquant_validation_status?: string;
}

const DEFAULT_STRATEGY_CODE = `# JoinQuant兼容策略示例
def initialize(context):
    """初始化函数，回测开始时执行一次"""
    # 设置基准
    set_benchmark('000300.XSHG')
    
    # 启用真实价格模式
    set_option('use_real_price', True)
    
    # 设置交易费用：佣金万分之三，印花税千分之一
    set_order_cost(OrderCost(
        open_commission=0.0003,  # 买入佣金
        close_commission=0.0003,  # 卖出佣金
        close_tax=0.001,          # 卖出印花税
        min_commission=5          # 最低佣金5元
    ))
    
    # 定义股票池（在策略中配置）
    g.security = '000001.XSHE'  # 平安银行
    context.universe = [g.security]
    
    print("策略初始化完成")

def handle_data(context, data):
    """主策略函数，每个交易日调用一次"""
    security = g.security
    
    # 获取当前价格
    current_price = data[security].close
    
    # 获取当前持仓
    position = context.portfolio.positions.get(security)
    current_amount = position.total_amount if position else 0
    
    # 简单策略：价格>10买入，<10卖出
    if current_price > 10 and current_amount == 0:
        # 买入
        cash = context.portfolio.available_cash
        if cash > 10000:
            order_value(security, cash * 0.8)
            print(f"{context.current_dt.date()}: 买入 {security}")
    
    elif current_price < 10 and current_amount > 0:
        # 卖出
        order_target(security, 0)
        print(f"{context.current_dt.date()}: 卖出 {security}")
`;

const formatPercent = (value: number | null | undefined, digits = 2): string => {
  if (value === null || value === undefined) {
    return '-';
  }
  const numeric = Number(value);
  if (Number.isNaN(numeric)) {
    return '-';
  }
  return `${(numeric * 100).toFixed(digits)}%`;
};

const formatDecimal = (value: number | null | undefined, digits = 4): string => {
  if (value === null || value === undefined) {
    return '-';
  }
  const numeric = Number(value);
  if (Number.isNaN(numeric)) {
    return '-';
  }
  return numeric.toFixed(digits);
};

const formatDateLabel = (value?: string | null): string => {
  if (!value) return '-';
  const parsed = dayjs(value);
  if (!parsed.isValid()) {
    return value;
  }
  return parsed.format('YYYY-MM-DD');
};

const JQBacktestWorkbench: React.FC = () => {
  const [form] = Form.useForm();
  const [strategyCode, setStrategyCode] = useState(DEFAULT_STRATEGY_CODE);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [history, setHistory] = useState<BacktestSummary[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [activeTab, setActiveTab] = useState('editor');
  
  // Strategy management state
  const queryClient = useQueryClient();
  const { activeProfileId } = useDatasource();
  const [activeStrategyId, setActiveStrategyId] = useState<string | null>(null);
  const [loadingStrategyId, setLoadingStrategyId] = useState<string | null>(null);
  const [deletingStrategyId, setDeletingStrategyId] = useState<string | null>(null);
  const [saveModalVisible, setSaveModalVisible] = useState(false);
  const [strategyName, setStrategyName] = useState('');
  const [strategyDescription, setStrategyDescription] = useState('');

  const strategiesQuery = useQuery({
    queryKey: ['jq-strategies', activeProfileId],
    queryFn: fetchJQStrategies,
    enabled: Boolean(activeProfileId),
  });

  const strategies = strategiesQuery.data ?? [];
  const strategiesLoading = strategiesQuery.isLoading;
  const strategiesError = strategiesQuery.error as Error | null;

  useEffect(() => {
    setActiveStrategyId(null);
  }, [activeProfileId]);

  const createStrategyMutation = useMutation({
    mutationFn: createJQStrategy,
    onSuccess: (strategy) => {
      message.success('策略已保存');
      setStrategyCode(strategy.code);
      setActiveStrategyId(strategy.strategy_id);
      setActiveTab('editor');
      setSaveModalVisible(false);
      setStrategyName('');
      setStrategyDescription('');
      queryClient.invalidateQueries({ queryKey: ['jq-strategies'] });
    },
    onError: (error: any) => {
      message.error(error?.response?.data?.detail || '保存策略失败');
    }
  });

  const loadStrategyMutation = useMutation({
    mutationFn: getJQStrategy,
    onSuccess: (strategy) => {
      setStrategyCode(strategy.code);
      setActiveStrategyId(strategy.strategy_id);
      message.success(`已加载策略: ${strategy.name}`);
      setActiveTab('editor');
    },
    onError: (error: any) => {
      message.error(error?.response?.data?.detail || '加载策略失败');
    }
  });

  const deleteStrategyMutation = useMutation({
    mutationFn: deleteJQStrategy,
    onSuccess: (_, strategyId) => {
      message.success('策略已删除');
      if (activeStrategyId === strategyId) {
        setActiveStrategyId(null);
      }
      queryClient.invalidateQueries({ queryKey: ['jq-strategies'] });
    },
    onError: (error: any) => {
      message.error(error?.response?.data?.detail || '删除策略失败');
    }
  });
  
  // JoinQuant validation state
  const [validating, setValidating] = useState(false);
  const [validationPolling, setValidationPolling] = useState<NodeJS.Timeout | null>(null);

  // Export functions
  const exportToCSV = () => {
    if (!result) return;
    
    const csv: string[] = [];
    
    // Header
    csv.push('JoinQuant回测结果导出');
    csv.push('');
    
    // Basic info
    csv.push('基本信息');
    csv.push(`回测ID,${result.backtest_id}`);
    csv.push(`状态,${result.status}`);
    csv.push(`创建时间,${result.created_at}`);
    csv.push(`开始日期,${result.start_date}`);
    csv.push(`结束日期,${result.end_date}`);
    if (result.benchmark) csv.push(`基准,${result.benchmark}`);
    csv.push('');
    
    // Performance metrics
    csv.push('收益指标');
    csv.push(`初始资金,${result.initial_cash}`);
    csv.push(`最终价值,${result.final_value}`);
    csv.push(`总收益率,${(result.total_return || 0) * 100}%`);
    csv.push(`年化收益,${(result.annualized_return || 0) * 100}%`);
    csv.push(`年化波动,${(result.annualized_volatility || 0) * 100}%`);
    csv.push('');
    
    // Risk metrics
    csv.push('风险指标');
    csv.push(`夏普比率,${result.sharpe_ratio}`);
    csv.push(`最大回撤,${(result.max_drawdown || 0) * 100}%`);
    csv.push(`索提诺比率,${result.sortino_ratio}`);
    csv.push(`卡玛比率,${result.calmar_ratio}`);
    csv.push('');
    
    // Trade analytics
    if (result.total_trades) {
      csv.push('交易分析');
      csv.push(`总交易次数,${result.total_trades}`);
      csv.push(`胜率,${(result.win_rate || 0) * 100}%`);
      csv.push(`盈利因子,${result.profit_factor}`);
      csv.push(`盈亏比,${result.winning_trades}/${result.losing_trades}`);
      csv.push('');
    }
    
    // Trades table
    if (result.trades && result.trades.length > 0) {
      csv.push('交易记录');
      csv.push('时间,标的,方向,数量,价格,金额,手续费');
      result.trades.forEach(trade => {
        csv.push(`${trade.datetime},${trade.instrument},${trade.side},${trade.amount},${trade.price},${trade.value},${trade.commission}`);
      });
    }
    
    const blob = new Blob([csv.join('\n')], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = `backtest_${result.backtest_id}_${dayjs().format('YYYYMMDD_HHmmss')}.csv`;
    link.click();
    message.success('CSV导出成功');
  };

  const exportToJSON = () => {
    if (!result) return;
    
    const json = JSON.stringify(result, null, 2);
    const blob = new Blob([json], { type: 'application/json' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = `backtest_${result.backtest_id}_${dayjs().format('YYYYMMDD_HHmmss')}.json`;
    link.click();
    message.success('JSON导出成功');
  };

  const handleSaveStrategy = () => {
    if (!activeProfileId) {
      message.warning('请选择数据源后再保存策略');
      return;
    }
    if (!strategyName.trim()) {
      message.error('请输入策略名称');
      return;
    }

    createStrategyMutation.mutate({
      name: strategyName.trim(),
      description: strategyDescription.trim() || undefined,
      code: strategyCode,
      tags: [],
    });
  };

  const handleLoadStrategy = (strategyId: string) => {
    setLoadingStrategyId(strategyId);
    loadStrategyMutation.mutate(strategyId, {
      onSettled: () => setLoadingStrategyId(null),
    });
  };

  const handleDeleteStrategy = (strategyId: string) => {
    setDeletingStrategyId(strategyId);
    deleteStrategyMutation.mutate(strategyId, {
      onSettled: () => setDeletingStrategyId(null),
    });
  };

  const loadHistory = async () => {
    setLoadingHistory(true);
    try {
      const response = await api.get('/jq-backtest/', {
        params: { limit: 20 },
      });
      setHistory(response.data);
    } catch (error: any) {
      console.error('加载历史失败:', error);
      message.error(error.response?.data?.detail || '加载回测历史失败');
    } finally {
      setLoadingHistory(false);
    }
  };

  useEffect(() => {
    loadHistory();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const runBacktest = async (values: any) => {
    setRunning(true);
    setResult(null);

    try {
      const payload: Record<string, any> = {
        strategy_code: strategyCode,
        start_date: values.dateRange[0].format('YYYY-MM-DD'),
        end_date: values.dateRange[1].format('YYYY-MM-DD'),
        initial_cash: values.initialCash,
        freq: values.freq || 'daily',
        fq: values.fq || 'pre',
      };

      const selectedSecurities = Array.isArray(values.securities)
        ? values.securities
            .map((code: string) => (typeof code === 'string' ? code.trim() : ''))
            .filter((code: string) => code.length > 0)
        : [];
      if (selectedSecurities.length > 0) {
        payload.securities = selectedSecurities;
      }

      const commissionValue = values.commission;
      if (commissionValue !== undefined && commissionValue !== null && commissionValue !== '') {
        const numericCommission = Number(commissionValue);
        if (!Number.isNaN(numericCommission)) {
          payload.commission = numericCommission;
        }
      }

      const stampDutyValue = values.stamp_duty;
      if (stampDutyValue !== undefined && stampDutyValue !== null && stampDutyValue !== '') {
        const numericStampDuty = Number(stampDutyValue);
        if (!Number.isNaN(numericStampDuty)) {
          payload.stamp_duty = numericStampDuty;
        }
      }

      const response = await api.post('/jq-backtest/run', payload);
      const resultData: BacktestResult = response.data;
      
      setResult(resultData);
      message.success('回测完成！');
      setActiveTab('results');
      
      // Reload history
      loadHistory();
    } catch (error: any) {
      console.error('回测失败:', error);
      message.error(error.response?.data?.detail || '回测执行失败');
    } finally {
      setRunning(false);
    }
  };

  const loadBacktest = async (backtestId: string) => {
    try {
      const response = await api.get(`/jq-backtest/${backtestId}`);
      setResult(response.data);
      setActiveTab('results');
      message.success('加载回测结果成功');
    } catch (error: any) {
      message.error(error.response?.data?.detail || '加载回测失败');
    }
  };

  // JoinQuant validation function
  const handleJoinQuantValidation = async () => {
    if (!result) return;
    
    try {
      setValidating(true);
      message.info('正在启动聚宽验证...');
      
      const response = await validateBacktestOnJoinQuant(result.backtest_id, {
        benchmark: result.benchmark || '000300.XSHG'
      });
      
      message.success(response.message);
      
      // Start polling for validation status
      startValidationPolling(result.backtest_id);
      
    } catch (error: any) {
      console.error('聚宽验证失败:', error);
      message.error(error.response?.data?.detail || '启动聚宽验证失败');
      setValidating(false);
    }
  };

  // Poll for validation status
  const startValidationPolling = (backtestId: string) => {
    // Clear existing polling
    if (validationPolling) {
      clearInterval(validationPolling);
    }
    
    const pollInterval = setInterval(async () => {
      try {
        const response = await api.get(`/jq-backtest/${backtestId}`);
        const updatedResult = response.data;
        
        setResult(updatedResult);
        
        const status = updatedResult.joinquant_validation_status;
        if (status === 'completed') {
          message.success('聚宽验证完成！');
          setValidating(false);
          clearInterval(pollInterval);
          setValidationPolling(null);
        } else if (status === 'failed') {
          message.error('聚宽验证失败: ' + (updatedResult.joinquant_error || '未知错误'));
          setValidating(false);
          clearInterval(pollInterval);
          setValidationPolling(null);
        }
        // Continue polling if status is 'pending' or 'running'
        
      } catch (error: any) {
        console.error('轮询验证状态失败:', error);
        clearInterval(pollInterval);
        setValidationPolling(null);
        setValidating(false);
      }
    }, 5000); // Poll every 5 seconds
    
    setValidationPolling(pollInterval);
  };

  // Cleanup polling on unmount
  useEffect(() => {
    return () => {
      if (validationPolling) {
        clearInterval(validationPolling);
      }
    };
  }, [validationPolling]);

  const historyColumns = [
    {
      title: 'ID',
      dataIndex: 'backtest_id',
      key: 'backtest_id',
      width: 100,
      render: (id: string) => (
        <Button type="link" size="small" onClick={() => loadBacktest(id)}>
          {id.slice(0, 8)}...
        </Button>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 80,
      render: (status: string) => {
        const color = status === 'completed' ? 'success' : status === 'failed' ? 'error' : 'processing';
        return <Tag color={color}>{status}</Tag>;
      },
    },
    {
      title: '日期范围',
      key: 'date_range',
      width: 200,
      render: (record: BacktestSummary) =>
        record.start_date && record.end_date
          ? `${record.start_date} ~ ${record.end_date}`
          : '-',
    },
    {
      title: '总收益',
      dataIndex: 'total_return',
      key: 'total_return',
      width: 100,
      render: (value: number | null | undefined) => formatPercent(value, 2),
    },
    {
      title: '夏普比率',
      dataIndex: 'sharpe_ratio',
      key: 'sharpe_ratio',
      width: 100,
      render: (value: number | null | undefined) => formatDecimal(value, 4),
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (value: string | undefined) =>
        value ? dayjs(value).format('YYYY-MM-DD HH:mm:ss') : '-',
    },
    {
      title: '聚宽验证',
      dataIndex: 'joinquant_validation_status',
      key: 'joinquant_validation_status',
      width: 100,
      render: (status: string | undefined) => {
        if (!status) return '-';
        const color = status === 'completed' ? 'success' : status === 'failed' ? 'error' : status === 'running' ? 'processing' : 'default';
        return <Tag color={color}>{status}</Tag>;
      },
    },
  ];

  return (
    <div style={{ padding: '24px' }}>
      <Title level={2}>
        <CodeOutlined /> JoinQuant 策略回测
      </Title>
      <Paragraph>
        使用JoinQuant兼容的API编写策略，支持完整的因子库、交易规则和数据访问功能。
      </Paragraph>

      <Tabs activeKey={activeTab} onChange={setActiveTab} size="large">
        <TabPane
          tab={
            <span>
              <CodeOutlined /> 策略编辑
            </span>
          }
          key="editor"
        >
          <Row gutter={24}>
            <Col span={16}>
              <Card title="策略代码" extra={
                <Space>
                  <Button 
                    icon={<SaveOutlined />} 
                    size="small"
                    onClick={() => setSaveModalVisible(true)}
                  >
                    保存策略
                  </Button>
                  <Button
                    icon={<DownloadOutlined />}
                    size="small"
                    onClick={() => {
                      const blob = new Blob([strategyCode], { type: 'text/python' });
                      const url = URL.createObjectURL(blob);
                      const a = document.createElement('a');
                      a.href = url;
                      a.download = 'strategy.py';
                      a.click();
                    }}
                  >
                    导出
                  </Button>
                </Space>
              }>
                <Editor
                  height="600px"
                  defaultLanguage="python"
                  value={strategyCode}
                  onChange={(value) => setStrategyCode(value || '')}
                  theme="vs-dark"
                  options={{
                    minimap: { enabled: false },
                    fontSize: 14,
                    lineNumbers: 'on',
                    scrollBeyondLastLine: false,
                    automaticLayout: true,
                  }}
                />
              </Card>
            </Col>

            <Col span={8}>
              <Card title="回测参数">
                <Alert
                  type="info"
                  showIcon
                  message="策略配置说明"
                  description={
                    <div>
                      <div style={{ marginBottom: 8 }}>
                        • <strong>股票池</strong>：在 initialize 中设置 context.universe 或 g.security
                      </div>
                      <div style={{ marginBottom: 8 }}>
                        • <strong>基准</strong>：使用 set_benchmark('000300.XSHG')
                      </div>
                      <div>
                        • <strong>交易费用</strong>：使用 set_order_cost(OrderCost(...))
                      </div>
                    </div>
                  }
                  style={{ marginBottom: 16 }}
                />
                <Form
                  form={form}
                  layout="vertical"
                  onFinish={runBacktest}
                  initialValues={{
                    dateRange: [dayjs('2023-01-01'), dayjs('2023-12-31')],
                    initialCash: 1000000,
                    freq: 'daily',
                    fq: 'pre',
                    securities: [],
                  }}
                >
                  <Form.Item
                    label="回测日期"
                    name="dateRange"
                    rules={[{ required: true, message: '请选择日期范围' }]}
                  >
                    <RangePicker style={{ width: '100%' }} />
                  </Form.Item>

                  <Form.Item 
                    label="初始资金" 
                    name="initialCash"
                    tooltip="策略开始时的初始资金"
                  >
                    <InputNumber
                      min={10000}
                      max={100000000}
                      step={100000}
                      style={{ width: '100%' }}
                      formatter={(value) => `¥ ${value}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}
                    />
                  </Form.Item>

                  <Form.Item 
                    label="数据频率" 
                    name="freq"
                    tooltip="回测使用的数据频率"
                  >
                    <Select>
                      <Option value="daily">日线</Option>
                      <Option value="minute">分钟线</Option>
                    </Select>
                  </Form.Item>

                  <Form.Item 
                    label="复权方式" 
                    name="fq"
                    tooltip="价格复权方式，前复权推荐用于回测"
                  >
                    <Select>
                      <Option value="pre">前复权</Option>
                      <Option value="post">后复权</Option>
                      <Option value="none">不复权</Option>
                    </Select>
                  </Form.Item>

                  <Collapse
                    bordered={false}
                    style={{ background: 'transparent', marginBottom: 16 }}
                    items={[
                      {
                        key: 'advanced',
                        label: '高级参数',
                        children: (
                          <Space
                            direction="vertical"
                            style={{ width: '100%' }}
                            size="middle"
                          >
                            <Form.Item
                              label="股票池 (可选)"
                              name="securities"
                              tooltip="无需在代码中重复设置，可在此输入股票代码列表，例如 000001.XSHE。"
                            >
                              <Select
                                mode="tags"
                                tokenSeparators={[',', ' ', ';']}
                                placeholder="输入股票代码并按回车确认，可留空让系统从策略推断"
                                allowClear
                              />
                            </Form.Item>

                            <Form.Item
                              label="买卖佣金率 (可选)"
                              name="commission"
                              tooltip="按成交金额的比例输入，例如 0.0003 代表万分之三。不填则使用策略代码或默认值。"
                            >
                              <InputNumber
                                min={0}
                                max={0.05}
                                step={0.0001}
                                style={{ width: '100%' }}
                                precision={6}
                                placeholder="例如 0.0003"
                              />
                            </Form.Item>

                            <Form.Item
                              label="印花税率 (可选)"
                              name="stamp_duty"
                              tooltip="卖出时适用的印花税，例如 0.001 表示千分之一。"
                            >
                              <InputNumber
                                min={0}
                                max={0.05}
                                step={0.0001}
                                style={{ width: '100%' }}
                                precision={6}
                                placeholder="例如 0.001"
                              />
                            </Form.Item>
                          </Space>
                        ),
                      },
                    ]}
                  />

                  <Form.Item>
                    <Button
                      type="primary"
                      htmlType="submit"
                      icon={<PlayCircleOutlined />}
                      loading={running}
                      block
                      size="large"
                    >
                      {running ? '回测运行中...' : '开始回测'}
                    </Button>
                  </Form.Item>
                </Form>
              </Card>

              <Card title="API 参考" style={{ marginTop: 16 }} size="small">
                <Paragraph style={{ fontSize: 12 }}>
                  <Text strong>策略函数：</Text>
                  <ul style={{ marginLeft: 0, paddingLeft: 20 }}>
                    <li><code>initialize(context)</code> - 初始化</li>
                    <li><code>handle_data(context, data)</code> - 每日执行</li>
                  </ul>
                  
                  <Text strong>配置函数：</Text>
                  <ul style={{ marginLeft: 0, paddingLeft: 20 }}>
                    <li><code>set_benchmark(code)</code> - 设置基准</li>
                    <li><code>set_order_cost(OrderCost(...))</code> - 设置费用</li>
                    <li><code>set_option(key, value)</code> - 设置选项</li>
                  </ul>
                  
                  <Text strong>交易函数：</Text>
                  <ul style={{ marginLeft: 0, paddingLeft: 20 }}>
                    <li><code>order(security, amount)</code></li>
                    <li><code>order_target(security, amount)</code></li>
                    <li><code>order_value(security, value)</code></li>
                    <li><code>order_target_value(security, value)</code></li>
                  </ul>
                  
                  <Text strong>数据访问：</Text>
                  <ul style={{ marginLeft: 0, paddingLeft: 20 }}>
                    <li><code>data[security].close</code> - 收盘价</li>
                    <li><code>history(count, unit, field)</code> - 历史数据</li>
                    <li><code>attribute_history(security, count)</code></li>
                  </ul>
                </Paragraph>
              </Card>
            </Col>
          </Row>
        </TabPane>

        <TabPane
          tab={
            <span>
              <FolderOutlined /> 策略列表
            </span>
          }
          key="strategies"
        >
          {!activeProfileId ? (
            <Alert
              message="请先选择数据源"
              description="策略列表需在数据源上下文中加载，请先在顶部切换到有效的数据源。"
              type="info"
              showIcon
            />
          ) : (
            <Card 
            title={`已保存策略 (${strategies.length})`}
            extra={
              <Button 
                type="primary" 
                icon={<SaveOutlined />}
                onClick={() => setSaveModalVisible(true)}
                disabled={!activeProfileId}
              >
                保存当前策略
              </Button>
            }
          >
            {strategiesQuery.isError ? (
              <Alert
                message="加载策略失败"
                description={strategiesError?.message || '请稍后重试'}
                type="error"
                showIcon
              />
            ) : strategiesLoading ? (
              <div style={{ display: 'flex', justifyContent: 'center', padding: '24px 0' }}>
                <Spin />
              </div>
            ) : strategies.length === 0 ? (
              <Alert
                message="暂无保存的策略"
                description="点击右上角「保存当前策略」按钮可以保存您的策略代码，方便后续使用。"
                type="info"
                showIcon
              />
            ) : (
              <List
                dataSource={strategies}
                renderItem={(strategy) => (
                  <List.Item
                    actions={[
                      <Button 
                        type="link" 
                        icon={<FileTextOutlined />}
                        onClick={() => handleLoadStrategy(strategy.strategy_id)}
                        loading={loadStrategyMutation.isPending && loadingStrategyId === strategy.strategy_id}
                      >
                        加载
                      </Button>,
                      <Popconfirm
                        title="确认删除此策略？"
                        description="删除后将无法恢复"
                        onConfirm={() => handleDeleteStrategy(strategy.strategy_id)}
                        okText="确定"
                        cancelText="取消"
                      >
                        <Button
                          type="link"
                          danger
                          icon={<DeleteOutlined />}
                          loading={deleteStrategyMutation.isPending && deletingStrategyId === strategy.strategy_id}
                        >
                          删除
                        </Button>
                      </Popconfirm>
                    ]}
                  >
                    <List.Item.Meta
                      title={
                        <Space size="small">
                          <span>{strategy.name}</span>
                          {activeStrategyId === strategy.strategy_id && <Tag color="blue">当前</Tag>}
                        </Space>
                      }
                      description={
                        <div>
                          {strategy.description && (
                            <div style={{ marginBottom: 4 }}>
                              <Text type="secondary">{strategy.description}</Text>
                            </div>
                          )}
                          {strategy.tags && strategy.tags.length > 0 && (
                            <div style={{ marginBottom: 4 }}>
                              {strategy.tags.map((tag) => (
                                <Tag key={tag}>{tag}</Tag>
                              ))}
                            </div>
                          )}
                          <Text type="secondary" style={{ display: 'block', fontSize: 12 }}>
                            所有者: {strategy.owner || '未知'}
                          </Text>
                          <Text type="secondary" style={{ fontSize: 12 }}>
                            创建: {dayjs(strategy.created_at).format('YYYY-MM-DD HH:mm')} | 
                            更新: {dayjs(strategy.updated_at).format('YYYY-MM-DD HH:mm')}
                          </Text>
                        </div>
                      }
                    />
                  </List.Item>
                )}
              />
            )}
            </Card>
          )}
        </TabPane>

        <TabPane
          tab={
            <span>
              <LineChartOutlined /> 回测结果
            </span>
          }
          key="results"
        >
          {result ? (
            <div>
              <Alert
                message={`回测ID: ${result.backtest_id}`}
                description={`状态: ${result.status} | 创建时间: ${dayjs(result.created_at).format('YYYY-MM-DD HH:mm:ss')}${result.benchmark ? ' | 基准: ' + result.benchmark : ''}`}
                type={result.status === 'completed' ? 'success' : 'error'}
                showIcon
                style={{ marginBottom: 16 }}
                action={
                  result.status === 'completed' ? (
                    <Space>
                      <Button 
                        size="small" 
                        icon={validating ? <SyncOutlined spin /> : <CheckCircleOutlined />} 
                        onClick={handleJoinQuantValidation}
                        loading={validating}
                        disabled={validating || result.joinquant_validation_status === 'running' || result.joinquant_validation_status === 'pending'}
                      >
                        {result.joinquant_validation_status === 'completed' ? '重新验证' : '聚宽验证'}
                      </Button>
                      <Button size="small" icon={<DownloadOutlined />} onClick={exportToCSV}>
                        导出CSV
                      </Button>
                      <Button size="small" icon={<DownloadOutlined />} onClick={exportToJSON}>
                        导出JSON
                      </Button>
                    </Space>
                  ) : undefined
                }
              />

              {/* JoinQuant Validation Status */}
              {result.joinquant_validation_status && (
                <Alert
                  message="聚宽验证状态"
                  description={
                    <div>
                      <p>
                        <strong>状态:</strong>{' '}
                        <Tag color={
                          result.joinquant_validation_status === 'completed' ? 'success' :
                          result.joinquant_validation_status === 'failed' ? 'error' :
                          result.joinquant_validation_status === 'running' ? 'processing' : 'default'
                        }>
                          {result.joinquant_validation_status}
                        </Tag>
                      </p>
                      {result.joinquant_backtest_url && (
                        <p>
                          <strong>聚宽回测链接:</strong>{' '}
                          <a href={result.joinquant_backtest_url} target="_blank" rel="noopener noreferrer">
                            {result.joinquant_backtest_url}
                          </a>
                        </p>
                      )}
                      {result.joinquant_error && (
                        <p style={{ color: '#cf1322' }}>
                          <strong>错误:</strong> {result.joinquant_error}
                        </p>
                      )}
                    </div>
                  }
                  type={
                    result.joinquant_validation_status === 'completed' ? 'success' :
                    result.joinquant_validation_status === 'failed' ? 'error' :
                    'info'
                  }
                  showIcon
                  style={{ marginBottom: 16 }}
                />
              )}

              {/* Comparison with JoinQuant Results */}
              {result.joinquant_validation_status === 'completed' && result.joinquant_results && (
                <Card title="对比结果：本地 vs 聚宽" style={{ marginBottom: 16 }}>
                  <Table
                    size="small"
                    pagination={false}
                    dataSource={[
                      {
                        key: 'total_return',
                        metric: '总收益率',
                        local: formatPercent(result.total_return),
                        joinquant: formatPercent(result.joinquant_results.total_return),
                      },
                      {
                        key: 'annualized_return',
                        metric: '年化收益',
                        local: formatPercent(result.annualized_return),
                        joinquant: formatPercent(result.joinquant_results.annualized_return),
                      },
                      {
                        key: 'sharpe_ratio',
                        metric: '夏普比率',
                        local: formatDecimal(result.sharpe_ratio),
                        joinquant: formatDecimal(result.joinquant_results.sharpe_ratio),
                      },
                      {
                        key: 'max_drawdown',
                        metric: '最大回撤',
                        local: formatPercent(result.max_drawdown),
                        joinquant: formatPercent(result.joinquant_results.max_drawdown),
                      },
                      {
                        key: 'annualized_volatility',
                        metric: '年化波动',
                        local: formatPercent(result.annualized_volatility),
                        joinquant: formatPercent(result.joinquant_results.annualized_volatility),
                      },
                    ]}
                    columns={[
                      {
                        title: '指标',
                        dataIndex: 'metric',
                        key: 'metric',
                        width: 150,
                      },
                      {
                        title: '本地回测',
                        dataIndex: 'local',
                        key: 'local',
                        align: 'right',
                      },
                      {
                        title: '聚宽回测',
                        dataIndex: 'joinquant',
                        key: 'joinquant',
                        align: 'right',
                      },
                    ]}
                  />
                </Card>
              )}

              {result.status === 'completed' && (
                <>
                  {/* Performance Metrics */}
                  <Card title="收益指标" style={{ marginBottom: 16 }}>
                    <Row gutter={16}>
                      <Col span={4}>
                        <Statistic
                          title="初始资金"
                          value={result.initial_cash}
                          precision={2}
                          prefix="¥"
                        />
                      </Col>
                      <Col span={4}>
                        <Statistic
                          title="最终价值"
                          value={result.final_value}
                          precision={2}
                          prefix="¥"
                          valueStyle={{ color: (result.final_value || 0) >= result.initial_cash ? '#3f8600' : '#cf1322' }}
                        />
                      </Col>
                      <Col span={4}>
                        <Statistic
                          title="总收益率"
                          value={(result.total_return || 0) * 100}
                          precision={2}
                          suffix="%"
                          valueStyle={{ color: (result.total_return || 0) >= 0 ? '#3f8600' : '#cf1322' }}
                        />
                      </Col>
                      <Col span={4}>
                        <Statistic
                          title="年化收益"
                          value={(result.annualized_return || 0) * 100}
                          precision={2}
                          suffix="%"
                          valueStyle={{ color: (result.annualized_return || 0) >= 0 ? '#3f8600' : '#cf1322' }}
                        />
                      </Col>
                      <Col span={4}>
                        <Statistic
                          title="年化波动"
                          value={(result.annualized_volatility || 0) * 100}
                          precision={2}
                          suffix="%"
                        />
                      </Col>
                      <Col span={4}>
                        <Statistic
                          title="盈亏金额"
                          value={(result.final_value || 0) - result.initial_cash}
                          precision={2}
                          prefix="¥"
                          valueStyle={{ color: (result.final_value || 0) >= result.initial_cash ? '#3f8600' : '#cf1322' }}
                        />
                      </Col>
                    </Row>
                  </Card>

                  {/* Risk Metrics */}
                  <Card title="风险指标" style={{ marginBottom: 16 }}>
                    <Row gutter={16}>
                      <Col span={6}>
                        <Statistic
                          title="夏普比率"
                          value={result.sharpe_ratio}
                          precision={4}
                          valueStyle={{ color: (result.sharpe_ratio || 0) > 1 ? '#3f8600' : '#000' }}
                        />
                      </Col>
                      <Col span={6}>
                        <Statistic
                          title="最大回撤"
                          value={(result.max_drawdown || 0) * 100}
                          precision={2}
                          suffix="%"
                          valueStyle={{ color: '#cf1322' }}
                        />
                      </Col>
                      <Col span={6}>
                        <Statistic
                          title="索提诺比率"
                          value={result.sortino_ratio}
                          precision={4}
                          valueStyle={{ color: (result.sortino_ratio || 0) > 1 ? '#3f8600' : '#000' }}
                        />
                      </Col>
                      <Col span={6}>
                        <Statistic
                          title="卡玛比率"
                          value={result.calmar_ratio}
                          precision={4}
                          valueStyle={{ color: (result.calmar_ratio || 0) > 1 ? '#3f8600' : '#000' }}
                        />
                      </Col>
                    </Row>
                    {result.benchmark && result.benchmark_total_return !== undefined && (
                      <Row gutter={16} style={{ marginTop: 16 }}>
                        <Col span={12}>
                          <Statistic
                            title="基准收益"
                            value={(result.benchmark_total_return || 0) * 100}
                            precision={2}
                            suffix="%"
                            valueStyle={{ color: (result.benchmark_total_return || 0) >= 0 ? '#faad14' : '#cf1322' }}
                          />
                        </Col>
                        <Col span={12}>
                          <Statistic
                            title="超额收益"
                            value={((result.total_return || 0) - (result.benchmark_total_return || 0)) * 100}
                            precision={2}
                            suffix="%"
                            valueStyle={{ color: ((result.total_return || 0) - (result.benchmark_total_return || 0)) >= 0 ? '#3f8600' : '#cf1322' }}
                          />
                        </Col>
                      </Row>
                    )}
                  </Card>

                  {/* Trade Analytics */}
                  {result.total_trades !== undefined && result.total_trades > 0 && (
                    <Card title="交易分析" style={{ marginBottom: 16 }}>
                      <Row gutter={16}>
                        <Col span={6}>
                          <Statistic
                            title="总交易次数"
                            value={result.total_trades}
                            precision={0}
                          />
                        </Col>
                        <Col span={6}>
                          <Statistic
                            title="胜率"
                            value={(result.win_rate || 0) * 100}
                            precision={2}
                            suffix="%"
                            valueStyle={{ color: (result.win_rate || 0) >= 0.5 ? '#3f8600' : '#cf1322' }}
                          />
                        </Col>
                        <Col span={6}>
                          <Statistic
                            title="盈利因子"
                            value={result.profit_factor}
                            precision={2}
                            valueStyle={{ color: (result.profit_factor || 0) >= 1 ? '#3f8600' : '#cf1322' }}
                          />
                        </Col>
                        <Col span={6}>
                          <Statistic
                            title="盈亏比"
                            value={`${result.winning_trades || 0}/${result.losing_trades || 0}`}
                          />
                        </Col>
                      </Row>
                    </Card>
                  )}

                  {/* Equity Curve Chart */}
                  {result.equity_curve && result.equity_curve.length > 0 && (
                    <Card title="净值曲线" style={{ marginBottom: 16 }}>
                      <EquityCurveChart 
                        equity={result.equity_curve} 
                        benchmark={result.benchmark_curve}
                      />
                    </Card>
                  )}

                  {/* Daily Returns Chart */}
                  {result.daily_returns && result.daily_returns.length > 0 && (
                    <Card title="日收益率" style={{ marginBottom: 16 }}>
                      <DailyReturnsChart 
                        returns={result.daily_returns}
                        benchmarkReturns={result.benchmark_returns}
                      />
                    </Card>
                  )}

                  {/* Drawdown Curve Chart */}
                  {result.drawdown_curve && result.drawdown_curve.length > 0 && (
                    <Card title="回撤曲线" style={{ marginBottom: 16 }}>
                      <DrawdownCurveChart drawdown={result.drawdown_curve} />
                    </Card>
                  )}

                  {/* Rolling Sharpe Chart */}
                  {result.rolling_sharpe && result.rolling_sharpe.length > 0 && (
                    <Card title="滚动夏普比率" style={{ marginBottom: 16 }}>
                      <RollingSharpeChart rollingSharpe={result.rolling_sharpe} />
                    </Card>
                  )}

                  {/* Trades Table */}
                  {result.trades && result.trades.length > 0 && (
                    <Card title="交易记录" style={{ marginBottom: 16 }}>
                      <Table
                        dataSource={result.trades}
                        size="small"
                        pagination={{ pageSize: 10 }}
                        columns={[
                          {
                            title: '时间',
                            dataIndex: 'datetime',
                            key: 'datetime',
                            render: (text: string) => dayjs(text).format('YYYY-MM-DD HH:mm:ss'),
                            width: 180,
                          },
                          {
                            title: '标的',
                            dataIndex: 'instrument',
                            key: 'instrument',
                            width: 120,
                          },
                          {
                            title: '方向',
                            dataIndex: 'side',
                            key: 'side',
                            width: 80,
                            render: (text: string) => (
                              <Tag color={text === 'buy' ? 'red' : 'green'}>
                                {text === 'buy' ? '买入' : '卖出'}
                              </Tag>
                            ),
                          },
                          {
                            title: '数量',
                            dataIndex: 'amount',
                            key: 'amount',
                            width: 100,
                            render: (value: number) => value.toFixed(0),
                          },
                          {
                            title: '价格',
                            dataIndex: 'price',
                            key: 'price',
                            width: 100,
                            render: (value: number) => value.toFixed(2),
                          },
                          {
                            title: '金额',
                            dataIndex: 'value',
                            key: 'value',
                            width: 120,
                            render: (value: number) => `¥${value.toFixed(2)}`,
                          },
                          {
                            title: '手续费',
                            dataIndex: 'commission',
                            key: 'commission',
                            width: 100,
                            render: (value: number) => `¥${value.toFixed(2)}`,
                          },
                        ]}
                      />
                    </Card>
                  )}

                  {/* Positions Table */}
                  {result.positions && result.positions.length > 0 && (
                    <Card title="持仓历史" style={{ marginBottom: 16 }}>
                      <Table
                        dataSource={result.positions}
                        size="small"
                        pagination={{ pageSize: 10 }}
                        rowKey={(record) => `${record.datetime}-${record.instrument}`}
                        columns={[
                          {
                            title: '日期',
                            dataIndex: 'datetime',
                            key: 'datetime',
                            render: (text: string) => dayjs(text).format('YYYY-MM-DD'),
                            width: 120,
                          },
                          {
                            title: '标的',
                            dataIndex: 'instrument',
                            key: 'instrument',
                            width: 120,
                          },
                          {
                            title: '数量',
                            dataIndex: 'amount',
                            key: 'amount',
                            width: 100,
                            render: (value: number) => value != null ? value.toFixed(0) : '-',
                          },
                          {
                            title: '价格',
                            dataIndex: 'price',
                            key: 'price',
                            width: 100,
                            render: (value: number) => value != null ? value.toFixed(2) : '-',
                          },
                          {
                            title: '市值',
                            dataIndex: 'value',
                            key: 'value',
                            width: 120,
                            render: (value: number) => value != null ? `¥${value.toFixed(2)}` : '-',
                          },
                          {
                            title: '权重',
                            dataIndex: 'weight',
                            key: 'weight',
                            width: 100,
                            render: (value: number) => value != null ? `${(value * 100).toFixed(2)}%` : '-',
                          },
                        ]}
                      />
                    </Card>
                  )}

                  {/* Period Info */}
                  <Card title="回测周期">
                    <Paragraph>
                      <Text strong>请求区间：</Text> {`${formatDateLabel(result.start_date)} ~ ${formatDateLabel(result.end_date)}`}
                      <br />
                      <Text strong>实际区间：</Text>{' '}
                      {`${formatDateLabel(result.actual_start_date ?? result.start_date)} ~ ${formatDateLabel(result.actual_end_date ?? result.end_date)}`}
                      {((result.actual_start_date && result.actual_start_date !== result.start_date) ||
                        (result.actual_end_date && result.actual_end_date !== result.end_date)) && (
                        <>
                          <br />
                          <Tag color="warning">提示</Tag>
                          <Text type="secondary">
                            一部分日期超出当前数据源覆盖范围，已自动裁剪至有效区间。
                          </Text>
                        </>
                      )}
                      {typeof result.bars_loaded === 'number' && (
                        <>
                          <br />
                          <Text strong>加载K线数：</Text> {result.bars_loaded}
                        </>
                      )}
                      {result.benchmark && (
                        <>
                          <br />
                          <Text strong>基准指数：</Text> {result.benchmark}
                        </>
                      )}
                    </Paragraph>
                    {result.data_coverage && result.data_coverage.length > 0 && (
                      <Table
                        size="small"
                        dataSource={result.data_coverage.map((item, index) => ({
                          ...item,
                          key: `${item.instrument || 'sec'}-${index}`,
                        }))}
                        pagination={false}
                        columns={[
                          {
                            title: '标的',
                            dataIndex: 'instrument',
                            key: 'instrument',
                            width: 140,
                          },
                          {
                            title: '请求起始',
                            dataIndex: 'requested_start',
                            key: 'requested_start',
                            render: (value: string) => formatDateLabel(value),
                          },
                          {
                            title: '请求结束',
                            dataIndex: 'requested_end',
                            key: 'requested_end',
                            render: (value: string) => formatDateLabel(value),
                          },
                          {
                            title: '实际起始',
                            dataIndex: 'actual_start',
                            key: 'actual_start',
                            render: (value: string | null) => formatDateLabel(value),
                          },
                          {
                            title: '实际结束',
                            dataIndex: 'actual_end',
                            key: 'actual_end',
                            render: (value: string | null) => formatDateLabel(value),
                          },
                          {
                            title: 'K线数',
                            dataIndex: 'bars',
                            key: 'bars',
                            render: (value: number | null) => (value ?? '-'),
                          },
                        ]}
                        style={{ marginTop: 16 }}
                      />
                    )}
                  </Card>
                </>
              )}

              {result.error && (
                <Alert
                  message="回测失败"
                  description={result.error}
                  type="error"
                  showIcon
                  style={{ marginTop: 24 }}
                />
              )}
            </div>
          ) : (
            <Alert
              message="未找到回测结果"
              description="请先运行回测或从历史记录中选择一个回测查看结果。"
              type="info"
              showIcon
            />
          )}
        </TabPane>

        <TabPane
          tab={
            <span>
              <HistoryOutlined /> 历史记录
            </span>
          }
          key="history"
        >
          <Card
            title="回测历史"
            extra={
              <Button
                icon={<HistoryOutlined />}
                onClick={loadHistory}
                loading={loadingHistory}
              >
                刷新
              </Button>
            }
          >
            <Table
              dataSource={history}
              columns={historyColumns}
              loading={loadingHistory}
              rowKey="backtest_id"
              pagination={{
                pageSize: 10,
                showSizeChanger: false,
                showTotal: (total) => `共 ${total} 条记录`,
              }}
            />
          </Card>
        </TabPane>
      </Tabs>

      {/* Save Strategy Modal */}
      <Modal
        title="保存策略"
        open={saveModalVisible}
        onOk={handleSaveStrategy}
        onCancel={() => {
          setSaveModalVisible(false);
      setStrategyName('');
      setStrategyDescription('');
    }}
    okText="保存"
    cancelText="取消"
    confirmLoading={createStrategyMutation.isPending}
  >
        <Form layout="vertical">
          <Form.Item 
            label="策略名称" 
            required
            help="请输入便于识别的策略名称"
          >
            <Input
              placeholder="例如：均线策略v1.0"
              value={strategyName}
              onChange={(e) => setStrategyName(e.target.value)}
            />
          </Form.Item>
          <Form.Item label="策略描述">
            <Input.TextArea
              placeholder="简要描述策略逻辑和特点（可选）"
              value={strategyDescription}
              onChange={(e) => setStrategyDescription(e.target.value)}
              rows={3}
            />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default JQBacktestWorkbench;
