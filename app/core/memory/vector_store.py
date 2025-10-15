"""
ChromaDB向量存储模块

提供与ChromaDB交互的封装类，支持记忆的存储、检索和管理。
"""

import os
import uuid
import json  # 新增：导入JSON序列化模块
from typing import Dict, List, Any, Optional, Tuple

import chromadb
from chromadb.config import Settings
from chromadb.utils import embedding_functions

class ChromaMemoryStore:
    """
    ChromaDB向量存储封装类
    
    提供对ChromaDB的封装，支持记忆的存储、检索和管理
    """
    
    def __init__(self, persist_directory: str = "./chroma_db", openai_api_key: Optional[str] = None):
        """
        初始化ChromaDB客户端
        
        Args:
            persist_directory: 持久化存储目录
            openai_api_key: OpenAI API密钥，如果为None则从环境变量获取
        """
        # 确保存储目录存在
        os.makedirs(persist_directory, exist_ok=True)
        
        # 初始化ChromaDB客户端
        self.client = chromadb.Client(Settings(
            persist_directory=persist_directory,
            anonymized_telemetry=False
        ))
        
        # 设置OpenAI嵌入函数
        self.api_key = openai_api_key or os.environ.get("OPENAI_API_KEY")
        self.embedding_function = embedding_functions.OpenAIEmbeddingFunction(
            api_key=self.api_key,
            model_name="text-embedding-3-large"
        )
    
    def get_character_collection_name(self, character_id: str) -> str:
        """
        获取角色记忆集合名称
        
        Args:
            character_id: 角色ID
            
        Returns:
            集合名称
        """
        return f"character_memories_{character_id}"
    
    def create_collection(self, name: str) -> Any:
        """
        创建记忆集合
        
        Args:
            name: 集合名称
            
        Returns:
            创建的集合对象
        """
        try:
            # 尝试获取已存在的集合
            return self.client.get_collection(name=name, embedding_function=self.embedding_function)
        except Exception:
            # 如果不存在则创建新集合
            return self.client.create_collection(name=name, embedding_function=self.embedding_function)
    
    def get_collection(self, name: str) -> Any:
        """
        获取记忆集合
        
        Args:
            name: 集合名称
            
        Returns:
            集合对象
        """
        try:
            return self.client.get_collection(name=name, embedding_function=self.embedding_function)
        except Exception as e:
            raise ValueError(f"Collection {name} not found: {str(e)}")
    
    def add_memory(self, 
                character_id: str, 
                memory_data: Dict[str, Any]) -> str:
        """
        添加单个记忆（完整支持所有记忆字段存储）
        
        Args:
            character_id: 角色ID
            memory_data: 记忆数据（需包含完整字段）
                
        Returns:
            记忆ID
        """
        collection_name = self.get_character_collection_name(character_id)
        collection = self.create_collection(collection_name)
        
        # 生成记忆ID
        memory_id = str(uuid.uuid4())
        
        # 准备记忆文本
        memory_text = f"{memory_data.get('title', '')}: {memory_data.get('content', '')}"
        
        # 准备元数据（处理所有嵌套字段的JSON序列化）
        metadata = {
            "character_id": character_id,
            "type": memory_data.get("type", "general"),
            "title": memory_data.get("title", "")
        }
        
        # 处理time字段（嵌套字典转JSON）
        time_data = memory_data.get("time", {})
        metadata["time"] = json.dumps(time_data, ensure_ascii=False) if isinstance(time_data, dict) else time_data
        
        # 处理emotion字段
        emotion_data = memory_data.get("emotion", {})
        metadata["emotion"] = json.dumps(emotion_data, ensure_ascii=False) if isinstance(emotion_data, dict) else emotion_data
        
        # 处理importance字段
        importance_data = memory_data.get("importance", {})
        metadata["importance"] = json.dumps(importance_data, ensure_ascii=False) if isinstance(importance_data, dict) else importance_data
        
        # 处理behavior_impact字段
        behavior_data = memory_data.get("behavior_impact", {})
        metadata["behavior_impact"] = json.dumps(behavior_data, ensure_ascii=False) if isinstance(behavior_data, dict) else behavior_data
        
        # 处理trigger_system字段
        trigger_data = memory_data.get("trigger_system", {})
        metadata["trigger_system"] = json.dumps(trigger_data, ensure_ascii=False) if isinstance(trigger_data, dict) else trigger_data
        
        # 处理memory_distortion字段
        distortion_data = memory_data.get("memory_distortion", {})
        metadata["memory_distortion"] = json.dumps(distortion_data, ensure_ascii=False) if isinstance(distortion_data, dict) else distortion_data
        
        # 添加到集合
        collection.add(
            documents=[memory_text],
            metadatas=[metadata],
            ids=[memory_id]
        )
        
        return memory_id
    
    def add_memories(self, 
                    character_id: str, 
                    memories_data: List[Dict[str, Any]]) -> List[str]:
        """
        批量添加记忆（支持完整字段存储）
        
        Args:
            character_id: 角色ID
            memories_data: 记忆数据列表
                
        Returns:
            记忆ID列表
        """
        collection_name = self.get_character_collection_name(character_id)
        collection = self.create_collection(collection_name)
        
        memory_ids = []
        documents = []
        metadatas = []
        ids = []
        
        for memory_data in memories_data:
            # 生成记忆ID
            memory_id = str(uuid.uuid4())
            memory_ids.append(memory_id)
            
            # 准备记忆文本
            memory_text = f"{memory_data.get('title', '')}: {memory_data.get('content', '')}"
            
            # 准备元数据（处理所有嵌套字段的JSON序列化）
            metadata = {
                "character_id": character_id,
                "type": memory_data.get("type", "general"),
                "title": memory_data.get("title", "")
            }
            
            # 处理time字段（嵌套字典转JSON）
            time_data = memory_data.get("time", {})
            metadata["time"] = json.dumps(time_data, ensure_ascii=False) if isinstance(time_data, dict) else time_data
            
            # 处理emotion字段
            emotion_data = memory_data.get("emotion", {})
            metadata["emotion"] = json.dumps(emotion_data, ensure_ascii=False) if isinstance(emotion_data, dict) else emotion_data
            
            # 处理importance字段
            importance_data = memory_data.get("importance", {})
            metadata["importance"] = json.dumps(importance_data, ensure_ascii=False) if isinstance(importance_data, dict) else importance_data
            
            # 处理behavior_impact字段
            behavior_data = memory_data.get("behavior_impact", {})
            metadata["behavior_impact"] = json.dumps(behavior_data, ensure_ascii=False) if isinstance(behavior_data, dict) else behavior_data
            
            # 处理trigger_system字段
            trigger_data = memory_data.get("trigger_system", {})
            metadata["trigger_system"] = json.dumps(trigger_data, ensure_ascii=False) if isinstance(trigger_data, dict) else trigger_data
            
            # 处理memory_distortion字段
            distortion_data = memory_data.get("memory_distortion", {})
            metadata["memory_distortion"] = json.dumps(distortion_data, ensure_ascii=False) if isinstance(distortion_data, dict) else distortion_data
            
            documents.append(memory_text)
            metadatas.append(metadata)
            ids.append(memory_id)
        
        # 批量添加到集合
        if documents:  # 确保有数据才添加
            collection.add(
                documents=documents,
                metadatas=metadatas,
                ids=ids
            )
        
        return memory_ids
    
    def query_memories(self, 
                character_id: str, 
                query_text: str, 
                n_results: int = 5,
                memory_type: Optional[str] = None,
                min_importance: Optional[int] = None,
                return_full_fields: bool = False) -> List[Dict[str, Any]]:
        """
        查询记忆（完整支持所有字段反序列化和字段映射）
        
        Args:
            character_id: 角色ID
            query_text: 查询文本
            n_results: 返回结果数量
            memory_type: 记忆类型过滤
            min_importance: 最小重要性过滤
            return_full_fields: 是否返回完整记忆字段
                    
        Returns:
            记忆列表（包含所有必填字段）
        """
        collection_name = self.get_character_collection_name(character_id)
        
        try:
            collection = self.get_collection(collection_name)
        except ValueError:
            return []  # 集合不存在，返回空列表
        
        # 准备查询过滤条件
        where_clause = {"character_id": character_id}
        if memory_type:
            where_clause["type"] = memory_type  # 使用type字段过滤
        if min_importance is not None:
            where_clause["importance"] = {"$gte": min_importance}
        
        # 执行查询
        results = collection.query(
            query_texts=[query_text],
            n_results=n_results,
            where=where_clause if len(where_clause) > 1 else None
        )
        
        # 处理结果（完整反序列化所有字段）
        memories = []
        for i, (doc, metadata, distance) in enumerate(zip(
            results.get("documents", [[]])[0],
            results.get("metadatas", [[]])[0],
            results.get("distances", [[]])[0]
        )):
            # 核心修复1：字段名映射（兼容旧数据）
            if "type" not in metadata and "memory_type" in metadata:
                metadata["type"] = metadata["memory_type"]
            
            # 核心修复2：完整反序列化所有嵌套字段
            nested_fields = [
                "time", "emotion", "importance", 
                "behavior_impact", "trigger_system", "memory_distortion"
            ]
            for key in nested_fields:
                if key in metadata and isinstance(metadata[key], str):
                    try:
                        metadata[key] = json.loads(metadata[key])
                    except json.JSONDecodeError:
                        # 容错处理：解析失败时保留原始字符串并添加错误标记
                        metadata[key] = {
                            "raw_value": metadata[key],
                            "parse_error": True
                        }
            
            # 计算相关性分数
            relevance = 1.0 - (distance / 2.0)
            
            # 构建返回结构
            if return_full_fields:
                memory = {
                    "id": results.get("ids", [[]])[0][i],
                    "content": doc,
                    "relevance": round(relevance, 3),** metadata
                }
            else:
                memory = {
                    "id": results.get("ids", [[]])[0][i],
                    "type": metadata.get("type"),
                    "title": metadata.get("title"),
                    "content": doc,
                    "relevance": round(relevance, 3)
                }
            
            memories.append(memory)
        
        return memories
    
    def get_memory_by_id(self, character_id: str, memory_id: str) -> Optional[Dict[str, Any]]:
        """
        通过ID获取记忆
        
        Args:
            character_id: 角色ID
            memory_id: 记忆ID
            
        Returns:
            记忆数据，如果不存在则返回None
        """
        collection_name = self.get_character_collection_name(character_id)
        
        try:
            collection = self.get_collection(collection_name)
            result = collection.get(ids=[memory_id])
            
            if not result["ids"]:
                return None
            
            metadata = result["metadatas"][0]
            
            # 解析time字段（若为JSON字符串，转回字典）
            try:
                if isinstance(metadata.get("time"), str):
                    metadata["time"] = json.loads(metadata["time"])
            except json.JSONDecodeError:
                pass  # 解析失败则保留原始字符串
            
            # 解析emotion字段（若为JSON字符串，转回字典）
            try:
                if isinstance(metadata.get("emotion"), str):
                    metadata["emotion"] = json.loads(metadata["emotion"])
            except json.JSONDecodeError:
                pass  # 解析失败则保留原始字符串
            
            return {
                "id": result["ids"][0],
                "content": result["documents"][0],** metadata
            }
        except Exception:
            return None
    
    def update_memory(self, 
                     character_id: str, 
                     memory_id: str, 
                     memory_data: Dict[str, Any]) -> bool:
        """
        更新记忆
        
        Args:
            character_id: 角色ID
            memory_id: 记忆ID
            memory_data: 新的记忆数据
            
        Returns:
            是否更新成功
        """
        collection_name = self.get_character_collection_name(character_id)
        
        try:
            collection = self.get_collection(collection_name)
            
            # 准备记忆文本
            memory_text = f"{memory_data.get('title', '')}: {memory_data.get('content', '')}"
            
            # 准备元数据（处理字典类型字段）
            metadata = {}
            metadata["character_id"] = character_id
            metadata["memory_type"] = memory_data.get("type", "general")
            
            # 处理time字段（若为字典，转JSON字符串）
            time_data = memory_data.get("time", "")
            metadata["time"] = json.dumps(time_data, ensure_ascii=False) if isinstance(time_data, dict) else time_data
            
            # 处理emotion字段（若为字典，转JSON字符串）
            emotion_data = memory_data.get("emotion", "neutral")
            metadata["emotion"] = json.dumps(emotion_data, ensure_ascii=False) if isinstance(emotion_data, dict) else emotion_data
            
            metadata["importance"] = memory_data.get("importance", 5)
            metadata["title"] = memory_data.get("title", "")
            
            # 更新记忆
            collection.update(
                ids=[memory_id],
                documents=[memory_text],
                metadatas=[metadata]
            )
            
            return True
        except Exception:
            return False
    
    def delete_memory(self, character_id: str, memory_id: str) -> bool:
        """
        删除记忆
        
        Args:
            character_id: 角色ID
            memory_id: 记忆ID
            
        Returns:
            是否删除成功
        """
        collection_name = self.get_character_collection_name(character_id)
        
        try:
            collection = self.get_collection(collection_name)
            collection.delete(ids=[memory_id])
            return True
        except Exception:
            return False
    
    def delete_all_memories(self, character_id: str) -> bool:
        """
        删除角色的所有记忆
        
        Args:
            character_id: 角色ID
            
        Returns:
            是否删除成功
        """
        collection_name = self.get_character_collection_name(character_id)
        
        try:
            # 尝试获取集合
            self.get_collection(collection_name)
            # 删除集合
            self.client.delete_collection(collection_name)
            return True
        except Exception:
            return False


