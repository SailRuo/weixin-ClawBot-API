#!/usr/bin/env python3
"""
iLink API 快速测试脚本
用于验证后端服务是否正常运行
"""

import requests
import json

BASE_URL = "http://localhost:5000"

def test_endpoint(name, method, endpoint, data=None):
    """测试单个接口"""
    try:
        url = f"{BASE_URL}{endpoint}"
        print(f"\n{'='*60}")
        print(f"测试: {name}")
        print(f"{'='*60}")
        print(f"URL: {url}")
        print(f"方法: {method}")
        
        if method == "GET":
            response = requests.get(url)
        else:
            response = requests.post(url, json=data)
        
        print(f"状态码: {response.status_code}")
        
        try:
            result = response.json()
            print(f"响应: {json.dumps(result, indent=2, ensure_ascii=False)}")
            
            if result.get("success"):
                print(f"✅ {name} - 成功")
                return True
            else:
                print(f"❌ {name} - 失败: {result.get('error', '未知错误')}")
                return False
        except:
            print(f"响应: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ {name} - 异常: {str(e)}")
        return False

def main():
    print("="*60)
    print("iLink API 接口测试")
    print("="*60)
    
    results = []
    
    # 测试状态接口
    results.append(test_endpoint("获取系统状态", "GET", "/api/state"))
    
    # 测试获取二维码
    results.append(test_endpoint("获取登录二维码", "POST", "/api/get_qrcode"))
    
    # 测试轮询状态（可能失败，因为没有二维码）
    results.append(test_endpoint("轮询登录状态", "POST", "/api/poll_status"))
    
    # 测试获取消息（可能失败，因为未登录）
    results.append(test_endpoint("获取消息更新", "POST", "/api/get_updates"))
    
    # 测试获取消息历史
    results.append(test_endpoint("获取消息历史", "GET", "/api/messages"))
    
    # 测试清空消息
    results.append(test_endpoint("清空消息", "POST", "/api/clear_messages"))
    
    # 测试通知接口（可能失败，因为未登录）
    results.append(test_endpoint("通知开始接收", "POST", "/api/notify_start"))
    results.append(test_endpoint("通知停止接收", "POST", "/api/notify_stop"))
    
    # 测试获取上传 URL（可能失败，因为未登录）
    results.append(test_endpoint("获取上传 URL", "POST", "/api/get_upload_url", {
        "filekey": "test_file_123",
        "media_type": 1
    }))
    
    # 汇总结果
    print("\n" + "="*60)
    print("测试汇总")
    print("="*60)
    success_count = sum(results)
    total_count = len(results)
    print(f"成功: {success_count}/{total_count}")
    print(f"失败: {total_count - success_count}/{total_count}")
    
    if success_count == total_count:
        print("\n✅ 所有接口测试通过")
    else:
        print(f"\n⚠️  {total_count - success_count} 个接口测试失败")
        print("注意: 部分接口需要先登录才能正常工作")

if __name__ == "__main__":
    main()
