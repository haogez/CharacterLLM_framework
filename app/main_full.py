"""
角色化大语言模型知识库管理系统 - 完整版主应用
适配完整记忆格式 + 多响应类型（direct/immediate/supplementary/no_memory）
"""

import os
import time
import json
import uuid
import traceback  # 提前导入，避免在except块中导入
from typing import Dict, List, Any, Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel  # 用于定义数据模型

from app.core.character.generator import CharacterGenerator
from app.core.llm.openai_client import CharacterLLM
from app.core.memory.vector_store import ChromaMemoryStore
from app.core.response.flow import ResponseFlow  # 对接优化后的flow

# 创建FastAPI应用
app = FastAPI(
    title="角色化大语言模型知识库管理系统",
    description="支持完整记忆格式+多响应类型的AI对话框架",
    version="2.0.0"  # 版本升级，标记适配完整记忆格式
)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境需限制为特定域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 创建全局组件（确保MemoryStore支持完整记忆格式读取）
character_llm = CharacterLLM()
character_generator = CharacterGenerator(character_llm)
# 初始化ChromaMemoryStore，后续需在其内部实现return_full_fields参数
memory_store = ChromaMemoryStore(persist_directory="./chroma_db_full")
response_flow = ResponseFlow(character_llm, memory_store)  # 对接优化后的ResponseFlow

# ------------------------------------------------------------------------------
# 核心修改1：定义适配「完整记忆格式」的数据模型（嵌套Pydantic模型）
# ------------------------------------------------------------------------------
class TimeDetail(BaseModel):
    """记忆中time字段的详细结构（对应完整记忆格式）"""
    age: int  # 角色当时年龄（整数）
    period: str  # 人生阶段（如“工作第3年”）
    specific: str  # 具体时间特征（如“周五加班到凌晨”）

class EmotionDetail(BaseModel):
    """记忆中emotion字段的详细结构"""
    immediate: List[str]  # 即时情绪（2-3个）
    reflected: List[str]  # 事后反思情绪（2-3个）
    residual: str  # 残留至今的情感
    intensity: int  # 情感强度（1-10）

class ImportanceDetail(BaseModel):
    """记忆中importance字段的详细结构"""
    score: int  # 重要性评分（1-10）
    reason: str  # 重要性原因
    frequency: str  # 回忆频率（如“每月至少想起1次”）

class BehaviorImpactDetail(BaseModel):
    """记忆中behavior_impact字段的详细结构"""
    habit_formed: str  # 形成的习惯
    attitude_change: str  # 态度转变
    response_pattern: str  # 应对模式

class TriggerSystemDetail(BaseModel):
    """记忆中trigger_system字段的详细结构"""
    sensory: List[str]  # 感官触发点（如“闻到速溶咖啡焦味”）
    contextual: List[str]  # 情境触发点（如“项目上线前测试”）
    emotional: List[str]  # 情绪触发点（如“感到焦虑时”）

class MemoryDistortionDetail(BaseModel):
    """记忆中memory_distortion字段的详细结构"""
    exaggerated: str  # 被夸大的部分
    downplayed: str  # 被淡化的部分
    reason: str  # 扭曲原因（符合角色性格）

class MemoryResponse(BaseModel):
    """完整记忆格式的响应模型（覆盖所有字段）"""
    id: str  # 记忆ID
    type: str  # 记忆类型（education/work/family等）
    title: str  # 记忆标题（10-15字）
    content: str  # 记忆详细内容（350-500字）
    time: TimeDetail  # 嵌套时间详情
    emotion: EmotionDetail  # 嵌套情绪详情
    importance: ImportanceDetail  # 嵌套重要性详情
    behavior_impact: BehaviorImpactDetail  # 嵌套行为影响详情
    trigger_system: TriggerSystemDetail  # 嵌套触发机制详情
    memory_distortion: MemoryDistortionDetail  # 嵌套记忆偏差详情
    relevance: Optional[float] = None  # 检索时的相关性分数（可选）

# ------------------------------------------------------------------------------
# 核心修改2：定义适配「多响应类型」的对话模型
# ------------------------------------------------------------------------------
class CharacterGenerationRequest(BaseModel):
    """角色生成请求（无修改，保持原结构）"""
    description: str

class CharacterResponse(BaseModel):
    """角色详情响应（保持完整人设字段）"""
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
    """对话请求（无修改，保持原结构）"""
    character_id: str
    message: str
    conversation_history: Optional[List[Dict[str, str]]] = None  # 历史对话（角色/用户）

class ChatResponse(BaseModel):
    """对话响应（支持4种响应类型）"""
    message: str  # 响应内容
    type: str  # 响应类型：direct/immediate/supplementary/no_memory
    memories: Optional[List[MemoryResponse]] = None  # 关联的完整记忆（可选）

# 内存存储角色数据（生产环境需替换为数据库）
characters: Dict[str, Dict[str, Any]] = {}

# ------------------------------------------------------------------------------
# API路由（核心修改：对话接口、记忆查询接口）
# ------------------------------------------------------------------------------
@app.get("/")
async def root():
    return {"message": "欢迎使用角色化大语言模型知识库管理系统（V2.0，适配完整记忆格式）"}

