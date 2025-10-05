"""
ChromaDB向量存储模块

提供与ChromaDB交互的封装类，支持记忆的存储、检索和管理。
"""

import os
import uuid
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
        添加记忆
        
        Args:
            character_id: 角色ID
            memory_data: 记忆数据
            
        Returns:
            记忆ID
        """
        collection_name = self.get_character_collection_name(character_id)
        collection = self.create_collection(collection_name)
        
        # 生成记忆ID
        memory_id = str(uuid.uuid4())
        
        # 准备记忆文本
        memory_text = f"{memory_data.get('title', '')}: {memory_data.get('content', '')}"
        
        # 准备元数据
        metadata = {
            "character_id": character_id,
            "memory_type": memory_data.get("type", "general"),
            "time": memory_data.get("time", ""),
            "emotion": memory_data.get("emotion", "neutral"),
            "importance": memory_data.get("importance", 5),
            "title": memory_data.get("title", "")
        }
        
        # 添加到集合
        collection.add(
            documents=[memory_text],
            metadatas=[metadata],
            ids=[memory_id]
        )
        
        return memory_id
    
    def add_memories(self, 
                    character_id: str, 
                    memories: List[Dict[str, Any]]) -> List[str]:
        """
        批量添加记忆
        
        Args:
            character_id: 角色ID
            memories: 记忆数据列表
            
        Returns:
            记忆ID列表
        """
        collection_name = self.get_character_collection_name(character_id)
        collection = self.create_collection(collection_name)
        
        # 准备批量添加数据
        memory_ids = [str(uuid.uuid4()) for _ in range(len(memories))]
        memory_texts = []
        metadatas = []
        
        for memory_data in memories:
            # 准备记忆文本
            memory_text = f"{memory_data.get('title', '')}: {memory_data.get('content', '')}"
            memory_texts.append(memory_text)
            
            # 准备元数据
            metadata = {
                "character_id": character_id,
                "memory_type": memory_data.get("type", "general"),
                "time": memory_data.get("time", ""),
                "emotion": memory_data.get("emotion", "neutral"),
                "importance": memory_data.get("importance", 5),
                "title": memory_data.get("title", "")
            }
            metadatas.append(metadata)
        
        # 批量添加到集合
        collection.add(
            documents=memory_texts,
            metadatas=metadatas,
            ids=memory_ids
        )
        
        return memory_ids
    
    def query_memories(self, 
                      character_id: str, 
                      query_text: str, 
                      n_results: int = 5,
                      memory_type: Optional[str] = None,
                      min_importance: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        查询记忆
        
        Args:
            character_id: 角色ID
            query_text: 查询文本
            n_results: 返回结果数量
            memory_type: 记忆类型过滤
            min_importance: 最小重要性过滤
            
        Returns:
            记忆列表
        """
        collection_name = self.get_character_collection_name(character_id)
        
        try:
            collection = self.get_collection(collection_name)
        except ValueError:
            # 如果集合不存在，返回空列表
            return []
        
        # 准备查询过滤条件
        where_clause = {"character_id": character_id}
        if memory_type:
            where_clause["memory_type"] = memory_type
        if min_importance is not None:
            where_clause["importance"] = {"$gte": min_importance}
        
        # 执行查询
        results = collection.query(
            query_texts=[query_text],
            n_results=n_results,
            where=where_clause if len(where_clause) > 1 else None  # 只有character_id时不使用where过滤
        )
        
        # 处理结果
        memories = []
        for i, (doc, metadata, distance) in enumerate(zip(
            results.get("documents", [[]])[0],
            results.get("metadatas", [[]])[0],
            results.get("distances", [[]])[0]
        )):
            memory = {
                "id": results.get("ids", [[]])[0][i],
                "content": doc,
                "relevance": 1.0 - (distance / 2.0),  # 转换距离为相关性分数
                **metadata
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
            
            return {
                "id": result["ids"][0],
                "content": result["documents"][0],
                **result["metadatas"][0]
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
            
            # 准备元数据
            metadata = {
                "character_id": character_id,
                "memory_type": memory_data.get("type", "general"),
                "time": memory_data.get("time", ""),
                "emotion": memory_data.get("emotion", "neutral"),
                "importance": memory_data.get("importance", 5),
                "title": memory_data.get("title", "")
            }
            
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
    
    # 测试添加记忆
    memory_id = memory_store.add_memory(
        character_id=character_id,
        memory_data={
            "type": "education",
            "title": "大学毕业",
            "content": "1965年从北京师范大学中文系毕业，成为一名光荣的人民教师。",
            "time": "1965年",
            "emotion": "positive",
            "importance": 9
        }
    )
    print(f"添加记忆成功，ID: {memory_id}")
    
    # 测试批量添加记忆
    memory_ids = memory_store.add_memories(
        character_id=character_id,
        memories=[
            {
                "type": "work",
                "title": "教学成就",
                "content": "1980年被评为市级优秀教师，获得表彰。",
                "time": "1980年",
                "emotion": "positive",
                "importance": 8
            },
            {
                "type": "family",
                "title": "女儿出生",
                "content": "1970年女儿出生，取名丽华，全家欢喜。",
                "time": "1970年",
                "emotion": "positive",
                "importance": 10
            }
        ]
    )
    print(f"批量添加记忆成功，ID列表: {memory_ids}")
    
    # 测试查询记忆
    query_results = memory_store.query_memories(
        character_id=character_id,
        query_text="教学经历",
        n_results=5
    )
    print("\n查询结果:")
    for memory in query_results:
        print(f"- [{memory['memory_type']}] {memory['title']} (相关性: {memory['relevance']:.2f})")
        print(f"  {memory['content']}")
    
    # 测试按类型查询
    education_memories = memory_store.query_memories(
        character_id=character_id,
        query_text="教育经历",
        memory_type="education"
    )
    print("\n教育类记忆:")
    for memory in education_memories:
        print(f"- {memory['title']}: {memory['content']}")
    
    # 测试按重要性查询
    important_memories = memory_store.query_memories(
        character_id=character_id,
        query_text="重要经历",
        min_importance=9
    )
    print("\n重要记忆:")
    for memory in important_memories:
        print(f"- {memory['title']} (重要性: {memory['importance']}): {memory['content']}")
    
    # 测试获取单个记忆
    if memory_id:
        memory = memory_store.get_memory_by_id(character_id, memory_id)
        if memory:
            print(f"\n获取记忆 {memory_id}:")
            print(f"- {memory['title']}: {memory['content']}")
    
    # 测试更新记忆
    if memory_id:
        update_success = memory_store.update_memory(
            character_id=character_id,
            memory_id=memory_id,
            memory_data={
                "type": "education",
                "title": "大学毕业（更新）",
                "content": "1965年从北京师范大学中文系毕业，以优异成绩成为一名光荣的人民教师。",
                "time": "1965年",
                "emotion": "positive",
                "importance": 9
            }
        )
        print(f"\n更新记忆 {memory_id}: {'成功' if update_success else '失败'}")
        
        # 验证更新
        memory = memory_store.get_memory_by_id(character_id, memory_id)
        if memory:
            print(f"更新后的记忆: {memory['title']}: {memory['content']}")
    
    # 测试删除记忆
    if memory_ids and len(memory_ids) > 0:
        delete_success = memory_store.delete_memory(character_id, memory_ids[0])
        print(f"\n删除记忆 {memory_ids[0]}: {'成功' if delete_success else '失败'}")
    
    # 清理测试数据
    print("\n清理测试数据...")
    memory_store.delete_all_memories(character_id)
    print("测试完成")
