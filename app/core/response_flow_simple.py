import asyncio
import random
from typing import Dict, Any, List
from datetime import datetime
from app.models.character import Character
from app.crud.crud_memory_simple import search_memories

class SimpleResponseFlow:
    """简化版三阶段响应流程管理器（使用模拟对话）"""
    
    def __init__(self):
        self.conversation_history = {}  # 存储对话历史
        
        # 预定义响应模板
        self.immediate_responses = {
            "greeting": [
                "你好！很高兴见到你。",
                "嗨，今天过得怎么样？",
                "你好，有什么我可以帮助你的吗？",
                "很高兴和你聊天！"
            ],
            "question": [
                "这是个有趣的问题，让我想想...",
                "嗯，关于这个问题...",
                "你问得很好，我觉得...",
                "这让我想起了一些事情..."
            ],
            "general": [
                "我明白你的意思。",
                "这确实值得思考。",
                "你说得有道理。",
                "我也有类似的感受。"
            ]
        }
        
        self.supplemented_responses = {
            "memory_based": [
                "说到这个，我想起了{memory_content}。这让我对{topic}有了更深的理解。",
                "你的话让我回想起{memory_content}。那次经历教会了我{lesson}。",
                "这提醒我想起了{memory_content}。我觉得{insight}。",
                "我记得{memory_content}。从那以后，我就{change}。"
            ],
            "personality_based": [
                "以我的性格来说，我倾向于{personality_trait}。",
                "根据我的经验，{personality_insight}。",
                "我一直相信{value}，所以我觉得{opinion}。",
                "作为一个{occupation}，我的看法是{professional_view}。"
            ]
        }
    
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
        
        # 模拟思考时间
        await asyncio.sleep(0.1)
        
        message_lower = user_message.lower()
        
        # 简单的消息分类
        if any(word in message_lower for word in ["你好", "hi", "hello", "嗨"]):
            response_type = "greeting"
        elif "?" in user_message or "？" in user_message or any(word in message_lower for word in ["什么", "为什么", "怎么", "如何"]):
            response_type = "question"
        else:
            response_type = "general"
        
        # 选择基础响应
        base_response = random.choice(self.immediate_responses[response_type])
        
        # 根据角色性格调整响应
        personality_modifier = self._get_personality_modifier(character)
        
        return f"{base_response}{personality_modifier}"
    
    async def _retrieve_relevant_memories(self, character_id: int, user_message: str) -> List[Dict[str, Any]]:
        """第二阶段：异步检索相关记忆"""
        
        try:
            # 模拟异步操作
            await asyncio.sleep(0.2)  # 模拟检索时间
            
            memories = search_memories(character_id, user_message, n_results=2)
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
        
        # 模拟思考时间
        await asyncio.sleep(0.3)
        
        if not memories:
            # 如果没有相关记忆，基于性格生成补充
            template = random.choice(self.supplemented_responses["personality_based"])
            return self._fill_personality_template(template, character)
        
        # 基于记忆生成补充响应
        memory = memories[0]  # 使用最相关的记忆
        template = random.choice(self.supplemented_responses["memory_based"])
        
        filled_response = template.replace("{memory_content}", memory["text"])
        filled_response = filled_response.replace("{topic}", self._extract_topic(user_message))
        filled_response = filled_response.replace("{lesson}", self._get_random_lesson())
        filled_response = filled_response.replace("{insight}", self._get_random_insight())
        filled_response = filled_response.replace("{change}", self._get_random_change())
        
        return f"{immediate_response} {filled_response}"
    
    def _get_personality_modifier(self, character: Character) -> str:
        """根据角色性格生成响应修饰符"""
        modifiers = []
        
        if character.ocean_extraversion > 0.6:
            modifiers.extend(["", " 我很喜欢和人交流！", " 这真是太有趣了！"])
        elif character.ocean_extraversion < 0.4:
            modifiers.extend(["", " 让我静静想想。", " 嗯..."])
        
        if character.ocean_agreeableness > 0.6:
            modifiers.extend(["", " 你说得很对。", " 我很赞同你的看法。"])
        
        if character.ocean_openness > 0.6:
            modifiers.extend(["", " 这给了我新的思路。", " 我们可以从不同角度看这个问题。"])
        
        return random.choice(modifiers) if modifiers else ""
    
    def _fill_personality_template(self, template: str, character: Character) -> str:
        """填充性格相关的模板"""
        personality_traits = []
        
        if character.ocean_extraversion > 0.6:
            personality_traits.append("主动交流和分享")
        elif character.ocean_extraversion < 0.4:
            personality_traits.append("深入思考和观察")
        
        if character.ocean_conscientiousness > 0.6:
            personality_traits.append("认真对待每件事")
        
        if character.ocean_agreeableness > 0.6:
            personality_traits.append("理解和支持他人")
        
        trait = random.choice(personality_traits) if personality_traits else "保持开放的心态"
        
        filled = template.replace("{personality_trait}", trait)
        filled = filled.replace("{personality_insight}", f"基于我的经验，{trait}很重要")
        filled = filled.replace("{value}", character.values_and_taboos or "诚实和善良")
        filled = filled.replace("{opinion}", "这样做是对的")
        filled = filled.replace("{occupation}", character.occupation or "我的工作")
        filled = filled.replace("{professional_view}", f"从{character.occupation}的角度来看，这很有意义")
        
        return filled
    
    def _extract_topic(self, message: str) -> str:
        """从消息中提取话题"""
        topics = ["工作", "生活", "学习", "人际关系", "兴趣爱好", "未来规划"]
        return random.choice(topics)
    
    def _get_random_lesson(self) -> str:
        """获取随机的人生感悟"""
        lessons = ["坚持的重要性", "沟通的价值", "学习的意义", "友谊的珍贵", "时间的宝贵"]
        return random.choice(lessons)
    
    def _get_random_insight(self) -> str:
        """获取随机的洞察"""
        insights = ["每个人都有自己的故事", "经历让人成长", "理解比判断更重要", "耐心是一种美德"]
        return random.choice(insights)
    
    def _get_random_change(self) -> str:
        """获取随机的改变"""
        changes = ["更加珍惜当下", "学会了倾听", "变得更有耐心", "更加理解他人", "更注重细节"]
        return random.choice(changes)
    
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