@app.get("/health")
async def health_check():
    return {"status": "ok", "version": "2.0.0"}

@app.get("/api/v1/system/status")
async def system_status():
    return {
        "status": "ok",
        "version": "2.0.0",
        "components": {
            "llm": "OpenAI GPT-4",
            "vector_db": "ChromaDB（支持完整记忆格式）",
            "character_count": len(characters),
            "response_types": ["direct", "immediate", "supplementary", "no_memory"]
        }
    }

@app.post("/api/v1/characters/generate", response_model=CharacterResponse)
async def generate_character(request: CharacterGenerationRequest, background_tasks: BackgroundTasks):
    """生成角色（无核心修改，仅补充完整记忆生成注释）"""
    start_time = time.time()
    try:
        # 生成完整人设（需确保character_generator返回所有字段）
        character_data = character_generator.generate_character(request.description)
        if "error" in character_data:
            raise ValueError(f"LLM生成角色失败: {character_data['error']}")
        
        # 生成角色ID并存储
        character_id = str(uuid.uuid4())
        characters[character_id] = character_data
        
        # 打印耗时
        role_gen_time = time.time() - start_time
        print(f"=== 角色 [{character_id}: {character_data['name']}] 生成耗时: {role_gen_time:.2f} 秒 ===")
        
        # 后台生成「完整格式记忆」
        background_tasks.add_task(
            generate_and_store_memories,
            character_id,
            character_data,
            start_time  # 传递角色生成开始时间，计算总耗时
        )
        
        return {"id": character_id, **character_data}
    except Exception as e:
        error_detail = f"角色生成失败: {str(e)}\n{traceback.format_exc()}"
        print(error_detail)
        raise HTTPException(status_code=500, detail=f"角色生成失败: {str(e)}")

@app.get("/api/v1/characters", response_model=List[CharacterResponse])
async def list_characters():
    """列出所有角色（无修改）"""
    return [{"id": cid, **cdata} for cid, cdata in characters.items()]

@app.get("/api/v1/characters/{character_id}", response_model=CharacterResponse)
async def get_character(character_id: str):
    """获取单个角色详情（无修改）"""
    if character_id not in characters:
        raise HTTPException(status_code=404, detail="角色不存在")
    return {"id": character_id, **characters[character_id]}

# ------------------------------------------------------------------------------
# 核心修改3：记忆查询接口（适配完整记忆格式，反序列化JSON字段）
# ------------------------------------------------------------------------------
@app.get("/api/v1/characters/{character_id}/memories", response_model=List[MemoryResponse])
async def get_character_memories(character_id: str):
    """查询角色的所有完整记忆（反序列化存储时的JSON字段）"""
    if character_id not in characters:
        raise HTTPException(status_code=404, detail="角色不存在")
    
    # 调用MemoryStore查询完整记忆（需确保返回所有嵌套字段的JSON字符串）
    raw_memories = memory_store.query_memories(
        character_id=character_id,
        query_text="",  # 空查询返回所有记忆
        n_results=100,
        return_full_fields=True  # 关键参数：获取完整记忆格式（非简化版）
    )
    
    # 反序列化存储时的JSON字段（time/emotion等嵌套字段）
    processed_memories = []
    for mem in raw_memories:
        try:
            # 对所有嵌套字典字段进行JSON反序列化（存储时转了字符串）
            for key in ["time", "emotion", "importance", "behavior_impact", "trigger_system", "memory_distortion"]:
                if key in mem and isinstance(mem[key], str):
                    mem[key] = json.loads(mem[key])  # 转回字典
            # 转换为MemoryResponse模型（自动校验字段完整性）
            processed_memories.append(MemoryResponse(**mem))
        except Exception as e:
            print(f"跳过格式异常的记忆: {str(e)} | 记忆ID: {mem.get('id', '未知')}")
            continue
    
    return processed_memories

@app.post("/api/v1/characters/{character_id}/memories/regenerate")
async def regenerate_character_memories(character_id: str, background_tasks: BackgroundTasks):
    """重新生成角色记忆（适配完整记忆格式）"""
    if character_id not in characters:
        raise HTTPException(status_code=404, detail="角色不存在")
    
    # 删除现有完整记忆
    memory_store.delete_all_memories(character_id)
    print(f"=== 已删除角色 [{character_id}] 的所有旧记忆 ===")
    
    # 后台重新生成完整记忆（不传递role_start_time，使用默认值None）
    background_tasks.add_task(
        generate_and_store_memories,
        character_id,
        characters[character_id]
    )
    
    return {"message": "完整记忆重新生成任务已启动", "character_id": character_id}

