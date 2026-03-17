#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import datetime

def get_current_time():
    """
    获取当前系统时间并格式化输出
    """
    # 获取当前日期和时间
    current_time = datetime.datetime.now()
    
    # 格式化为字符串
    formatted_time = current_time.strftime("%Y-%m-%d %H:%M:%S")
    
    return formatted_time, current_time

def main():
    """
    主函数：获取并打印当前时间
    """
    try:
        # 获取当前时间
        formatted_time, full_time = get_current_time()
        
        # 打印格式化后的时间
        print(f"当前系统时间: {formatted_time}")
        
        # 打印各个时间组件
        print(f"年: {full_time.year}")
        print(f"月: {full_time.month}")
        print(f"日: {full_time.day}")
        print(f"时: {full_time.hour}")
        print(f"分: {full_time.minute}")
        print(f"秒: {full_time.second}")
        print(f"星期: {full_time.strftime('%A')} (星期{full_time.strftime('%w')})")
        
        return 0
    except Exception as e:
        print(f"获取时间时出错: {e}")
        return 1

if __name__ == "__main__":
    exit_code = main()
    exit(exit_code)