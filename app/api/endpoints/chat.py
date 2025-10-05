from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
import os

from app.db.session import get_db
from app.schemas.character import (
    Character, CharacterCreate, CharacterUpdate, 
    CharacterGenerationRequest, ChatRequest, ChatResponse
)
from app.crud.crud_character import (
    create_character, get_character, get_characters, 
    update_character, delete_character
)
from app.crud.crud_memory import get_all_memories, clear_character_memories
from app.core.character_generator import CharacterGenerator
from app.core.memory_generator import MemoryGenerator
from app.core.response_flow import ResponseFlow

router = APIRouter()

# 初始化核心组件
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("请设置OPENAI_API_KEY环境变量")

character_generator = CharacterGenerator(OPENAI_API_KEY)
memory_generator = MemoryGenerator(OPENAI_API_KEY)
response_flow = ResponseFlow(OPENAI_API_KEY)

@router.post("/characters/generate", response_model=Character)
async def generate_character(
    request: CharacterGenerationRequest,
    db: Session = Depends(get_db)
):
    """从自然语言描述生成角色"""
    try:
        # 生成角色人设
        character_data = character_generator.generate_character(request.description)
        
        # 保存到数据库
        db_character = create_character(db, character_data)
        
        # 生成记忆
        memory_generator.generate_memories(db_character, num_memories=8)
        
        return db_character
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"生成角色失败: {str(e)}")

@router.get("/characters", response_model=List[Character])
def list_characters(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """获取角色列表"""
    characters = get_characters(db, skip=skip, limit=limit)
    return characters

@router.get("/characters/{character_id}", response_model=Character)
def get_character_detail(character_id: int, db: Session = Depends(get_db)):
    """获取角色详情"""
    character = get_character(db, character_id)
    if character is None:
        raise HTTPException(status_code=404, detail="角色不存在")
    return character

@router.put("/characters/{character_id}", response_model=Character)
def update_character_info(
    character_id: int,
    character_update: CharacterUpdate,
    db: Session = Depends(get_db)
):
    """更新角色信息"""
    character = update_character(db, character_id, character_update)
    if character is None:
        raise HTTPException(status_code=404, detail="角色不存在")
    return character

@router.delete("/characters/{character_id}")
def delete_character_info(character_id: int, db: Session = Depends(get_db)):
    """删除角色"""
    success = delete_character(db, character_id)
    if not success:
        raise HTTPException(status_code=404, detail="角色不存在")
    
    # 同时清空角色记忆
    clear_character_memories(character_id)
    
    return {"message": "角色删除成功"}

@router.get("/characters/{character_id}/memories")
def get_character_memories(character_id: int, db: Session = Depends(get_db)):
    """获取角色记忆"""
    character = get_character(db, character_id)
    if character is None:
        raise HTTPException(status_code=404, detail="角色不存在")
    
    memories = get_all_memories(character_id)
    return {"character_id": character_id, "memories": memories}

@router.post("/characters/{character_id}/memories/regenerate")
def regenerate_character_memories(
    character_id: int, 
    num_memories: int = 8,
    db: Session = Depends(get_db)
):
    """重新生成角色记忆"""
    character = get_character(db, character_id)
    if character is None:
        raise HTTPException(status_code=404, detail="角色不存在")
    
    # 清空现有记忆
    clear_character_memories(character_id)
    
    # 生成新记忆
    memory_ids = memory_generator.generate_memories(character, num_memories)
    
    return {"message": f"成功生成{len(memory_ids)}条记忆", "memory_ids": memory_ids}

@router.post("/chat", response_model=ChatResponse)
async def chat_with_character(request: ChatRequest, db: Session = Depends(get_db)):
    """与角色对话"""
    character = get_character(db, request.character_id)
    if character is None:
        raise HTTPException(status_code=404, detail="角色不存在")
    
    try:
        # 执行三阶段响应流程
        result = await response_flow.process_message(character, request.message)
        
        # 构建响应
        response = ChatResponse(
            character_id=result["character_id"],
            response=result.get("supplemented_response", result["response"]),
            response_type=result["response_type"],
            timestamp=result["timestamp"]
        )
        
        return response
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"对话处理失败: {str(e)}")

@router.get("/chat/{character_id}/history")
def get_chat_history(character_id: int, db: Session = Depends(get_db)):
    """获取对话历史"""
    character = get_character(db, character_id)
    if character is None:
        raise HTTPException(status_code=404, detail="角色不存在")
    
    history = response_flow.conversation_history.get(character_id, [])
    return {"character_id": character_id, "history": history}