# 测试代码
if __name__ == "__main__":
    # 设置API密钥
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("请设置OPENAI_API_KEY环境变量")
        exit(1)
    
    # 创建向量存储
    memory_store = ChromaMemoryStore(
        persist_directory="./test_chroma_db",
        openai_api_key=api_key
    )
    
    # 测试角色ID
    character_id = "test_character_001"
    
    # 测试添加包含字典的记忆
    memory_id = memory_store.add_memory(
        character_id=character_id,
        memory_data={
            "type": "education",
            "title": "大学毕业",
            "content": "1965年从北京师范大学中文系毕业，成为一名光荣的人民教师。",
            "time": {  # 测试字典类型
                "age": 22,
                "period": "青年时期",
                "specific": "夏季毕业典礼"
            },
            "emotion": {  # 测试字典类型
                "immediate": ["激动", "期待"],
                "intensity": 8
            },
            "importance": 9
        }
    )
    print(f"添加记忆成功，ID: {memory_id}")
    
    # 测试批量添加包含字典的记忆
    memory_ids = memory_store.add_memories(
        character_id=character_id,
        memories=[
            {
                "type": "work",
                "title": "教学成就",
                "content": "1980年被评为市级优秀教师，获得表彰。",
                "time": {
                    "age": 37,
                    "period": "中年时期",
                    "specific": "教师节表彰大会"
                },
                "emotion": {
                    "immediate": ["自豪", "欣慰"],
                    "intensity": 7
                },
                "importance": 8
            },
            {
                "type": "family",
                "title": "女儿出生",
                "content": "1970年女儿出生，取名丽华，全家欢喜。",
                "time": {
                    "age": 27,
                    "period": "成家初期",
                    "specific": "冬季凌晨"
                },
                "emotion": {
                    "immediate": ["幸福", "责任"],
                    "intensity": 10
                },
                "importance": 10
            }
        ]
    )
    print(f"批量添加记忆成功，ID列表: {memory_ids}")
    
    # 测试查询记忆（验证字典字段是否能正确解析）
    query_results = memory_store.query_memories(
        character_id=character_id,
        query_text="重要人生事件",
        n_results=5
    )
    print("\n查询结果:")
    for memory in query_results:
        print(f"- [{memory['memory_type']}] {memory['title']} (相关性: {memory['relevance']:.2f})")
        print(f"  时间信息: {memory['time']} (类型: {type(memory['time']).__name__})")
        print(f"  情感信息: {memory['emotion']} (类型: {type(memory['emotion']).__name__})")
    
    # 清理测试数据
    print("\n清理测试数据...")
    memory_store.delete_all_memories(character_id)
    print("测试完成")
    