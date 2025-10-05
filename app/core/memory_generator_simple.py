import random
from typing import List, Dict, Any
from app.models.character import Character
from app.crud.crud_memory_simple import add_memory

class SimpleMemoryGenerator:
    """简化版角色记忆生成器（使用模板数据）"""
    
    def __init__(self):
        # 预定义记忆模板
        self.memory_templates = {
            "教育经历": [
                "小学时期在{region}的一所普通小学就读，成绩中等",
                "中学时代参加过学校的{activity}社团，结识了很多朋友",
                "大学期间主修{subject}专业，对{interest}产生了浓厚兴趣",
                "毕业论文写的是关于{topic}的研究，获得了导师的好评"
            ],
            "工作成就": [
                "刚入职时因为{skill}能力突出，很快得到了上司的认可",
                "在{year}年的项目中担任{role}，成功完成了{task}",
                "曾经帮助一位{colleague}解决了工作难题，建立了深厚友谊",
                "获得过{award}奖项，这是对我工作能力的肯定"
            ],
            "家庭生活": [
                "童年时和{relative}一起度过了很多快乐时光",
                "家里养过一只{pet}，给我的生活带来了很多乐趣",
                "每年{festival}都会和家人团聚，这是我最珍视的时刻",
                "父母教会我{value}的重要性，这影响了我的一生"
            ],
            "兴趣爱好": [
                "从小就喜欢{hobby}，这让我在业余时间很充实",
                "曾经为了{goal}而努力练习{skill}，虽然辛苦但很有成就感",
                "和朋友们一起{activity}是我最快乐的时光",
                "通过{hobby}认识了很多志同道合的朋友"
            ],
            "人际关系": [
                "有一位{friend_type}朋友，我们经常一起{activity}",
                "在{place}遇到了一位{person}，他/她教会了我{lesson}",
                "曾经和{someone}发生过误会，但后来通过沟通化解了",
                "有一位{mentor}对我影响很大，他/她的{quality}让我很敬佩"
            ],
            "生活感悟": [
                "经历过{difficulty}后，我明白了{wisdom}的重要性",
                "在{situation}中学会了{skill}，这让我变得更加{quality}",
                "有一次{experience}让我深刻体会到{feeling}",
                "通过{event}我认识到{truth}，这改变了我的人生观"
            ]
        }
        
        # 填充词汇库
        self.fill_words = {
            "activity": ["篮球", "音乐", "绘画", "写作", "摄影", "舞蹈"],
            "subject": ["计算机", "文学", "历史", "经济", "心理学", "艺术"],
            "interest": ["科技", "文化", "艺术", "体育", "旅游", "美食"],
            "topic": ["人工智能", "文学创作", "历史研究", "经济分析", "心理健康", "艺术表现"],
            "skill": ["沟通", "组织", "分析", "创新", "领导", "协调"],
            "year": ["2018", "2019", "2020", "2021", "2022", "2023"],
            "role": ["组长", "协调员", "负责人", "主要成员", "技术骨干", "项目经理"],
            "task": ["重要任务", "技术攻关", "团队建设", "客户服务", "产品开发", "质量改进"],
            "colleague": ["新同事", "老员工", "实习生", "合作伙伴", "客户", "供应商"],
            "award": ["优秀员工", "创新", "团队合作", "客户服务", "技术突破", "年度最佳"],
            "relative": ["爷爷奶奶", "外公外婆", "叔叔阿姨", "哥哥姐姐", "弟弟妹妹", "表兄弟姐妹"],
            "pet": ["小狗", "小猫", "金鱼", "小鸟", "仓鼠", "乌龟"],
            "festival": ["春节", "中秋节", "国庆节", "元旦", "端午节", "重阳节"],
            "value": ["诚实", "勤奋", "善良", "坚持", "宽容", "责任"],
            "hobby": ["读书", "运动", "音乐", "绘画", "旅游", "烹饪"],
            "goal": ["提高技能", "参加比赛", "完成作品", "达成目标", "克服困难", "实现梦想"],
            "friend_type": ["知心", "童年", "大学", "工作", "邻居", "网友"],
            "place": ["图书馆", "咖啡厅", "公园", "健身房", "培训班", "旅途中"],
            "person": ["老师", "前辈", "陌生人", "志愿者", "艺术家", "专家"],
            "lesson": ["耐心", "坚持", "创新", "合作", "思考", "表达"],
            "someone": ["同事", "朋友", "家人", "邻居", "同学", "合作伙伴"],
            "mentor": ["老师", "上司", "前辈", "朋友", "家长", "专家"],
            "quality": ["智慧", "耐心", "热情", "专业", "人格魅力", "工作态度"],
            "difficulty": ["挫折", "失败", "困难", "挑战", "压力", "变化"],
            "wisdom": ["坚持", "适应", "学习", "沟通", "合作", "创新"],
            "situation": ["工作", "学习", "生活", "旅行", "比赛", "项目"],
            "experience": ["失败的经历", "成功的体验", "意外的收获", "深刻的教训", "美好的回忆", "重要的决定"],
            "feeling": ["成长的喜悦", "友谊的珍贵", "家庭的温暖", "工作的意义", "生活的美好", "梦想的力量"],
            "event": ["这次经历", "那个项目", "这段时光", "那次旅行", "这个挑战", "那个机会"],
            "truth": ["努力的重要性", "友谊的珍贵", "家庭的意义", "学习的价值", "健康的重要", "时间的宝贵"]
        }
    
    def generate_memories(self, character: Character, num_memories: int = 8) -> List[str]:
        """为角色生成记忆事件"""
        
        memory_ids = []
        event_types = list(self.memory_templates.keys())
        
        for i in range(num_memories):
            # 随机选择事件类型
            event_type = random.choice(event_types)
            
            # 随机选择模板
            template = random.choice(self.memory_templates[event_type])
            
            # 填充模板
            memory_text = self._fill_template(template, character)
            
            # 添加记忆
            memory_id = add_memory(
                character_id=character.id,
                memory_text=memory_text,
                event_type=event_type,
                metadata={
                    "generated": True,
                    "template_based": True
                }
            )
            memory_ids.append(memory_id)
        
        return memory_ids
    
    def _fill_template(self, template: str, character: Character) -> str:
        """填充记忆模板"""
        filled_template = template
        
        # 替换角色相关信息
        filled_template = filled_template.replace("{region}", character.region or "本地")
        filled_template = filled_template.replace("{name}", character.name)
        filled_template = filled_template.replace("{occupation}", character.occupation or "工作")
        
        # 替换其他占位符
        for placeholder, options in self.fill_words.items():
            if f"{{{placeholder}}}" in filled_template:
                replacement = random.choice(options)
                filled_template = filled_template.replace(f"{{{placeholder}}}", replacement)
        
        return filled_template
    
    def add_custom_memory(self, character_id: int, memory_text: str, event_type: str = "自定义") -> str:
        """添加自定义记忆"""
        return add_memory(
            character_id=character_id,
            memory_text=memory_text,
            event_type=event_type,
            metadata={"generated": False, "custom": True}
        )