# ------------------------------------------------------------------------------
# 核心修改4：对话接口（返回所有响应，适配4种类型，反序列化记忆）
# ------------------------------------------------------------------------------
@app.post("/api/v1/chat", response_model=List[ChatResponse])
async def chat_with_character(request: ChatRequest):
    """对话接口：返回所有响应（1条：direct；2条：immediate+supplementary/no_memory）"""
    # 1. 校验角色存在性
    if request.character_id not in characters:
        raise HTTPException(status_code=404, detail="角色不存在")
    character_data = characters[request.character_id]
    
    try:
        # 2. 调用flow处理对话（获取所有响应）
        chat_responses: List[ChatResponse] = []
        async for flow_resp in response_flow.process(
            character_id=request.character_id,
            character_data=character_data,
            user_input=request.message,
            conversation_history=request.conversation_history
        ):
            # 3. 转换flow响应为ChatResponse（处理记忆反序列化）
            current_resp = ChatResponse(
                message=flow_resp["content"],
                type=flow_resp["type"],
                memories=None
            )
            
            # 4. 若有记忆，反序列化并转换为MemoryResponse列表
            if "memories" in flow_resp and flow_resp["memories"]:
                processed_mem = []
                for mem in flow_resp["memories"]:
                    # 反序列化嵌套字段（存储时转了JSON字符串）
                    for key in ["time", "emotion", "importance", "behavior_impact", "trigger_system", "memory_distortion"]:
                        if key in mem and isinstance(mem[key], str):
                            mem[key] = json.loads(mem[key])
                    processed_mem.append(MemoryResponse(**mem))
                current_resp.memories = processed_mem
            
            chat_responses.append(current_resp)
        
        # 5. 返回所有响应（前端根据type区分处理：1条或2条）
        return chat_responses
    
    except Exception as e:
        error_detail = f"对话生成失败: {str(e)}\n{traceback.format_exc()}"
        print(error_detail)
        raise HTTPException(status_code=500, detail=f"对话生成失败: {str(e)}")

@app.get("/api/v1/chat/{character_id}/history")
async def get_chat_history(character_id: str):
    """对话历史接口（暂未实现，返回空列表）"""
    return {"message": "对话历史功能暂未实现", "character_id": character_id, "history": []}

# ------------------------------------------------------------------------------
# 核心修改5：后台任务（生成+存储完整格式记忆，处理嵌套JSON序列化）
# ------------------------------------------------------------------------------
async def generate_and_store_memories(
    character_id: str, 
    character_data: Dict[str, Any], 
    role_start_time: float = None  # 允许为None（重新生成时无此参数）
):
    """
    生成并存储「完整格式记忆」：
    1. 调用generator生成含所有嵌套字段的记忆
    2. 将嵌套字典字段转JSON字符串（适配ChromaDB存储）
    3. 存储到ChromaDB并打印日志
    """
    memory_start = time.time()
    try:
        character_name = character_data.get("name", "未知角色")
        print(f"=== 开始生成角色 [{character_id}: {character_name}] 的完整记忆 ===")
        
        # 1. 生成完整格式记忆（需确保generator返回所有嵌套字段）
        # 此处count=5控制记忆数量，可根据需求调整
        raw_memories = character_generator.generate_memories(character_data, count=5)
        if not raw_memories:
            print(f"警告：角色 [{character_name}] 未生成任何记忆")
            return
        
        # 2. 处理完整记忆：嵌套字典转JSON字符串（适配ChromaDB元数据）
        processed_memories = []
        for mem in raw_memories:
            processed_mem = {}
            for key, value in mem.items():
                # 对所有嵌套字典字段（time/emotion等）进行JSON序列化
                if isinstance(value, dict):
                    processed_mem[key] = json.dumps(value, ensure_ascii=False)  # 保留中文
                else:
                    processed_mem[key] = value
                # 确保记忆有唯一ID（若generator未生成）
                if "id" not in processed_mem:
                    processed_mem["id"] = str(uuid.uuid4())
            processed_memories.append(processed_mem)
        
        # 3. 存储完整记忆到ChromaDB
        memory_ids = memory_store.add_memories(character_id, processed_memories)
        print(f"=== 角色 [{character_name}] 成功存储 {len(memory_ids)} 条完整记忆 ===")
        print(f"  记忆ID列表: {memory_ids}")
        
        # 4. 计算耗时（区分“记忆生成耗时”和“完整流程耗时”）
        memory_gen_time = time.time() - memory_start
        print(f"  记忆生成+存储耗时: {memory_gen_time:.2f} 秒")
        
        if role_start_time:
            total_time = time.time() - role_start_time
            print(f"  角色生成→记忆存储完整流程耗时: {total_time:.2f} 秒")
    
    except Exception as e:
        error_detail = f"记忆生成失败: {str(e)}\n{traceback.format_exc()}"
        print(f"\n=== 角色 [{character_id}] 记忆生成失败 ===\n{error_detail}\n")

# ------------------------------------------------------------------------------
# 启动服务器
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    
    # 从环境变量获取端口，默认8000
    port = int(os.environ.get("PORT", 8000))
    print(f"=== 启动角色化大语言模型知识库管理系统（V2.0） ===")
    print(f"  端口: {port}")
    print(f"  记忆存储路径: ./chroma_db_full")
    print(f"  支持响应类型: direct/immediate/supplementary/no_memory")
    
    # 启动UVicorn服务器（reload=True仅用于开发环境）
    uvicorn.run(
        "app.main_full:app",
        host="0.0.0.0",
        port=port,
        reload=True,
        log_level="info"
    )