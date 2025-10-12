"""
角色化大语言模型知识库管理系统 - 完整版主应用

提供API服务的FastAPI主应用程序。
"""

import os
import time
import uuid
from typing import Dict, List, Any, Optional

from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.core.character.generator import CharacterGenerator
from app.core.llm.openai_client import CharacterLLM
from app.core.memory.vector_store import ChromaMemoryStore
from app.core.response.flow import ResponseFlow

# 创建FastAPI应用
app = FastAPI(
    title="角色化大语言模型知识库管理系统",
    description="一个支持角色建模、记忆管理和智能对话的AI框架",
    version="1.0.0"
)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 在生产环境中应该限制为特定域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 创建全局组件
character_llm = CharacterLLM()
character_generator = CharacterGenerator(character_llm)
memory_store = ChromaMemoryStore(persist_directory="./chroma_db")
response_flow = ResponseFlow(character_llm, memory_store)

# 数据模型
class CharacterGenerationRequest(BaseModel):
    description: str

class CharacterResponse(BaseModel):
    id: str
    name: str
    age: int
    gender: str
    occupation: str
    hobby: str  # 新增
    skill: str  # 新增
    values: str  # 新增
    living_habit: str  # 新增
    dislike: str  # 新增
    language_style: str  # 新增
    appearance: str  # 新增
    family_status: str  # 新增
    education: str  # 新增
    social_pattern: str  # 新增
    favorite_thing: str  # 新增
    usual_place: str  # 新增
    past_experience: str  # 新增
    speech_style: str
    personality: Dict[str, int]
    background: str

class MemoryResponse(BaseModel):
    id: str
    type: str
    title: str
    content: str
    time: str
    emotion: str
    importance: int

class ChatRequest(BaseModel):
    character_id: str
    message: str
    conversation_history: Optional[List[Dict[str, str]]] = None

class ChatResponse(BaseModel):
    message: str
    type: str
    memories: Optional[List[Dict[str, Any]]] = None

# 内存存储角色数据（在生产环境中应该使用数据库）
characters = {}

# API路由
@app.get("/")
async def root():
    return {"message": "欢迎使用角色化大语言模型知识库管理系统"}

@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.get("/api/v1/system/status")
async def system_status():
    return {
        "status": "ok",
        "version": "1.0.0",
        "components": {
            "llm": "OpenAI GPT-4",
            "vector_db": "ChromaDB",
            "character_count": len(characters)
        }
    }

@app.post("/api/v1/characters/generate", response_model=CharacterResponse)
async def generate_character(request: CharacterGenerationRequest, background_tasks: BackgroundTasks):
    start_time = time.time()  # 记录角色生成开始时间
    try:
        # 生成角色数据
        character_data = character_generator.generate_character(request.description)
        
        # 检查生成结果
        if "error" in character_data:
            raise ValueError(f"LLM返回错误: {character_data.get('error')}")
        
        # 生成角色ID并存储
        character_id = str(uuid.uuid4())
        characters[character_id] = character_data
        
        # 计算角色生成耗时
        role_gen_time = time.time() - start_time
        print(f"=== 角色 [{character_id}] 生成耗时: {role_gen_time:.2f} 秒 ===")
        
        # 后台生成记忆（传递角色生成开始时间，用于计算总耗时）
        background_tasks.add_task(
            generate_and_store_memories,
            character_id,
            character_data,
            start_time
        )
        
        # 返回角色数据
        return {"id": character_id, **character_data}
    except Exception as e:
        import traceback
        error_detail = f"角色生成失败: {str(e)}\n{traceback.format_exc()}"
        print(error_detail)
        raise HTTPException(status_code=500, detail=f"角色生成失败: {str(e)}")

@app.get("/api/v1/characters", response_model=List[CharacterResponse])
async def list_characters():
    return [
        {"id": character_id, **character_data}
        for character_id, character_data in characters.items()
    ]

@app.get("/api/v1/characters/{character_id}", response_model=CharacterResponse)
async def get_character(character_id: str):
    if character_id not in characters:
        raise HTTPException(status_code=404, detail="角色不存在")
    
    return {
        "id": character_id,
        **characters[character_id]
    }

@app.get("/api/v1/characters/{character_id}/memories", response_model=List[MemoryResponse])
async def get_character_memories(character_id: str):
    if character_id not in characters:
        raise HTTPException(status_code=404, detail="角色不存在")
    
    # 查询所有记忆
    memories = memory_store.query_memories(
        character_id=character_id,
        query_text="",  # 空查询返回所有记忆
        n_results=100
    )
    
    return memories

@app.post("/api/v1/characters/{character_id}/memories/regenerate")
async def regenerate_character_memories(character_id: str, background_tasks: BackgroundTasks):
    if character_id not in characters:
        raise HTTPException(status_code=404, detail="角色不存在")
    
    # 删除现有记忆
    memory_store.delete_all_memories(character_id)
    
    # 在后台重新生成记忆
    background_tasks.add_task(
        generate_and_store_memories,
        character_id,
        characters[character_id]
    )
    
    return {"message": "记忆重新生成任务已启动"}

@app.post("/api/v1/chat", response_model=ChatResponse)
async def chat_with_character(request: ChatRequest):
    if request.character_id not in characters:
        raise HTTPException(status_code=404, detail="角色不存在")
    
    character_data = characters[request.character_id]
    
    try:
        # 处理对话
        responses = []
        async for response in response_flow.process(
            character_id=request.character_id,
            character_data=character_data,
            user_input=request.message,
            conversation_history=request.conversation_history
        ):
            responses.append(response)
        
        # 如果有补充响应，返回补充响应
        if len(responses) > 1 and responses[1]["type"] == "supplementary" and responses[1]["content"]:
            return {
                "message": responses[1]["content"],
                "type": "supplementary",
                "memories": responses[1]["memories"]
            }
        
        # 否则返回下意识响应
        return {
            "message": responses[0]["content"],
            "type": "immediate",
            "memories": None
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"对话生成失败: {str(e)}")

@app.get("/api/v1/chat/{character_id}/history")
async def get_chat_history(character_id: str):
    # 这里应该实现对话历史的存储和检索
    # 当前版本不实现此功能，返回空列表
    return []

# 后台任务
async def generate_and_store_memories(character_id: str, character_data: Dict[str, Any], role_start_time: float):
    """
    生成并存储角色记忆
    
    Args:
        character_id: 角色ID
        character_data: 角色数据
    """
    memory_start = time.time()
    try:
        print(f"=== 开始生成角色 [{character_id}] 的记忆 ===")
        # 生成记忆
        memories = character_generator.generate_memories(character_data, count=5)
        
        # 存储记忆
        memory_store.add_memories(character_id, memories)
        # 计算耗时
        memory_gen_time = time.time() - memory_start
        total_time = time.time() - role_start_time
        print(f"=== 角色 [{character_id}] 记忆生成耗时: {memory_gen_time:.2f} 秒 ===")
        print(f"=== 从角色生成到记忆存储完成，总耗时: {total_time:.2f} 秒 ===")
    except Exception as e:
        print(f"记忆生成失败: {str(e)}")

# 启动服务器
if __name__ == "__main__":
    import uvicorn
    
    # 获取端口
    port = int(os.environ.get("PORT", 8000))
    
    # 启动服务器
    uvicorn.run("app.main_full:app", host="0.0.0.0", port=port, reload=True)
