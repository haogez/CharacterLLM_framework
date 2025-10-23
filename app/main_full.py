"""
角色化大语言模型知识库管理系统 - 完整版主应用
适配完整记忆格式 + 多响应类型（direct/immediate/supplementary/no_memory）
支持实时响应流（SSE）+ 直接日志输出
"""

import os
import time
import json
import uuid
import traceback
import asyncio # 1. 添加 asyncio 导入
from typing import Dict, List, Any, Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core.character.generator import CharacterGenerator
from app.core.llm.openai_client import CharacterLLM
from app.core.memory.vector_store import ChromaMemoryStore
from app.core.response.flow import ResponseFlow

app = FastAPI(
    title="角色化大语言模型知识库管理系统",
    description="支持完整记忆格式+多响应类型的AI对话框架",
    version="2.2.2"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

character_llm = CharacterLLM()
character_generator = CharacterGenerator(character_llm)
memory_store = ChromaMemoryStore(persist_directory="./chroma_db_full")
response_flow = ResponseFlow(character_llm, memory_store)

# ------------------------------------------------------------------------------
# 核心修改1：定义适配「完整记忆格式」的数据模型（嵌套Pydantic模型）
# ------------------------------------------------------------------------------
class TimeDetail(BaseModel):
    age: int
    period: str
    specific: str

class EmotionDetail(BaseModel):
    immediate: List[str]
    reflected: List[str]
    residual: str
    intensity: int

class ImportanceDetail(BaseModel):
    score: int
    reason: str
    frequency: str

class BehaviorImpactDetail(BaseModel):
    habit_formed: str
    attitude_change: str
    response_pattern: str

class TriggerSystemDetail(BaseModel):
    sensory: List[str]
    contextual: List[str]
    emotional: List[str]

class MemoryDistortionDetail(BaseModel):
    exaggerated: str
    downplayed: str
    reason: str

class MemoryResponse(BaseModel):
    id: str
    type: Optional[str] = "general"
    title: str
    content: str
    time: Optional[TimeDetail] = TimeDetail(age=0, period="未知", specific="未知")
    emotion: Optional[EmotionDetail] = EmotionDetail(immediate=[], reflected=[], residual="", intensity=0)
    importance: Optional[ImportanceDetail] = ImportanceDetail(score=5, reason="", frequency="")
    behavior_impact: Optional[BehaviorImpactDetail] = BehaviorImpactDetail(habit_formed="", attitude_change="", response_pattern="")
    trigger_system: Optional[TriggerSystemDetail] = TriggerSystemDetail(sensory=[], contextual=[], emotional=[])
    memory_distortion: Optional[MemoryDistortionDetail] = MemoryDistortionDetail(exaggerated="", downplayed="", reason="")
    relevance: Optional[float] = None

# ------------------------------------------------------------------------------
# 核心修改2：定义适配「多响应类型」的对话模型
# ------------------------------------------------------------------------------
class CharacterGenerationRequest(BaseModel):
    description: str

class CharacterResponse(BaseModel):
    id: str
    name: str
    age: int
    gender: str
    occupation: str
    hobby: str
    skill: str
    values: str
    living_habit: str
    dislike: str
    language_style: str
    appearance: str
    family_status: str
    education: str
    social_pattern: str
    favorite_thing: str
    usual_place: str
    past_experience: str
    speech_style: str
    personality: Dict[str, int]
    background: str

class ChatRequest(BaseModel):
    character_id: str
    message: str
    conversation_history: Optional[List[Dict[str, str]]] = None

class ChatResponse(BaseModel):
    message: str
    type: str
    memories: Optional[List[MemoryResponse]] = None
    timestamp: Optional[float] = None

characters: Dict[str, Dict[str, Any]] = {}

# ------------------------------------------------------------------------------
# API路由（核心修改：对话接口使用SSE实现实时响应流 + 直接日志输出）
# ------------------------------------------------------------------------------
@app.get("/")
async def root():
    return {"message": "欢迎使用角色化大语言模型知识库管理系统（V2.2.2，支持实时响应流+直接日志输出）"}

@app.get("/health")
async def health_check():
    return {"status": "ok", "version": "2.2.2"}

@app.get("/api/v1/system/status")
async def system_status():
    return {
        "status": "ok",
        "version": "2.2.2",
        "components": {
            "llm": "OpenAI GPT-4",
            "vector_db": "ChromaDB（支持完整记忆格式）",
            "character_count": len(characters),
            "response_types": ["direct", "immediate", "supplementary", "no_memory"],
            "features": ["实时响应流", "完整记忆格式", "多响应类型", "直接日志输出"]
        }
    }
        
# 2. 修改：generate_character 端点改为 async
@app.post("/api/v1/characters/generate", response_model=CharacterResponse)
async def generate_character(request: CharacterGenerationRequest, background_tasks: BackgroundTasks):
    """生成角色"""
    start_time = time.time()
    try:
        # 3. 修改：await 调用异步生成方法
        character_data = await character_generator.generate_character(request.description)
        if "error" in character_data:
            raise ValueError(f"LLM生成角色失败: {character_data['error']}")
        
        character_id = str(uuid.uuid4())
        characters[character_id] = character_data
        
        role_gen_time = time.time() - start_time
        print(f"=== 角色 [{character_id}: {character_data['name']}] 生成耗时: {role_gen_time:.2f} 秒 ===")
        
        background_tasks.add_task(
            generate_and_store_memories,
            character_id,
            character_data,
            start_time
        )
        
        return {
            "id": character_id,
            **character_data,
            "generation_info": {
                "start_time": start_time,
                "role_gen_time": round(role_gen_time, 2),
                "status": "generating_memories"
            }
        }
    except Exception as e:
        error_detail = f"角色生成失败: {str(e)}\n{traceback.format_exc()}"
        print(error_detail)
        raise HTTPException(status_code=500, detail=f"角色生成失败: {str(e)}")

@app.get("/api/v1/characters", response_model=List[CharacterResponse])
async def list_characters():
    return [{"id": cid, **cdata} for cid, cdata in characters.items()]

@app.get("/api/v1/characters/{character_id}", response_model=CharacterResponse)
async def get_character(character_id: str):
    if character_id not in characters:
        raise HTTPException(status_code=404, detail="角色不存在")
    return {"id": character_id, **characters[character_id]}

# ------------------------------------------------------------------------------
# 核心修改3：记忆查询接口（适配完整记忆格式，反序列化JSON字段）
# ------------------------------------------------------------------------------
@app.get("/api/v1/characters/{character_id}/memories", response_model=List[MemoryResponse])
async def get_character_memories(character_id: str):
    if character_id not in characters:
        raise HTTPException(status_code=404, detail="角色不存在")
    
    # Note: This uses the sync method. If performance is critical, you might want to add an async version here too.
    raw_memories = memory_store.query_memories(
        character_id=character_id,
        query_text="",
        n_results=100,
        return_full_fields=True
    )
    
    processed_memories = []
    for mem in raw_memories:
        try:
            for key in ["time", "emotion", "importance", "behavior_impact", "trigger_system", "memory_distortion"]:
                if key in mem and isinstance(mem[key], str):
                    mem[key] = json.loads(mem[key])
            processed_memories.append(MemoryResponse(**mem))
        except Exception as e:
            print(f"跳过格式异常的记忆: {str(e)} | 记忆ID: {mem.get('id', '未知')}")
            continue
    
    return processed_memories

@app.post("/api/v1/characters/{character_id}/memories/regenerate")
async def regenerate_character_memories(character_id: str, background_tasks: BackgroundTasks):
    if character_id not in characters:
        raise HTTPException(status_code=404, detail="角色不存在")
    
    memory_store.delete_all_memories(character_id)
    print(f"=== 已删除角色 [{character_id}] 的所有旧记忆 ===")
    
    background_tasks.add_task(
        generate_and_store_memories,
        character_id,
        characters[character_id]
    )
    
    return {"message": "完整记忆重新生成任务已启动", "character_id": character_id}

# ------------------------------------------------------------------------------
# 核心修改4：对话接口（使用SSE实现实时响应流 + 直接日志输出）
# 4. 修改：chat_with_character 端点改为 async
# ------------------------------------------------------------------------------
@app.post("/api/v1/chat", response_class=StreamingResponse)
async def chat_with_character(request: ChatRequest):
    """对话接口：使用SSE实现实时响应流 + 直接日志输出"""
    if request.character_id not in characters:
        raise HTTPException(status_code=404, detail="角色不存在")
    character_data = characters[request.character_id]
    
    # 5. 修改：event_generator 函数改为 async
    async def event_generator():
        try:
            start_time = time.time()
            
            print("\n" + "="*80)
            print("🔄 开始处理对话请求 | 角色ID:", request.character_id)
            print(f"📌 用户输入: {request.message}")
            print("="*80)
            
            # 6. 修改：使用 async for 遍历异步生成器
            response_count = 0
            async for flow_resp in response_flow.process(
                character_id=request.character_id,
                character_data=character_data,
                user_input=request.message,
                conversation_history=request.conversation_history
            ):
                response_count += 1
                current_resp = ChatResponse(
                    message=flow_resp["content"],
                    type=flow_resp["type"],
                    memories=None,
                    timestamp=flow_resp.get("timestamp", None)
                )
                
                if "memories" in flow_resp and flow_resp["memories"]:
                    processed_mem = []
                    for mem in flow_resp["memories"]:
                        for key in ["time", "emotion", "importance", "behavior_impact", "trigger_system", "memory_distortion"]:
                            if key in mem and isinstance(mem[key], str):
                                mem[key] = json.loads(mem[key])
                        processed_mem.append(MemoryResponse(**mem))
                    current_resp.memories = processed_mem
                
                response_data = current_resp.dict()
                response_json = json.dumps(response_data, ensure_ascii=False)
                
                yield f" {response_json}\n\n"
                
                print("\n" + "="*80)
                print(f"🔄 {flow_resp['type'].upper()}响应发送 | 角色ID: {request.character_id}")
                print(f"📌 用户输入: {request.message}")
                print(f"💬 响应内容: {flow_resp['content'][:150]}{'...' if len(flow_resp['content']) > 150 else ''}")
                print(f"⏱️  耗时: {flow_resp.get('timestamp', 0):.2f}秒")
                if current_resp.memories:
                    print(f"🧠 关联记忆数: {len(current_resp.memories)}")
                    for j, mem in enumerate(current_resp.memories):
                        print(f"     📝 记忆 {j+1}: {mem.title} (相关性: {mem.relevance:.3f})")
                print("="*80 + "\n")
        
            total_time = time.time() - start_time
            print("\n" + "="*80)
            print(f"✅ 对话响应完成 | 角色ID: {request.character_id}")
            print(f"📌 用户输入: {request.message}")
            print(f"⏱️  总耗时: {total_time:.2f}秒")
            print(f"📊 发送响应数: {response_count}")
            print("="*80 + "\n")
        
        except Exception as e:
            error_detail = f"对话生成失败: {str(e)}\n{traceback.format_exc()}"
            print(error_detail)
            error_data = {"error": str(e)}
            error_json = json.dumps(error_data, ensure_ascii=False)
            yield f" {error_json}\n\n"
    
    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.get("/api/v1/chat/{character_id}/history")
async def get_chat_history(character_id: str):
    return {"message": "对话历史功能暂未实现", "character_id": character_id, "history": []}

# ------------------------------------------------------------------------------
# 核心修改5：后台任务（生成+存储完整格式记忆，处理嵌套JSON序列化）
# 7. 修改：generate_and_store_memories 任务改为 async
# ------------------------------------------------------------------------------
async def generate_and_store_memories(
    character_id: str, 
    character_data: Dict[str, Any], 
    role_start_time: float = None
):
    """
    生成并存储「完整格式记忆」
    """
    memory_start = time.time()
    try:
        character_name = character_data.get("name", "未知角色")
        print(f"\n=== 开始生成角色 [{character_id}: {character_name}] 的完整记忆 ===")
        
        # 8. 修改：await 调用异步生成方法
        raw_memories = await character_generator.generate_memories(character_data, count=5)
        if not raw_memories:
            print(f"警告：角色 [{character_name}] 未生成任何记忆")
            return
        
        processed_memories = []
        for mem in raw_memories:
            processed_mem = {}
            for key, value in mem.items():
                if isinstance(value, dict):
                    processed_mem[key] = json.dumps(value, ensure_ascii=False)
                else:
                    processed_mem[key] = value
                if "id" not in processed_mem:
                    processed_mem["id"] = str(uuid.uuid4())
            processed_memories.append(processed_mem)
        
        # 9. 修改：await 调用异步存储方法
        memory_ids = await memory_store.add_memories_async(character_id, processed_memories)
        memory_gen_time = time.time() - memory_start
        
        print(f"=== 角色 [{character_name}] 成功存储 {len(memory_ids)} 条完整记忆 ===")
        print(f"  记忆ID列表: {memory_ids}")
        print(f"  记忆生成+存储耗时: {memory_gen_time:.2f} 秒")
        
        if role_start_time:
            total_time = time.time() - role_start_time
            print(f"  角色生成→记忆存储完整流程耗时: {total_time:.2f} 秒")
            
        if character_id in characters:
            characters[character_id]["generation_info"] = {
                "start_time": role_start_time,
                "role_gen_time": round(memory_start - role_start_time, 2),
                "memory_gen_time": round(memory_gen_time, 2),
                "total_time": round(total_time, 2),
                "status": "completed"
            }
            
    except Exception as e:
        error_detail = f"记忆生成失败: {str(e)}\n{traceback.format_exc()}"
        print(f"\n=== 角色 [{character_id}] 记忆生成失败 ===\n{error_detail}\n")

# ------------------------------------------------------------------------------
# 启动服务器
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    
    port = int(os.environ.get("PORT", 8000))
    print(f"=== 启动角色化大语言模型知识库管理系统（V2.2.2，支持实时响应流+直接日志输出） ===")
    print(f"  端口: {port}")
    print(f"  记忆存储路径: ./chroma_db_full")
    print(f"  支持响应类型: direct/immediate/supplementary/no_memory")
    print(f"  支持特性: 实时响应流(SSE), 直接日志输出")
    
    uvicorn.run(
        "app.main_full:app",
        host="0.0.0.0",
        port=port,
        reload=True,
        log_level="info"
    )