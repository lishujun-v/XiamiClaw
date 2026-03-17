#!/usr/bin/env python3
# -*- coding: utf-8 -*-

def print_cute_hui_min():
    """打印可爱版本的'慧敏'"""
    
    # 可爱的ASCII艺术
    cute_art = r"""
    　　　　　　／＞　　フ
    　　　　　| 　_　 _ |
     　 　　　／` ミ＿xノ
    　　 　 /　　　 　 |
    　　　 /　 ヽ　　 ﾉ
    　 　 │　　|　|　|
    ／￣|　　 |　|　|
    (￣ヽ＿_ヽ_)__)
    　＼二) 
    
    ✧･ﾟ: *✧･ﾟ:* 慧敏 *:･ﾟ✧*:･ﾟ✧
    
    🎀 最可爱的慧敏 🎀
    
    💖 特点：
    - 聪明伶俐 💡
    - 温柔体贴 🌸
    - 笑容甜美 😊
    - 心地善良 ❤️
    
    ฅ^•ﻌ•^ฅ 喵~ 慧敏最可爱啦！
    """
    
    print(cute_art)
    
    # 添加一些可爱的装饰
    print("\n" + "="*40)
    print("✨ 慧敏的可爱时刻 ✨")
    print("="*40)
    
    cute_moments = [
        "🌼 早上起床时的迷糊样子",
        "🍰 吃到甜点时的幸福表情",
        "📚 认真学习时的专注模样",
        "🎵 听到音乐时轻轻哼唱",
        "🌈 看到彩虹时惊喜的欢呼"
    ]
    
    for i, moment in enumerate(cute_moments, 1):
        print(f"{i}. {moment}")
    
    print("\n" + "❤️" * 20)
    print("慧敏，你是最棒的！")
    print("❤️" * 20)

if __name__ == "__main__":
    print_cute_hui_min()