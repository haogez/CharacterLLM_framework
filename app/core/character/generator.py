"""
角色生成器模块

提供基于大语言模型的角色生成功能，支持从自然语言描述生成结构化角色数据。
"""

import json
import os
import asyncio # 1. 添加 asyncio 导入
from typing import Dict, List, Any, Optional, Tuple

from app.core.llm.openai_client import CharacterLLM, OpenAIClient

class CharacterGenerator:
    """
    角色生成器类
    
    提供基于大语言模型的角色生成功能，支持从自然语言描述生成结构化角色数据
    """
    
    def __init__(self, character_llm: Optional[CharacterLLM] = None):
        """
        初始化角色生成器
        
        Args:
            character_llm: 角色LLM客户端，如果为None则创建新实例
        """
        self.character_llm = character_llm or CharacterLLM()
    
    # 2. 修改：generate_character 方法改为 async
    async def generate_character(self, description: str) -> Dict[str, Any]:
        """
        从自然语言描述生成角色
        
        Args:
            description: 角色描述
            
        Returns:
            角色数据字典
        """
        # 3. 修改：await 调用 LLM 异步方法
        character_data = await self.character_llm.generate_character(description)
        
        # 确保生成的角色数据包含必要的字段
        self._validate_and_fix_character_data(character_data)
        
        return character_data
    
    # 4. 修改：generate_memories 方法改为 async
    async def generate_memories(self, character_data: Dict[str, Any], count: int = 10) -> List[Dict[str, Any]]:
        """
        为角色生成记忆
        
        Args:
            character_data: 角色数据
            count: 生成的记忆数量
            
        Returns:
            记忆数据列表
        """
        # 记忆类型及其分配比例
        memory_types = {
            "education": 0.2,  # 教育经历
            "work": 0.3,       # 工作经历
            "family": 0.2,     # 家庭生活
            "hobby": 0.1,      # 兴趣爱好
            "trauma": 0.1,     # 创伤经历
            "achievement": 0.1 # 成就
        }
        
        # 根据比例计算每种类型的记忆数量
        type_counts = {}
        remaining = count
        for memory_type, ratio in memory_types.items():
            type_count = max(1, int(count * ratio))
            if remaining >= type_count:
                type_counts[memory_type] = type_count
                remaining -= type_count
            else:
                type_counts[memory_type] = remaining
                remaining = 0
        
        # 如果还有剩余，分配给工作经历
        if remaining > 0:
            type_counts["work"] += remaining
        
        # 生成各类型记忆
        all_memories = []
        for memory_type, type_count in type_counts.items():
            for _ in range(type_count):
                # 5. 修改：await 调用 LLM 异步方法
                memory = await self.character_llm.generate_memory(character_data, memory_type)
                # 确保记忆类型字段存在
                memory["type"] = memory_type
                all_memories.append(memory)
        
        return all_memories
    
    def _validate_and_fix_character_data(self, character_data: Dict[str, Any]) -> None:
        """
        验证并修复角色数据
        
        Args:
            character_data: 角色数据
        """
        # 确保基本字段存在
        if "name" not in character_data:
            character_data["name"] = "Unknown name"
        if "age" not in character_data:
            character_data["age"] = 30  # 默认年龄为整数
        elif isinstance(character_data["age"], str):
            # 如果age是字符串，尝试转换为整数
            try:
                character_data["age"] = int(character_data["age"])
            except ValueError:
                character_data["age"] = 30
        if "gender" not in character_data:
            character_data["gender"] = "Unknown gender"
        if "occupation" not in character_data:
            character_data["occupation"] = "Unknown occupation"
        if "background" not in character_data:
            character_data["background"] = "Unknown background"
        
        # 确保人格特征存在
        if "personality" not in character_data:
            character_data["personality"] = {
                "openness": 50,
                "conscientiousness": 50,
                "extraversion": 50,
                "agreeableness": 50,
                "neuroticism": 50
            }
        else:
            # 确保OCEAN五维特征完整
            ocean_traits = ["openness", "conscientiousness", "extraversion", "agreeableness", "neuroticism"]
            for trait in ocean_traits:
                if trait not in character_data["personality"]:
                    character_data["personality"][trait] = 50
        
        # 确保语言风格字段存在
        if "speech_style" not in character_data:
            character_data["speech_style"] = "Neutral and standard speech pattern."


# 测试代码
if __name__ == "__main__":
    # Note: The synchronous test script needs to be adapted to use async/await
    # Example using asyncio.run:
    # import asyncio
    # async def test():
    #     api_key = os.environ.get("OPENAI_API_KEY")
    #     if not api_key:
    #         print("请设置OPENAI_API_KEY环境变量")
    #         return
    #     character_generator = CharacterGenerator()
    #     description = "一位生活在90年代上海的退休语文教师，性格温和，喜欢读书写字"
    #     print(f"生成角色: {description}")
    #     character = await character_generator.generate_character(description)
    #     print("\n生成的角色:")
    #     print(json.dumps(character, ensure_ascii=False, indent=2))
    #     print("\n生成角色记忆...")
    #     memories = await character_generator.generate_memories(character, count=5)
    #     print("\n生成的记忆:")
    #     for i, memory in enumerate(memories, 1):
    #         print(f"\n记忆 {i} [{memory['type']}]:")
    #         print(f"标题: {memory.get('title', 'Unknown')}")
    #         print(f"内容: {memory.get('content', 'Unknown')}")
    #         print(f"时间: {memory.get('time', 'Unknown')}")
    #         print(f"情感: {memory.get('emotion', 'neutral')}")
    #         print(f"重要性: {memory.get('importance', 5)}/10")
    # asyncio.run(test())
    print("CharacterGenerator 模块已加载，方法已异步化。")