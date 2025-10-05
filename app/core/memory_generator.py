import openai
import json
from typing import List, Dict, Any
from app.models.character import Character
from app.crud.crud_memory import add_memory

class MemoryGenerator:
    """角色记忆生成器"""
    
    def __init__(self, api_key: str):
        self.client = openai.OpenAI(api_key=api_key)
        
        # 预定义事件类型库
        self.event_types = [
            "教育经历", "工作成就", "家庭生活", "兴趣爱好", 
            "创伤事件", "社会交往", "重要决定", "旅行经历",
            "健康状况", "情感经历", "技能学习", "挫折失败"
        ]
    
    def generate_memories(self, character: Character, num_memories: int = 10) -> List[str]:
        """为角色生成记忆事件"""
        
        character_context = self._build_character_context(character)
        
        prompt = f"""
你是一个专业的角色背景设计师。请为以下角色生成{num_memories}个具体的记忆事件。

角色信息：
{character_context}

请生成具体、详细的记忆事件，每个事件应该：
1. 符合角色的背景设定（年龄、职业、地域、时代背景）
2. 体现角色的性格特征
3. 包含具体的时间、地点、人物、事件细节
4. 涵盖不同类型的人生经历

事件类型包括但不限于：{', '.join(self.event_types)}

请按照以下JSON格式输出：
{{
    "memories": [
        {{
            "text": "详细的记忆事件描述",
            "event_type": "事件类型",
            "time_period": "大概的时间段"
        }}
    ]
}}

示例：
{{
    "memories": [
        {{
            "text": "1995年春天，我带着班上的学生参加市里的作文比赛。那个叫小明的孩子写了一篇关于他奶奶的文章，最后获得了一等奖。看到他激动得哭了，我也忍不住红了眼眶。",
            "event_type": "工作成就",
            "time_period": "1995年"
        }}
    ]
}}
"""
        
        try:
            response = self.client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=[
                    {"role": "system", "content": "你是一个专业的角色背景设计师，擅长创建真实、具体的人生经历。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.8,
                max_tokens=2000
            )
            
            content = response.choices[0].message.content
            
            # 提取JSON部分
            import re
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                json_str = json_match.group()
                memories_data = json.loads(json_str)
                
                # 存储记忆到ChromaDB
                memory_ids = []
                for memory in memories_data.get("memories", []):
                    memory_id = add_memory(
                        character_id=character.id,
                        memory_text=memory["text"],
                        event_type=memory.get("event_type", "未分类"),
                        metadata={
                            "time_period": memory.get("time_period", "未知"),
                            "generated": True
                        }
                    )
                    memory_ids.append(memory_id)
                
                return memory_ids
            else:
                raise ValueError("无法从响应中提取有效的JSON")
                
        except Exception as e:
            print(f"生成记忆时出错: {e}")
            # 生成默认记忆
            return self._generate_default_memories(character)
    
    def _build_character_context(self, character: Character) -> str:
        """构建角色上下文信息"""
        context = f"""
姓名: {character.name}
年龄: {character.age}
职业: {character.occupation}
地域: {character.region}

性格特征 (OCEAN模型):
- 开放性: {character.ocean_openness:.2f}
- 尽责性: {character.ocean_conscientiousness:.2f}
- 外向性: {character.ocean_extraversion:.2f}
- 宜人性: {character.ocean_agreeableness:.2f}
- 神经质: {character.ocean_neuroticism:.2f}

语言风格: {character.language_style}
价值观与禁忌: {character.values_and_taboos}
行为边界: {character.behavioral_boundaries}
"""
        return context
    
    def _generate_default_memories(self, character: Character) -> List[str]:
        """生成默认记忆（当生成失败时使用）"""
        default_memories = [
            f"{character.name}在{character.region}长大，有着普通的童年经历。",
            f"作为一名{character.occupation}，{character.name}在工作中积累了丰富的经验。",
            f"{character.name}喜欢在空闲时间思考人生和未来。"
        ]
        
        memory_ids = []
        for i, memory_text in enumerate(default_memories):
            memory_id = add_memory(
                character_id=character.id,
                memory_text=memory_text,
                event_type="默认记忆",
                metadata={"generated": True, "default": True}
            )
            memory_ids.append(memory_id)
        
        return memory_ids
    
    def add_custom_memory(self, character_id: int, memory_text: str, event_type: str = "自定义") -> str:
        """添加自定义记忆"""
        return add_memory(
            character_id=character_id,
            memory_text=memory_text,
            event_type=event_type,
            metadata={"generated": False, "custom": True}
        )
