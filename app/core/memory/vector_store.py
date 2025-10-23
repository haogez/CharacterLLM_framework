"""
ChromaDB向量存储模块

提供与ChromaDB交互的封装类，支持记忆的存储、检索和管理。
"""

import os
import uuid
import json
import asyncio # 1. 添加 asyncio 导入
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
        os.makedirs(persist_directory, exist_ok=True)
        
        self.client = chromadb.Client(Settings(
            persist_directory=persist_directory,
            anonymized_telemetry=False
        ))
        
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
            return self.client.get_collection(name=name, embedding_function=self.embedding_function)
        except Exception:
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
    
    # 2. 新增：内部同步方法 _sync_add_memory
    def _sync_add_memory(self, 
                character_id: str, 
                memory_data: Dict[str, Any]) -> str:
        """
        同步添加单个记忆（完整支持所有记忆字段存储）
        """
        collection_name = self.get_character_collection_name(character_id)
        collection = self.create_collection(collection_name)
        
        memory_id = str(uuid.uuid4())
        memory_text = f"{memory_data.get('title', '')}: {memory_data.get('content', '')}"
        
        metadata = {
            "character_id": character_id,
            "type": memory_data.get("type", "general"),
            "title": memory_data.get("title", "")
        }
        
        time_data = memory_data.get("time", {})
        metadata["time"] = json.dumps(time_data, ensure_ascii=False) if isinstance(time_data, dict) else time_data
        
        emotion_data = memory_data.get("emotion", {})
        metadata["emotion"] = json.dumps(emotion_data, ensure_ascii=False) if isinstance(emotion_data, dict) else emotion_data
        
        importance_data = memory_data.get("importance", {})
        metadata["importance"] = json.dumps(importance_data, ensure_ascii=False) if isinstance(importance_data, dict) else importance_data
        
        behavior_data = memory_data.get("behavior_impact", {})
        metadata["behavior_impact"] = json.dumps(behavior_data, ensure_ascii=False) if isinstance(behavior_data, dict) else behavior_data
        
        trigger_data = memory_data.get("trigger_system", {})
        metadata["trigger_system"] = json.dumps(trigger_data, ensure_ascii=False) if isinstance(trigger_data, dict) else trigger_data
        
        distortion_data = memory_data.get("memory_distortion", {})
        metadata["memory_distortion"] = json.dumps(distortion_data, ensure_ascii=False) if isinstance(distortion_data, dict) else distortion_data
        
        collection.add(
            documents=[memory_text],
            metadatas=[metadata],
            ids=[memory_id]
        )
        
        return memory_id
    
    # 3. 新增：异步方法 add_memory_async
    async def add_memory_async(self, 
                character_id: str, 
                memory_data: Dict[str, Any]) -> str:
        """
        异步添加单个记忆（完整支持所有记忆字段存储）
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._sync_add_memory, character_id, memory_data)

    # 4. 新增：内部同步方法 _sync_add_memories
    def _sync_add_memories(self, 
                    character_id: str, 
                    memories_data: List[Dict[str, Any]]) -> List[str]:
        """
        同步批量添加记忆（支持完整字段存储）
        """
        collection_name = self.get_character_collection_name(character_id)
        collection = self.create_collection(collection_name)
        
        memory_ids = []
        documents = []
        metadatas = []
        ids = []
        
        for memory_data in memories_data:
            memory_id = str(uuid.uuid4())
            memory_ids.append(memory_id)
            
            memory_text = f"{memory_data.get('title', '')}: {memory_data.get('content', '')}"
            
            metadata = {
                "character_id": character_id,
                "type": memory_data.get("type", "general"),
                "title": memory_data.get("title", "")
            }
            
            time_data = memory_data.get("time", {})
            metadata["time"] = json.dumps(time_data, ensure_ascii=False) if isinstance(time_data, dict) else time_data
            
            emotion_data = memory_data.get("emotion", {})
            metadata["emotion"] = json.dumps(emotion_data, ensure_ascii=False) if isinstance(emotion_data, dict) else emotion_data
            
            importance_data = memory_data.get("importance", {})
            metadata["importance"] = json.dumps(importance_data, ensure_ascii=False) if isinstance(importance_data, dict) else importance_data
            
            behavior_data = memory_data.get("behavior_impact", {})
            metadata["behavior_impact"] = json.dumps(behavior_data, ensure_ascii=False) if isinstance(behavior_data, dict) else behavior_data
            
            trigger_data = memory_data.get("trigger_system", {})
            metadata["trigger_system"] = json.dumps(trigger_data, ensure_ascii=False) if isinstance(trigger_data, dict) else trigger_data
            
            distortion_data = memory_data.get("memory_distortion", {})
            metadata["memory_distortion"] = json.dumps(distortion_data, ensure_ascii=False) if isinstance(distortion_data, dict) else distortion_data
            
            documents.append(memory_text)
            metadatas.append(metadata)
            ids.append(memory_id)
        
        if documents:
            collection.add(
                documents=documents,
                metadatas=metadatas,
                ids=ids
            )
        
        return memory_ids
    
    # 5. 新增：异步方法 add_memories_async
    async def add_memories_async(self, 
                    character_id: str, 
                    memories_data: List[Dict[str, Any]]) -> List[str]:
        """
        异步批量添加记忆（支持完整字段存储）
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._sync_add_memories, character_id, memories_data)

    # 6. 新增：内部同步方法 _sync_query_memories
    def _sync_query_memories(self, 
                character_id: str, 
                query_text: str, 
                n_results: int = 5,
                memory_type: Optional[str] = None,
                min_importance: Optional[int] = None,
                return_full_fields: bool = False) -> List[Dict[str, Any]]:
        """
        同步查询记忆（完整支持所有字段反序列化和字段映射）
        """
        collection_name = self.get_character_collection_name(character_id)
        
        try:
            collection = self.get_collection(collection_name)
        except ValueError:
            return []
        
        where_clause = {"character_id": character_id}
        if memory_type:
            where_clause["type"] = memory_type
        if min_importance is not None:
            where_clause["importance"] = {"$gte": min_importance}
        
        results = collection.query(
            query_texts=[query_text],
            n_results=n_results,
            where=where_clause if len(where_clause) > 1 else None
        )
        
        memories = []
        for i, (doc, metadata, distance) in enumerate(zip(
            results.get("documents", [[]])[0],
            results.get("metadatas", [[]])[0],
            results.get("distances", [[]])[0]
        )):
            if "type" not in metadata and "memory_type" in metadata:
                metadata["type"] = metadata["memory_type"]
            
            nested_fields = [
                "time", "emotion", "importance", 
                "behavior_impact", "trigger_system", "memory_distortion"
            ]
            for key in nested_fields:
                if key in metadata and isinstance(metadata[key], str):
                    try:
                        metadata[key] = json.loads(metadata[key])
                    except json.JSONDecodeError:
                        metadata[key] = {
                            "raw_value": metadata[key],
                            "parse_error": True
                        }
            
            relevance = 1.0 - (distance / 2.0)
            
            if return_full_fields:
                memory = {
                    "id": results.get("ids", [[]])[0][i],
                    "content": doc,
                    "relevance": round(relevance, 3),
                    **metadata
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
    
    # 7. 新增：异步方法 query_memories_async
    async def query_memories_async(self, 
                character_id: str, 
                query_text: str, 
                n_results: int = 5,
                memory_type: Optional[str] = None,
                min_importance: Optional[int] = None,
                return_full_fields: bool = False) -> List[Dict[str, Any]]:
        """
        异步查询记忆（完整支持所有字段反序列化和字段映射）
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._sync_query_memories, character_id, query_text, n_results, memory_type, min_importance, return_full_fields)

    # 8. 修改：同步方法 query_memories 现在调用内部同步方法
    def query_memories(self, 
                character_id: str, 
                query_text: str, 
                n_results: int = 5,
                memory_type: Optional[str] = None,
                min_importance: Optional[int] = None,
                return_full_fields: bool = False) -> List[Dict[str, Any]]:
        """
        查询记忆（完整支持所有字段反序列化和字段映射）
        """
        return self._sync_query_memories(character_id, query_text, n_results, memory_type, min_importance, return_full_fields)
    
    # 9. 修改：同步方法 add_memories 现在调用内部同步方法
    def add_memories(self, 
                    character_id: str, 
                    memories_data: List[Dict[str, Any]]) -> List[str]:
        """
        批量添加记忆（支持完整字段存储）
        """
        return self._sync_add_memories(character_id, memories_data)
    
    # 10. 修改：同步方法 add_memory 现在调用内部同步方法
    def add_memory(self, 
                character_id: str, 
                memory_data: Dict[str, Any]) -> str:
        """
        添加单个记忆（完整支持所有记忆字段存储）
        """
        return self._sync_add_memory(character_id, memory_data)
    
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
            
            try:
                if isinstance(metadata.get("time"), str):
                    metadata["time"] = json.loads(metadata["time"])
            except json.JSONDecodeError:
                pass
            
            try:
                if isinstance(metadata.get("emotion"), str):
                    metadata["emotion"] = json.loads(metadata["emotion"])
            except json.JSONDecodeError:
                pass
            
            return {
                "id": result["ids"][0],
                "content": result["documents"][0],
                **metadata
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
            
            memory_text = f"{memory_data.get('title', '')}: {memory_data.get('content', '')}"
            
            metadata = {}
            metadata["character_id"] = character_id
            metadata["memory_type"] = memory_data.get("type", "general")
            
            time_data = memory_data.get("time", "")
            metadata["time"] = json.dumps(time_data, ensure_ascii=False) if isinstance(time_data, dict) else time_data
            
            emotion_data = memory_data.get("emotion", "neutral")
            metadata["emotion"] = json.dumps(emotion_data, ensure_ascii=False) if isinstance(emotion_data, dict) else emotion_data
            
            metadata["importance"] = memory_data.get("importance", 5)
            metadata["title"] = memory_data.get("title", "")
            
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
            self.get_collection(collection_name)
            self.client.delete_collection(collection_name)
            return True
        except Exception:
            return False

if __name__ == "__main__":
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("请设置OPENAI_API_KEY环境变量")
        exit(1)
    
    memory_store = ChromaMemoryStore(
        persist_directory="./test_chroma_db",
        openai_api_key=api_key
    )
    
    print("ChromaMemoryStore 模块已加载，异步方法已添加。")