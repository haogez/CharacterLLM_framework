"""
角色化大语言模型知识库管理系统 - 主应用 (Neo4j版 - CSV导入版)
"""

import os
import time
import json
import uuid
import traceback
import asyncio
from typing import Dict, List, Any, Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core.character.generator import CharacterGenerator
from app.core.llm.openai_client import CharacterLLM
from app.core.memory.vector_store import ChromaMemoryStore
from app.core.response.flow import ResponseFlow
from app.core.memory.story_based_memory_generator import StoryBasedMemoryGenerator
from app.core.graph.graph_store import GraphStore
from app.core.utils.log_utils import (
    log_section_start, log_section_end, log_info, log_success, log_warning,
    log_error, log_debug, 
    log_character_creation, log_memory_generation_summary,
    log_chat_start, log_chat_response, log_chat_complete
)

app = FastAPI(
    title="角色化大语言模型知识库管理系统",
    description="支持完整记忆格式+多响应类型的AI对话框架",
    version="3.0.0"
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
response_flow = ResponseFlow(character_llm)

graph_store = GraphStore(
    uri="bolt://neo4j-latest:7687",
    user="neo4j",
    password="zyh123456",
    database="neo4j"
)
# ---

story_memory_generator = StoryBasedMemoryGenerator(character_llm)

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
    location: Optional[str] = ""
    participants: Optional[List[str]] = []
    tags: Optional[List[str]] = []
    duration: Optional[str] = ""
    context_before: Optional[str] = ""
    context_after: Optional[str] = ""
    relevance: Optional[float] = None

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

@app.get("/")
async def root():
    return {"message": "欢迎使用角色化大语言模型知识库管理系统（V3.0.0，支持细粒度记忆片段化）"}

@app.get("/health")
async def health_check():
    return {"status": "ok", "version": "3.0.0"}

@app.get("/api/v1/system/status")
async def system_status():
    return {
        "status": "ok",
        "version": "3.0.0",
        "components": {
            "llm": "OpenAI GPT-4",
            "vector_db": "ChromaDB",
            "graph_db": "GraphStore (Neo4j-based)",
            "character_count": len(characters),
        }
    }

@app.post("/api/v1/characters/generate", response_model=CharacterResponse)
async def generate_character(request: CharacterGenerationRequest, background_tasks: BackgroundTasks):
    start_time = time.time()
    try:
        log_info(f"开始生成角色，描述: {request.description}")
        character_data = await character_generator.generate_character(request.description)
        if "error" in character_data:
            raise ValueError(f"LLM生成角色失败: {character_data['error']}")

        character_id = str(uuid.uuid4())
        character_data["id"] = character_id
        characters[character_id] = character_data

        role_gen_time = time.time() - start_time
        log_character_creation(character_id, character_data['name'], role_gen_time)

        log_info(f"开始为角色 {character_id} 生成关系图谱")
        related_characters = await character_generator.generate_related_characters(character_data, count=5)
        relationships = await character_generator.generate_relationships(character_data, related_characters)

        # graph_store.create_character_node(character_data)
        for rc in related_characters:
            rc["id"] = rc.get("id") or str(uuid.uuid4())
            characters[rc["id"]] = rc
            # graph_store.create_character_node(rc)

        log_success(f"角色 {character_id} 的关系图谱生成并存储完成")

        background_tasks.add_task(
            generate_and_store_fine_grained_memories,
            character_id,
            character_data,
            related_characters,
            start_time
        )

        return {
            "id": character_id,
            **character_data,
            "generation_info": {
                "start_time": start_time,
                "role_gen_time": round(role_gen_time, 2),
                "status": "generating_memories_and_graph"
            }
        }
    except Exception as e:
        error_detail = f"角色生成失败: {str(e)}\n{traceback.format_exc()}"
        log_error(error_detail)
        raise HTTPException(status_code=500, detail=f"角色生成失败: {str(e)}")

@app.get("/api/v1/characters", response_model=List[CharacterResponse])
async def list_characters():
    return [{"id": cid, **cdata} for cid, cdata in characters.items()]

@app.get("/api/v1/characters/{character_id}", response_model=CharacterResponse)
async def get_character(character_id: str):
    if character_id not in characters:
        raise HTTPException(status_code=404, detail="角色不存在")
    return {"id": character_id, **characters[character_id]}

@app.get("/api/v1/characters/{character_id}/memories", response_model=List[MemoryResponse])
async def get_character_memories(character_id: str):
    if character_id not in characters:
        raise HTTPException(status_code=404, detail="角色不存在")

    raw_memories = graph_store.get_memories_for_character(character_id)

    processed_memories = []
    for mem in raw_memories:
        try:
            for key in ["time", "emotion", "importance", "behavior_impact", "trigger_system", "memory_distortion"]:
                if key in mem and isinstance(mem[key], str):
                    mem[key] = json.loads(mem[key])
            processed_memories.append(MemoryResponse(**mem))
        except Exception as e:
            log_warning(f"跳过格式异常的记忆: {str(e)} | 记忆ID: {mem.get('id', '未知')}")
            continue

    return processed_memories

@app.get("/api/v1/characters/{character_id}/relationships")
async def get_character_relationships(character_id: str):
    if character_id not in characters:
        raise HTTPException(status_code=404, detail="角色不存在")
    related_chars = graph_store.get_related_characters(character_id)
    return {"character_id": character_id, "related_characters": related_chars}

@app.post("/api/v1/characters/{character_id}/memories/regenerate")
async def regenerate_character_memories(character_id: str, background_tasks: BackgroundTasks):
    if character_id not in characters:
        raise HTTPException(status_code=404, detail="角色不存在")

    success = graph_store.delete_character_graph(character_id)
    if not success:
        raise HTTPException(status_code=500, detail="删除旧图谱数据失败")
    log_info(f"已删除角色 [{character_id}] 的所有旧关系和记忆")
    
    character_data = characters[character_id]
    background_tasks.add_task(
        generate_and_store_fine_grained_memories,
        character_id,
        character_data,
        [], # 重新生成关联角色
        time.time()
    )

    return {"message": "细粒度记忆片段重新生成任务已启动", "character_id": character_id}

@app.post("/api/v1/chat", response_class=StreamingResponse)
async def chat_with_character(request: ChatRequest):
    if request.character_id not in characters:
        raise HTTPException(status_code=404, detail="角色不存在")
    character_data = characters[request.character_id]

    async def event_generator():
        try:
            start_time = time.time()
            log_chat_start(request.character_id, request.message)

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

                log_chat_response(
                    flow_resp['type'],
                    request.character_id,
                    request.message,
                    flow_resp['content'],
                    flow_resp.get('timestamp', 0),
                    len(current_resp.memories) if current_resp.memories else 0
                )

            total_time = time.time() - start_time
            log_chat_complete(request.character_id, request.message, total_time, response_count)

        except Exception as e:
            error_detail = f"对话生成失败: {str(e)}\n{traceback.format_exc()}"
            log_error(error_detail)
            error_data = {"error": str(e)}
            error_json = json.dumps(error_data, ensure_ascii=False)
            yield f" {error_json}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.get("/api/v1/chat/{character_id}/history")
async def get_chat_history(character_id: str):
    return {"message": "对话历史功能暂未实现", "character_id": character_id, "history": []}

# --- 修改：generate_and_store_fine_grained_memories 函数 ---
# --- 修改：generate_and_store_fine_grained_memories 函数 ---
async def generate_and_store_fine_grained_memories(
    character_id: str,
    main_character: Dict[str, Any],
    related_characters: List[Dict[str, Any]],
    start_time: float
):
    memory_start = time.time()
    try:
        character_name = main_character.get("name", "未知角色")
        log_info(f"开始为角色 [{character_id}: {character_name}] 生成细粒度记忆片段")
        log_info("开始执行完整的故事生成流程...")
        story_gen_start_time = time.time()

        story_text = await story_memory_generator.generate_character_lifespan_story(main_character, related_characters, [])

        if not story_text:
            raise ValueError("生成人生故事失败")

        log_info(f"完整故事生成完成，耗时: {time.time() - story_gen_start_time:.2f} 秒")
        log_info("开始从故事中提取记忆片段...")
        memory_extraction_start_time = time.time()

        extracted_memories = await story_memory_generator.extract_memories_from_lifespan_story(story_text, main_character, related_characters)
        log_debug(f"提取记忆函数返回，共 {len(extracted_memories)} 个项目")
        log_info(f"提取完成，共 {len(extracted_memories)} 条记忆片段，耗时: {time.time() - memory_extraction_start_time:.2f} 秒")

        log_info("开始从故事中提取实体和关系...")
        entity_extraction_start_time = time.time()

        # --- 修改：调用修改后的方法，传入 graph_store, related_characters 和 extracted_memories ---
        entities, relationships_from_story = await story_memory_generator.extract_entities_and_relationships_from_story(
            story_text, 
            main_character, 
            related_characters, # 传递关联角色
            extracted_memories, # 传递提取的记忆
            graph_store
        )
        # ---
        
        log_debug(f"提取实体和关系函数返回，实体 {len(entities)} 个，关系 {len(relationships_from_story)} 条")
        log_info(f"提取完成，共 {len(entities)} 个实体和 {len(relationships_from_story)} 条关系，耗时: {time.time() - entity_extraction_start_time:.2f} 秒")

        # --- 修改：移除所有单独的节点和关系创建操作 ---
        # 之前的代码：
        # log_info("开始创建图谱节点和关系...")
        # graph_creation_start_time = time.time()
        # graph_store.create_character_node(main_character) # 移除
        # stored_memory_count = 0
        # for mem in extracted_memories: # 移除
        #     success = graph_store.create_memory_node_and_connect(mem, character_id) # 移除
        #     if success: # 移除
        #         stored_memory_count += 1 # 移除
        #     else: # 移除
        #         log_warning(...) # 移除
        # log_info(f"记忆节点创建/连接完成...") # 移除
        # created_rel_count = 0
        # for rel in relationships_from_story: # 移除
        #     success = graph_store.create_relationship_edge(rel) # 移除
        #     if success: # 移除
        #         created_rel_count += 1 # 移除
        #     else: # 移除
        #         log_warning(...) # 移除
        # log_info(f"关系数据验证并写入CSV完成...") # 移除
        # log_info(f"图谱创建完成...") # 移除
        # memory_gen_time = time.time() - memory_start # 移除
        # log_memory_generation_summary(...) # 移除

        # 现在所有数据（主角色、关联角色、实体、记忆、关系）都已通过 story_memory_generator 中的 save_entities_and_relationships_to_csv 和 import_nodes/relationships_from_csv 一次性注入
        log_info(f"所有图谱数据（节点和关系）已通过统一CSV流程一次性注入完成。")

        memory_gen_time = time.time() - memory_start
        # 由于所有数据都已通过CSV注入，我们可以认为存储的记忆片段数量等于提取的数量
        log_memory_generation_summary(character_id, character_name, len(extracted_memories), 0, memory_gen_time)

        total_time = time.time() - start_time
        log_info(f"角色生成→故事生成→记忆提取→图谱存储完整流程耗时: {total_time:.2f} 秒")

        if character_id in characters:
            characters[character_id]["generation_info"] = {
                "start_time": start_time,
                "role_gen_time": round(memory_start - start_time, 2),
                "memory_gen_time": round(memory_gen_time, 2),
                "total_time": round(total_time, 2),
                "status": "completed"
            }

    except Exception as e:
        error_detail = f"细粒度记忆片段生成失败: {str(e)}\n{traceback.format_exc()}"
        log_error(error_detail)

@app.on_event("shutdown")
async def shutdown_event():
    log_info("应用关闭，关闭 Neo4j 连接")
    graph_store.close()

if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8000))
    log_info(f"启动服务器，端口: {port}")
    uvicorn.run(
        "app.main_full:app",
        host="0.0.0.0",
        port=port,
        reload=True,
        log_level="warning"
    )