#!/usr/bin/env python3
"""
角色化大语言模型知识库管理系统启动脚本
"""

import uvicorn
import os
import sys

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def main():
    """启动应用"""
    # 检查环境变量
    if not os.getenv("OPENAI_API_KEY"):
        print("警告: 未设置OPENAI_API_KEY环境变量")
        print("请设置环境变量: export OPENAI_API_KEY=your_api_key")
        print("或者在.env文件中配置")
    
    print("正在启动角色化大语言模型知识库管理系统...")
    print("API文档地址: http://localhost:8000/docs")
    print("系统主页: http://localhost:8000")
    
    # 启动服务器
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,  # 开发模式下启用热重载
        log_level="info"
    )

if __name__ == "__main__":
    main()
