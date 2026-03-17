#!/usr/bin/env python3
"""
获取百度首页页面信息的脚本
"""

import requests
from bs4 import BeautifulSoup
import time
import sys

def get_baidu_page_info():
    """
    获取百度首页的页面信息
    """
    url = "https://www.baidu.com"
    
    # 设置请求头，模拟浏览器访问
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
    }
    
    try:
        print(f"正在访问: {url}")
        start_time = time.time()
        
        # 发送GET请求
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()  # 如果请求失败则抛出异常
        
        end_time = time.time()
        request_time = end_time - start_time
        
        # 获取页面信息
        status_code = response.status_code
        content_length = len(response.content)
        encoding = response.encoding
        content_type = response.headers.get('Content-Type', 'unknown')
        
        print(f"\n=== 请求结果 ===")
        print(f"状态码: {status_code}")
        print(f"响应时间: {request_time:.2f}秒")
        print(f"内容长度: {content_length} 字节")
        print(f"编码: {encoding}")
        print(f"Content-Type: {content_type}")
        
        # 解析HTML内容
        soup = BeautifulSoup(response.text, 'html.parser')
        
        print(f"\n=== 页面基本信息 ===")
        print(f"标题: {soup.title.string if soup.title else '无标题'}")
        
        # 获取meta信息
        meta_tags = soup.find_all('meta')
        print(f"Meta标签数量: {len(meta_tags)}")
        
        # 获取链接数量
        links = soup.find_all('a')
        print(f"链接数量: {len(links)}")
        
        # 获取图片数量
        images = soup.find_all('img')
        print(f"图片数量: {len(images)}")
        
        # 获取脚本数量
        scripts = soup.find_all('script')
        print(f"脚本数量: {len(scripts)}")
        
        # 获取样式表数量
        styles = soup.find_all('link', rel='stylesheet')
        print(f"样式表数量: {len(styles)}")
        
        # 显示前5个链接
        print(f"\n=== 前5个链接 ===")
        for i, link in enumerate(links[:5]):
            href = link.get('href', '无链接')
            text = link.get_text(strip=True)[:50]  # 限制文本长度
            print(f"{i+1}. {text} -> {href}")
        
        # 显示响应头信息
        print(f"\n=== 响应头信息 ===")
        for key, value in response.headers.items():
            if key.lower() in ['content-type', 'server', 'date', 'content-length', 'content-encoding']:
                print(f"{key}: {value}")
        
        # 保存页面内容到文件
        with open('baidu_page_content.html', 'w', encoding='utf-8') as f:
            f.write(response.text)
        print(f"\n页面内容已保存到: baidu_page_content.html")
        
        return True
        
    except requests.exceptions.Timeout:
        print("错误: 请求超时")
        return False
    except requests.exceptions.HTTPError as e:
        print(f"HTTP错误: {e}")
        return False
    except requests.exceptions.ConnectionError:
        print("错误: 连接失败")
        return False
    except requests.exceptions.RequestException as e:
        print(f"请求异常: {e}")
        return False
    except Exception as e:
        print(f"未知错误: {e}")
        return False

def main():
    """主函数"""
    print("百度首页信息获取工具")
    print("=" * 50)
    
    success = get_baidu_page_info()
    
    if success:
        print(f"\n✅ 页面信息获取成功！")
    else:
        print(f"\n❌ 页面信息获取失败！")
        sys.exit(1)

if __name__ == "__main__":
    main()