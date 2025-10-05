#!/usr/bin/env python3
"""
角色化大语言模型知识库管理系统 - 带环境变量加载的启动脚本
"""

import os
import sys
import uvicorn
import dotenv

def load_env():
    """加载.env文件中的环境变量"""
    # 尝试加载.env文件
    env_file = os.path.join(os.path.dirname(__file__), '.env')
    if os.path.exists(env_file):
        print(f"正在从{env_file}加载环境变量...")
        dotenv.load_dotenv(env_file)
        
        # 验证关键环境变量
        api_key = os.environ.get("OPENAI_API_KEY")
        base_url = os.environ.get("OPENAI_BASE_URL")
        
        print(f"OPENAI_API_KEY: {'已设置' if api_key else '未设置'}")
        print(f"OPENAI_BASE_URL: {'已设置' if base_url else '未设置'}")
        
        if not api_key:
            print("警告: OPENAI_API_KEY未设置，请确保已通过其他方式设置")
    else:
        print(f"警告: 未找到.env文件: {env_file}")

def main():
    """主函数"""
    # 加载环境变量
    load_env()
    
    # 确保环境变量设置
    if not os.environ.get("OPENAI_API_KEY"):
        print("错误: 未设置OPENAI_API_KEY环境变量")
        print("请设置环境变量后重试: export OPENAI_API_KEY=your_api_key")
        sys.exit(1)
    
    # 获取端口
    port = int(os.environ.get("PORT", 8000))
    
    # 启动服务器
    print(f"启动角色化大语言模型知识库管理系统 (完整版) 在端口 {port}...")
    uvicorn.run("app.main_full:app", host="0.0.0.0", port=port, reload=True)

if __name__ == "__main__":
    main()
