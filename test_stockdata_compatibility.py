#!/usr/bin/env python3
"""
数据兼容性测试 - 验证与 /Volumes/Extreme SSD/stockdata 的兼容性

这个测试验证 SimpleCSVDataProvider 是否能够正确处理目标数据目录。
"""

import sys
from pathlib import Path

# 添加backend路径到sys.path
backend_path = Path(__file__).parent / 'backend'
if backend_path.exists():
    sys.path.insert(0, str(backend_path))
    from data_provider.simple_provider import SimpleCSVDataProvider
else:
    # 如果在jq-backtest-standalone-full目录中运行
    sys.path.insert(0, str(Path(__file__).parent))
    try:
        from backend.data_provider.simple_provider import SimpleCSVDataProvider
    except ImportError:
        print("❌ 无法导入 SimpleCSVDataProvider")
        print(f"   当前路径: {Path(__file__).parent}")
        print(f"   Backend路径: {backend_path}")
        sys.exit(1)


def test_initialization():
    """测试初始化"""
    print("\n" + "=" * 60)
    print("测试1: 初始化 SimpleCSVDataProvider")
    print("=" * 60)
    
    try:
        # 使用目标数据路径
        provider = SimpleCSVDataProvider('/Volumes/Extreme SSD/stockdata')
        print(f"✅ 初始化成功")
        print(f"   数据根目录: {provider.data_root}")
        print(f"   格式类型: {'主系统格式' if provider.is_main_system else '简化格式'}")
        return provider
    except Exception as e:
        print(f"❌ 初始化失败: {e}")
        return None


def test_path_resolution(provider):
    """测试路径解析"""
    print("\n" + "=" * 60)
    print("测试2: 路径解析")
    print("=" * 60)
    
    test_cases = [
        ('000001.XSHE', 'daily', None, 'daily/000001.XSHE.csv'),
        ('000001.XSHE', 'daily', 'qfq', 'daily/000001.XSHE_qfq.csv'),
        ('000001.XSHE', 'daily', 'hfq', 'daily/000001.XSHE_hfq.csv'),
        ('000001.XSHE', '1min', None, 'minute/000001.XSHE.csv'),
    ]
    
    all_passed = True
    for security, freq, adjust, expected_suffix in test_cases:
        try:
            if provider.is_main_system:
                path = provider._get_main_system_path(security, freq, adjust)
            else:
                path = provider._get_simple_path(security, freq, adjust)
            
            # 验证路径是否以预期后缀结尾
            path_str = str(path)
            if path_str.endswith(expected_suffix):
                print(f"✅ 路径解析匹配: {expected_suffix}")
                print(f"   完整路径: {path}")
            else:
                print(f"❌ 路径解析不匹配: {expected_suffix}")
                print(f"   期望后缀: {expected_suffix}")
                print(f"   实际路径: {path}")
                all_passed = False
                
        except Exception as e:
            print(f"❌ 路径解析失败 ({expected_suffix}): {e}")
            all_passed = False
    
    return all_passed


def test_data_loading(provider):
    """测试数据加载（如果文件存在）"""
    print("\n" + "=" * 60)
    print("测试3: 数据加载")
    print("=" * 60)
    
    try:
        # 尝试加载数据
        df = provider.load_data(
            security='000001.XSHE',
            freq='daily',
            start_date='2024-01-01',
            end_date='2024-12-31',
            adjust='none'
        )
        
        if df is not None and not df.empty:
            print(f"✅ 数据加载成功")
            print(f"   数据行数: {len(df)}")
            print(f"   数据列: {df.columns.tolist()}")
            print(f"   时间范围: {df.index[0]} 到 {df.index[-1]}")
            return True
        else:
            print(f"⚠️  数据文件不存在或为空（这是正常的，如果还没有准备数据）")
            print(f"   预期数据路径: /Volumes/Extreme SSD/stockdata/daily/000001.XSHE.csv")
            return True  # 文件不存在不算错误
            
    except FileNotFoundError as e:
        print(f"⚠️  数据文件不存在（这是正常的，如果还没有准备数据）")
        print(f"   {e}")
        return True  # 文件不存在不算错误
    except Exception as e:
        print(f"❌ 数据加载失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_list_securities(provider):
    """测试列出证券"""
    print("\n" + "=" * 60)
    print("测试4: 列出可用证券")
    print("=" * 60)
    
    try:
        securities = provider.list_securities()
        if securities:
            print(f"✅ 找到 {len(securities)} 个证券")
            print(f"   示例: {securities[:5]}")
        else:
            print(f"⚠️  未找到证券（这是正常的，如果还没有准备数据）")
        return True
    except Exception as e:
        print(f"❌ 列出证券失败: {e}")
        return False


def test_format_detection(provider):
    """测试格式检测"""
    print("\n" + "=" * 60)
    print("测试5: 格式检测")
    print("=" * 60)
    
    # 检查是否正确识别为简化格式
    if not provider.is_main_system:
        print(f"✅ 格式检测正确: 识别为简化格式")
        print(f"   (因为不存在 dailyweekly/ 目录)")
        return True
    else:
        print(f"⚠️  格式检测异常: 识别为主系统格式")
        print(f"   (预期应该是简化格式)")
        return False


def main():
    """主测试函数"""
    print("🧪 开始数据兼容性测试")
    print(f"目标数据路径: /Volumes/Extreme SSD/stockdata")
    
    # 测试1: 初始化
    provider = test_initialization()
    if not provider:
        print("\n❌ 测试失败: 无法初始化")
        return False
    
    # 测试2: 路径解析
    path_test = test_path_resolution(provider)
    
    # 测试3: 数据加载
    load_test = test_data_loading(provider)
    
    # 测试4: 列出证券
    list_test = test_list_securities(provider)
    
    # 测试5: 格式检测
    format_test = test_format_detection(provider)
    
    # 总结
    print("\n" + "=" * 60)
    print("📊 测试总结")
    print("=" * 60)
    
    all_tests = {
        "初始化": provider is not None,
        "路径解析": path_test,
        "数据加载": load_test,
        "列出证券": list_test,
        "格式检测": format_test,
    }
    
    for test_name, result in all_tests.items():
        status = "✅" if result else "❌"
        print(f"{status} {test_name}")
    
    all_passed = all(all_tests.values())
    
    if all_passed:
        print("\n🎉 所有测试通过!")
        print("\n📝 使用说明:")
        print("  1. 将数据文件放在: /Volumes/Extreme SSD/stockdata/")
        print("  2. 目录结构:")
        print("     ├── daily/")
        print("     │   ├── 000001.XSHE.csv        # 不复权")
        print("     │   ├── 000001.XSHE_qfq.csv    # 前复权")
        print("     │   └── 000001.XSHE_hfq.csv    # 后复权")
        print("     └── minute/")
        print("         └── 000001.XSHE.csv         # 分钟数据")
        print("\n  3. 使用代码:")
        print("     from backend.data_provider.simple_provider import SimpleCSVDataProvider")
        print("     provider = SimpleCSVDataProvider('/Volumes/Extreme SSD/stockdata')")
        print("     df = provider.load_data(security='000001.XSHE', frequency='daily', ...)")
        return True
    else:
        print("\n❌ 部分测试失败")
        return False


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
