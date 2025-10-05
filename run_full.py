#!/usr/bin/env python3
"""
角色化大语言模型知识库管理系统 - 完整版启动脚本
"""

import os
import sys
import uvicorn

def main():
    """主函数"""
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
