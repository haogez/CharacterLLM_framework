#!/usr/bin/env python3
"""
角色化大语言模型知识库管理系统演示版启动脚本
"""

import uvicorn
import os
import sys

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def main():
    """启动演示版应用"""
    
    print("=" * 60)
    print("角色化大语言模型知识库管理系统 - 演示版")
    print("=" * 60)
    print("正在启动演示版系统...")
    print()
    print("系统特性:")
    print("• 角色生成：基于预设模板和关键词匹配")
    print("• 记忆管理：使用内存存储，支持简单检索")
    print("• 对话流程：三阶段响应机制的模拟实现")
    print("• 人格建模：OCEAN五维人格特征量化")
    print("• Web界面：现代化的React前端界面")
    print()
    print("访问地址:")
    print("• API文档: http://localhost:8000/docs")
    print("• 系统主页: http://localhost:8000")
    print("• 前端界面: http://localhost:3000 (需单独启动)")
    print()
    print("注意：这是演示版本，展示系统架构和核心功能")
    print("=" * 60)
    
    # 启动服务器
    uvicorn.run(
        "app.main_simple:app",
        host="0.0.0.0",
        port=8000,
        reload=True,  # 开发模式下启用热重载
        log_level="info"
    )

if __name__ == "__main__":
    main()
