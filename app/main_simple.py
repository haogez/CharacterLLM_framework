from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.endpoints import chat_simple
from app.db.session_simple import create_tables

# 创建FastAPI应用
app = FastAPI(
    title="角色化大语言模型知识库管理系统 (演示版)",
    description="一个支持角色建模、记忆管理和智能对话的AI框架演示版本",
    version="1.0.0-demo"
)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 在生产环境中应该设置具体的域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 包含路由
app.include_router(chat_simple.router, prefix="/api/v1", tags=["角色与对话"])

@app.on_event("startup")
async def startup_event():
    """应用启动时的初始化操作"""
    # 创建数据库表
    create_tables()
    print("数据库表创建完成")
    print("演示版应用启动成功！")
    print("注意：当前运行的是简化演示版本，使用模拟数据和模板响应")

@app.get("/")
async def root():
    """根路径"""
    return {
        "message": "欢迎使用角色化大语言模型知识库管理系统 (演示版)",
        "version": "1.0.0-demo",
        "mode": "demonstration",
        "docs": "/docs",
        "api_prefix": "/api/v1",
        "features": [
            "角色生成（基于预设模板）",
            "记忆管理（内存存储）", 
            "三阶段对话流程（模拟响应）",
            "OCEAN五维人格建模",
            "Web界面交互"
        ],
        "note": "这是一个演示版本，展示了系统的核心架构和功能流程"
    }

@app.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "healthy", "message": "演示系统运行正常", "mode": "demo"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
