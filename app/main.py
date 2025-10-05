from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.endpoints import chat
from app.db.session import create_tables

# 创建FastAPI应用
app = FastAPI(
    title="角色化大语言模型知识库管理系统",
    description="一个支持角色建模、记忆管理和智能对话的AI框架",
    version="1.0.0"
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
app.include_router(chat.router, prefix="/api/v1", tags=["角色与对话"])

@app.on_event("startup")
async def startup_event():
    """应用启动时的初始化操作"""
    # 创建数据库表
    create_tables()
    print("数据库表创建完成")
    print("应用启动成功！")

@app.get("/")
async def root():
    """根路径"""
    return {
        "message": "欢迎使用角色化大语言模型知识库管理系统",
        "version": "1.0.0",
        "docs": "/docs",
        "api_prefix": "/api/v1"
    }

@app.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "healthy", "message": "系统运行正常"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
