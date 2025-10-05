import openai
import asyncio
from typing import Dict, Any, List
from datetime import datetime
from app.models.character import Character
from app.crud.crud_memory import search_memories

class ResponseFlow:
    """三阶段响应流程管理器"""
    
    def __init__(self, api_key: str):
        self.client = openai.OpenAI(api_key=api_key)
        self.conversation_history = {}  # 存储对话历史
    
    async def process_message(self, character: Character, user_message: str) -> Dict[str, Any]:
        """处理用户消息，执行三阶段响应流程"""
        
        # 第一阶段：下意识响应
        immediate_response = await self._generate_immediate_response(character, user_message)
        
        # 第二阶段：异步记忆检索
        memory_task = asyncio.create_task(
            self._retrieve_relevant_memories(character.id, user_message)
        )
        
        # 立即返回下意识响应
        result = {
            "character_id": character.id,
            "response": immediate_response,
            "response_type": "immediate",
            "timestamp": datetime.utcnow()
        }
        
        # 等待记忆检索完成
        try:
            memories = await memory_task
            
            # 第三阶段：生成补充响应
            if memories:
                supplemented_response = await self._generate_supplemented_response(
                    character, user_message, immediate_response, memories
                )
                
                result.update({
                    "supplemented_response": supplemented_response,
                    "response_type": "supplemented",
                    "memories_used": len(memories)
                })
        except Exception as e:
            print(f"记忆检索或补充响应生成失败: {e}")
        
        # 更新对话历史
        self._update_conversation_history(character.id, user_message, result["response"])
        
        return result
    
    async def _generate_immediate_response(self, character: Character, user_message: str) -> str:
        """第一阶段：生成下意识响应"""
        
        personality_prompt = self._build_personality_prompt(character)
        conversation_context = self._get_conversation_context(character.id)
        
        prompt = f"""
{personality_prompt}

对话历史：
{conversation_context}

用户说: {user_message}

请以{character.name}的身份，根据你的性格特征和语言风格，给出一个自然、即时的回应。
这应该是一个基于直觉和性格的快速反应，不需要回忆具体的详细记忆。
保持角色的一致性，体现出{character.name}的个性特点。
"""
        
        try:
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": f"你正在扮演{character.name}，请保持角色的一致性。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=200
            )
            
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            print(f"生成即时响应时出错: {e}")
            return f"抱歉，我需要一点时间来思考..."
    
    async def _retrieve_relevant_memories(self, character_id: int, user_message: str) -> List[Dict[str, Any]]:
        """第二阶段：异步检索相关记忆"""
        
        try:
            # 模拟异步操作
            await asyncio.sleep(0.1)  # 小延迟模拟检索时间
            
            memories = search_memories(character_id, user_message, n_results=3)
            return memories
            
        except Exception as e:
            print(f"检索记忆时出错: {e}")
            return []
    
    async def _generate_supplemented_response(
        self, 
        character: Character, 
        user_message: str, 
        immediate_response: str, 
        memories: List[Dict[str, Any]]
    ) -> str:
        """第三阶段：生成补充响应"""
        
        personality_prompt = self._build_personality_prompt(character)
        memory_context = self._build_memory_context(memories)
        
        prompt = f"""
{personality_prompt}

用户说: {user_message}
你的即时回应: {immediate_response}

相关记忆：
{memory_context}

现在，请基于这些记忆，对你的即时回应进行补充和深化。
你可以：
1. 分享相关的具体经历
2. 提供更详细的背景信息
3. 表达更深层的情感或想法
4. 连接过去的经历与当前的对话

请保持自然的对话流程，就像是在回忆过程中想起了这些细节。
"""
        
        try:
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": f"你正在扮演{character.name}，现在要基于记忆补充你的回应。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.8,
                max_tokens=400
            )
            
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            print(f"生成补充响应时出错: {e}")
            return immediate_response  # 如果失败，返回原始响应
    
    def _build_personality_prompt(self, character: Character) -> str:
        """构建角色性格提示"""
        return f"""
你是{character.name}，{character.age}岁，职业是{character.occupation}，来自{character.region}。

你的性格特征：
- 开放性: {character.ocean_openness:.2f} (0=保守 1=开放)
- 尽责性: {character.ocean_conscientiousness:.2f} (0=随意 1=严谨)
- 外向性: {character.ocean_extraversion:.2f} (0=内向 1=外向)
- 宜人性: {character.ocean_agreeableness:.2f} (0=竞争 1=合作)
- 神经质: {character.ocean_neuroticism:.2f} (0=稳定 1=敏感)

语言风格: {character.language_style}
价值观与禁忌: {character.values_and_taboos}
行为边界: {character.behavioral_boundaries}
"""
    
    def _build_memory_context(self, memories: List[Dict[str, Any]]) -> str:
        """构建记忆上下文"""
        if not memories:
            return "没有找到相关记忆。"
        
        context = ""
        for i, memory in enumerate(memories, 1):
            context += f"{i}. {memory['text']}\n"
            if memory.get('metadata', {}).get('event_type'):
                context += f"   (类型: {memory['metadata']['event_type']})\n"
        
        return context
    
    def _get_conversation_context(self, character_id: int, max_turns: int = 3) -> str:
        """获取对话上下文"""
        history = self.conversation_history.get(character_id, [])
        
        if not history:
            return "这是对话的开始。"
        
        # 获取最近的几轮对话
        recent_history = history[-max_turns:]
        context = ""
        
        for turn in recent_history:
            context += f"用户: {turn['user_message']}\n"
            context += f"{turn['character_name']}: {turn['response']}\n\n"
        
        return context
    
    def _update_conversation_history(self, character_id: int, user_message: str, response: str):
        """更新对话历史"""
        if character_id not in self.conversation_history:
            self.conversation_history[character_id] = []
        
        self.conversation_history[character_id].append({
            "user_message": user_message,
            "response": response,
            "character_name": f"角色{character_id}",
            "timestamp": datetime.utcnow()
        })
        
        # 保持历史记录在合理范围内
        if len(self.conversation_history[character_id]) > 10:
            self.conversation_history[character_id] = self.conversation_history[character_id][-10:]
