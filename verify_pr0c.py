import sys
import os

# 确保能找到 gateway 模块
sys.path.append(os.getcwd())

def verify_language_strategy():
    print(">>> 开始验证 PR-0C (语言策略解耦 & 新增语种)...")

    # 1. 验证 utils 模块是否存在
    try:
        from gateway.app.utils.languages import get_lang_name, get_default_voice, LANGUAGE_CONFIG
        print("✅ 语言工具模块 (utils.languages) 导入成功")
    except ImportError as e:
        print(f"❌ 模块缺失: {e}")
        return

    # 2. 验证多语种配置 (含新增的 id, ms)
    test_cases = [
        ("my", "Burmese", "my-MM-TularWinNeural"),      # 原有
        ("vi", "Vietnamese", "vi-VN-HoaiMyNeural"),     # 扩展
        ("id", "Indonesian", "id-ID-GadisNeural"),      # 新增
        ("ms", "Malay", "ms-MY-YasminNeural")           # 新增
    ]

    all_passed = True
    for code, expected_name, expected_voice in test_cases:
        # A. 测试语言名称映射
        name = get_lang_name(code)
        if name != expected_name:
            print(f"❌ {code} 名称错误: 期望 {expected_name}, 实际 {name}")
            all_passed = False
        else:
            print(f"✅ {code} -> {name}")

        # B. 测试默认配音映射
        voice = get_default_voice(code)
        if voice != expected_voice:
            print(f"❌ {code} 配音错误: 期望 {expected_voice}, 实际 {voice}")
            all_passed = False
    
    if all_passed:
        print("✅ 所有语言配置验证通过")

    # 3. 验证业务逻辑是否去除了硬编码 (静态检查)
    # 我们检查 gemini_subtitles.py 文件里是否还有写死的 "Burmese"
    print("\n>>> 正在检查代码硬编码残留...")
    target_file = "gateway/app/services/gemini_subtitles.py"
    
    if os.path.exists(target_file):
        with open(target_file, "r", encoding="utf-8") as f:
            content = f.read()
            # 检查关键点：是否引入了 get_lang_name
            if "get_lang_name" in content:
                print("✅ Gemini 服务已引入 get_lang_name")
            else:
                print("⚠️ 警告: Gemini 服务似乎未引入语言工具 (可能还在用硬编码)")
            
            # 检查 prompt 模板里是否还有写死的 "Burmese"
            # 注意：注释里的 Burmese 不算，我们简单查一下
            if 'Translate to Burmese' in content or 'Target Language: Burmese' in content:
                 print("❌ 警告: 代码中似乎仍有 'Translate to Burmese' 硬编码！请检查 Prompt 模板。")
            else:
                print("✅ 未发现明显的 'Burmese' 硬编码字符串")
    else:
        print(f"⚠️ 找不到文件 {target_file}，跳过静态检查")

if __name__ == "__main__":
    verify_language_strategy()