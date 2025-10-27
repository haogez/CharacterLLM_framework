# app/main_full.py
"""
角色化大语言模型知识库管理系统 - 完整版主应用 (已集成人物关系图谱 - Neo4j版)
适配完整记忆格式 + 多响应类型（direct/immediate/supplementary/no_memory）
支持实时响应流（SSE）+ 直接日志输出
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
from app.core.memory.vector_store import ChromaMemoryStore # 保留，可能作为辅助
from app.core.response.flow import ResponseFlow
# --- 新增导入 ---
from app.core.graph.relationship_generator import RelationshipGenerator
from app.core.graph.graph_store import GraphStore # 导入新版 GraphStore
# ---

# --- 1. 添加日志格式化工具函数 ---
def log_section_start(title: str, char: str = "="):
    """打印分隔线开始的标题"""
    print(f"\n{char*80}")
    print(f" {title} ".center(80, char))
    print(f"{char*80}")

def log_section_end(char: str = "="):
    """打印分隔线结束"""
    print(f"{char*80}\n")

def log_info(message: str, indent: int = 0):
    """打印信息日志"""
    print("  " * indent + f"ℹ️  {message}")

def log_success(message: str, indent: int = 0):
    """打印成功日志"""
    print("  " * indent + f"✅ {message}")

def log_warning(message: str, indent: int = 0):
    """打印警告日志"""
    print("  " * indent + f"⚠️  {message}")

def log_error(message: str, indent: int = 0):
    """打印错误日志"""
    print("  " * indent + f"❌ {message}")

def log_debug(message: str, indent: int = 0):
    """打印调试日志（可选，生产环境可关闭）"""
    print("  " * indent + f"🔍 {message}")

def log_character_creation(char_id: str, char_name: str, gen_time: float):
    """专门打印角色创建完成日志"""
    log_section_start(f"角色 [{char_name}] (ID: {char_id}) 创建完成", "=")
    log_success(f"角色生成耗时: {gen_time:.2f} 秒")
    log_section_end("=")

def log_memory_generation_summary(char_id: str, char_name: str, self_memories: int, other_memories: int, total_time: float):
    """专门打印记忆生成摘要日志"""
    log_section_start(f"角色 [{char_name}] (ID: {char_id}) 记忆生成摘要", "=")
    log_success(f"自关系记忆数: {self_memories}")
    log_success(f"其他关系记忆数: {other_memories}")
    log_info(f"记忆生成+存储耗时: {total_time:.2f} 秒")
    log_section_end("=")

def log_chat_start(character_id: str, user_input: str):
    """打印对话开始日志"""
    log_section_start("开始处理对话请求", "-")
    log_info(f"角色ID: {character_id}")
    log_info(f"用户输入: {user_input}")
    log_section_end("-")

def log_chat_response(response_type: str, character_id: str, user_input: str, content: str, timestamp: float, memory_count: int = 0):
    """打印对话响应日志"""
    log_section_start(f"{response_type.upper()} 响应发送", "-")
    log_info(f"角色ID: {character_id}")
    log_info(f"用户输入: {user_input}")
    log_info(f"响应内容: {content[:150]}{'...' if len(content) > 150 else ''}")
    log_info(f"耗时: {timestamp:.2f}秒")
    if memory_count > 0:
        log_info(f"关联记忆数: {memory_count}")
    log_section_end("-")

def log_chat_complete(character_id: str, user_input: str, total_time: float, response_count: int):
    """打印对话完成日志"""
    log_section_start("对话响应完成", "=")
    log_info(f"角色ID: {character_id}")
    log_info(f"用户输入: {user_input}")
    log_info(f"总耗时: {total_time:.2f}秒")
    log_info(f"发送响应数: {response_count}")
    log_section_end("=")

# ---

app = FastAPI(
    title="角色化大语言模型知识库管理系统",
    description="支持完整记忆格式+多响应类型的AI对话框架",
    version="2.2.4" # 版本号更新，表示已集成Neo4j
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
memory_store = ChromaMemoryStore(persist_directory="./chroma_db_full") # 保留
response_flow = ResponseFlow(character_llm, memory_store)

# --- 实例化新模块 (Neo4j版) ---
# relationship_generator = RelationshipGenerator(character_llm)
# graph_store = GraphStore(persist_directory="./graph_db") # 旧版文件存储
# --- 替换为 Neo4j 版 ---
relationship_generator = RelationshipGenerator(character_llm)
graph_store = GraphStore(uri="bolt://zhouyuhao-neo4j:7687", user="neo4j", password="zyh123456") # 新版 Neo4j 存储
# ---

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
    return {"message": "欢迎使用角色化大语言模型知识库管理系统（V2.2.3，支持人物关系图谱）"}

@app.get("/health")
async def health_check():
    return {"status": "ok", "version": "2.2.3"}

@app.get("/api/v1/system/status")
async def system_status():
    return {
        "status": "ok",
        "version": "2.2.3",
        "components": {
            "llm": "OpenAI GPT-4",
            "vector_db": "ChromaDB（支持完整记忆格式）",
            "graph_db": "GraphStore (JSON-based, supports relationship graph)",
            "character_count": len(characters),
            "response_types": ["direct", "immediate", "supplementary", "no_memory"],
            "features": ["实时响应流", "完整记忆格式", "多响应类型", "直接日志输出", "人物关系图谱"]
        }
    }

# 2. 修改：generate_character 端点改为 async
@app.post("/api/v1/characters/generate", response_model=CharacterResponse)
async def generate_character(request: CharacterGenerationRequest, background_tasks: BackgroundTasks):
    """生成角色及其关系图谱"""
    start_time = time.time()
    try:
        # 3. 修改：await 调用异步生成方法
        log_info(f"开始生成角色，描述: {request.description}")
        character_data = await character_generator.generate_character(request.description)
        if "error" in character_data:
            raise ValueError(f"LLM生成角色失败: {character_data['error']}")

        character_id = str(uuid.uuid4())
        character_data["id"] = character_id # 确保ID被设置
        characters[character_id] = character_data

        role_gen_time = time.time() - start_time
        log_character_creation(character_id, character_data['name'], role_gen_time)

        # --- 新增：生成关联角色和关系，并存入图谱 ---
        log_info(f"开始为角色 {character_id} 生成关系图谱")
        related_characters = await relationship_generator.generate_related_characters(character_data, count=3) # 生成3个关联角色
        relationships = await relationship_generator.generate_relationships(character_data, related_characters)

        # 将主角色节点存入图谱
        graph_store.create_character_node(character_data)
        # 将关联角色节点存入图谱
        for rc in related_characters:
            rc["id"] = rc.get("id") or str(uuid.uuid4()) # 为关联角色生成ID
            characters[rc["id"]] = rc # 也加入全局字典 (可选，取决于如何管理所有角色)
            graph_store.create_character_node(rc)
        # 将关系边存入图谱
        for rel in relationships:
            graph_store.create_relationship_with_memories(rel)

        log_success(f"角色 {character_id} 的关系图谱生成并存储完成")
        # ---

        background_tasks.add_task(
            generate_and_store_graph_memories,
            character_id,
            character_data,
            related_characters,
            relationships,
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

# ------------------------------------------------------------------------------
# 核心修改3：记忆查询接口（现在从图谱中获取）
# ------------------------------------------------------------------------------
@app.get("/api/v1/characters/{character_id}/memories", response_model=List[MemoryResponse])
async def get_character_memories(character_id: str):
    if character_id not in characters:
        raise HTTPException(status_code=404, detail="角色不存在")

    # --- 修改：从图谱获取记忆 ---
    raw_memories = graph_store.get_all_memories_for_character(character_id)
    # ---

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

# --- 新增：获取角色关系图谱 ---
@app.get("/api/v1/characters/{character_id}/relationships")
async def get_character_relationships(character_id: str):
    if character_id not in characters:
        raise HTTPException(status_code=404, detail="角色不存在")
    related_chars = graph_store.get_related_characters(character_id)
    return {"character_id": character_id, "related_characters": related_chars}
# ---

@app.post("/api/v1/characters/{character_id}/memories/regenerate")
async def regenerate_character_memories(character_id: str, background_tasks: BackgroundTasks):
    if character_id not in characters:
        raise HTTPException(status_code=404, detail="角色不存在")

    # --- 修改：从图谱删除记忆 ---
    success = graph_store.delete_character_graph(character_id)
    if not success:
        raise HTTPException(status_code=500, detail="删除旧图谱数据失败")
    log_info(f"已删除角色 [{character_id}] 的所有旧关系和记忆")
    # ---
    
    # 重新生成角色和关系（简化处理，实际可能需要更复杂的重置逻辑）
    character_data = characters[character_id]
    background_tasks.add_task(
        generate_and_store_graph_memories,
        character_id,
        character_data,
        [], # 重新生成关联角色
        [], # 重新生成关系
        time.time()
    )

    return {"message": "完整记忆和关系图谱重新生成任务已启动", "character_id": character_id}

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
            log_chat_start(request.character_id, request.message)

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

# ------------------------------------------------------------------------------
# 核心修改5：后台任务（生成+存储图谱记忆 - Neo4j版）
# 7. 修改：generate_and_store_graph_memories 任务改为 async
# ------------------------------------------------------------------------------
async def generate_and_store_graph_memories(
    character_id: str,
    main_character: Dict[str, Any],
    related_characters: List[Dict[str, Any]],
    relationships: List[Dict[str, Any]],
    start_time: float
):
    """
    生成并存储「图谱记忆」 (Neo4j版)
    """
    memory_start = time.time()
    try:
        character_name = main_character.get("name", "未知角色")
        log_section_start(f"开始为角色 [{character_id}: {character_name}] 生成图谱记忆", "=")
        log_info("开始并发生成不同类型的记忆...")

        # --- 修改：并发生成不同类型的记忆 ---
        # 1. 为自关系生成记忆
        self_memories = await relationship_generator.generate_memories_for_relationship(main_character, related_character=None, relationship_type="self")
        # 2. 为每个关联角色的关系生成记忆
        relationship_tasks = []
        for rel_char in related_characters:
            task = relationship_generator.generate_memories_for_relationship(main_character, rel_char, relationship_type="other") # 可以根据具体关系类型调整
            relationship_tasks.append(task)

        # 并发执行
        rel_memory_lists = await asyncio.gather(*relationship_tasks)
        all_rel_memories = [mem for sublist in rel_memory_lists for mem in sublist] # 展平列表

        # 合并记忆
        all_memories_to_store = {
            f"{character_id}_self": self_memories,
            **{f"{character_id}_{rc['id']}": [] for rc in related_characters} # 初始化其他关系的记忆列表
        }
        # 将生成的关系记忆分配给对应的关系ID
        for i, rel_char in enumerate(related_characters):
             rel_id = f"{character_id}_{rel_char['id']}"
             all_memories_to_store[rel_id] = rel_memory_lists[i]

        log_info(f"生成完成: 自关系记忆 {len(self_memories)} 条, 其他关系记忆 {len(all_rel_memories)} 条")

        # --- 修改：将记忆存入 Neo4j 图谱 ---
        # 1. 首先确保主角色节点存在
        graph_store.create_character_node(main_character)
        # 2. 确保关联角色节点存在
        for rc in related_characters:
            rc["id"] = rc.get("id") or str(uuid.uuid4()) # 为关联角色生成ID
            # characters[rc["id"]] = rc # 也加入全局字典 (可选，取决于如何管理所有角色)
            graph_store.create_character_node(rc)
        # 3. 创建关系并存入记忆
        for rel in relationships:
            # 将生成的记忆列表添加到关系数据中
            rel_id = rel["relationship_id"]
            if rel_id in all_memories_to_store:
                rel["memories"] = all_memories_to_store[rel_id]
            else:
                rel["memories"] = [] # 如果没有为该关系生成记忆，则为空列表
            graph_store.create_relationship_with_memories(rel)
        # ---


        memory_gen_time = time.time() - memory_start
        log_memory_generation_summary(character_id, character_name, len(self_memories), len(all_rel_memories), memory_gen_time)

        total_time = time.time() - start_time
        log_info(f"角色生成→关系生成→记忆存储完整流程耗时: {total_time:.2f} 秒")

        if character_id in characters:
            characters[character_id]["generation_info"] = {
                "start_time": start_time,
                "role_gen_time": round(memory_start - start_time, 2),
                "memory_gen_time": round(memory_gen_time, 2),
                "total_time": round(total_time, 2),
                "status": "completed"
            }

    except Exception as e:
        error_detail = f"图谱记忆生成失败: {str(e)}\n{traceback.format_exc()}"
        log_section_start(f"角色 [{character_id}] 图谱记忆生成失败", "=")
        log_error(error_detail)
        log_section_end("=")


# ------------------------------------------------------------------------------
# 启动和关闭服务器
# ------------------------------------------------------------------------------
@app.on_event("shutdown")
async def shutdown_event():
    log_info("--- 应用关闭，关闭 Neo4j 连接 ---")
    graph_store.close() # 关闭 Neo4j 连接

if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8000))
    log_section_start("启动角色化大语言模型知识库管理系统", "=")
    log_info(f"端口: {port}")
    log_info(f"记忆存储路径: ./chroma_db_full")
    log_info(f"图谱存储: Neo4j (bolt://localhost:7687)")
    log_info(f"支持响应类型: direct/immediate/supplementary/no_memory")
    log_info(f"支持特性: 实时响应流(SSE), 直接日志输出, 人物关系图谱")
    log_info(f"新增API: GET /api/v1/characters/{{character_id}}/relationships")
    log_section_end("=")

    uvicorn.run(
        "app.main_full:app",
        host="0.0.0.0",
        port=port,
        reload=True,
        log_level="warning" # 降低 uvicorn 日志级别，只显示 warning 及以上
    )