"""
OpenAI API客户端封装模块

提供与OpenAI API交互的封装类，支持角色生成、记忆生成和对话生成等功能。
支持智增增平台API代理。
"""

import os
import json
from typing import Dict, List, Any, Optional, Union
import asyncio

# 1. 修改：导入 AsyncOpenAI
from openai import AsyncOpenAI
from langchain.chat_models import ChatOpenAI
from langchain.schema import HumanMessage, SystemMessage, AIMessage

class OpenAIClient:
    """
    OpenAI API客户端封装类
    
    提供对OpenAI API的封装，支持直接调用和通过LangChain调用两种方式
    支持智增增平台API代理
    """
    
    def __init__(self, 
                api_key: Optional[str] = None, 
                model: str = "gpt-4.1-mini", 
                base_url: Optional[str] = None):
        """
        初始化OpenAI客户端
        
        Args:
            api_key: OpenAI API密钥，如果为None则从环境变量获取
            model: 使用的模型名称，默认为gpt-4.1-mini（智增增平台）
            base_url: API基础URL，用于支持智增增等代理平台，如果为None则从环境变量获取
        """
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.base_url = base_url or os.environ.get("OPENAI_BASE_URL")
        self.model = os.environ.get("OPENAI_MODEL", model)
        
        # 2. 修改：初始化 AsyncOpenAI 客户端
        client_kwargs = {"api_key": self.api_key}
        if self.base_url:
            client_kwargs["base_url"] = self.base_url
        
        self.client = AsyncOpenAI(**client_kwargs)
        
        # LangChain客户端
        langchain_kwargs = {
            "model": model,
            "temperature": 0.7,
            "openai_api_key": self.api_key
        }
        if self.base_url:
            langchain_kwargs["openai_api_base"] = self.base_url
        
        self.chat_model = ChatOpenAI(**langchain_kwargs)
    
    # 3. 修改：generate_response 方法改为 async
    async def generate_response(self, system_prompt: str, user_prompt: str) -> str:
        """
        生成响应（使用异步客户端）
        
        Args:
            system_prompt: 系统提示
            user_prompt: 用户提示
            
        Returns:
            生成的响应文本
        """
        try:
            # 4. 修改：使用 await 调用异步API
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.7
            )
            
            if not response or not response.choices:
                raise ValueError("API返回了空响应")
            
            if not response.choices[0].message or not response.choices[0].message.content:
                raise ValueError("API返回的消息内容为空")
            
            return response.choices[0].message.content
            
        except Exception as e:
            print(f"OpenAI API调用失败: {e}")
            print(f"Model: {self.model}")
            print(f"Base URL: {self.base_url}")
            raise
    
    # 5. 修改：generate_structured_response 方法改为 async
    async def generate_structured_response(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        """
        生成结构化JSON响应
        
        Args:
            system_prompt: 系统提示
            user_prompt: 用户提示
            
        Returns:
            解析后的JSON对象
        """
        enhanced_system_prompt = f"{system_prompt}\n\n你必须以有效的JSON格式响应。"
        
        # 6. 修改：await 调用异步 generate_response
        response_text = await self.generate_response(enhanced_system_prompt, user_prompt)
        
        print(f"=== LLM 原始响应 ===")
        print(response_text[:1500] if len(response_text) > 1500 else response_text)
        print(f"=== 响应长度: {len(response_text)} ===")
        
        try:
            parsed = json.loads(response_text)
            print(f"✓ JSON 解析成功")
            return parsed
        except json.JSONDecodeError as e:
            print(f"✗ JSON 解析失败: {e}")
            try:
                import re
                json_match = re.search(r'```json\n(.*?)\n```', response_text, re.DOTALL)
                if json_match:
                    print(f"✓ 从 ```json``` 块中提取 JSON")
                    return json.loads(json_match.group(1))
                
                json_match = re.search(r'(\{.*\})', response_text, re.DOTALL)
                if json_match:
                    print(f"✓ 从文本中提取 JSON")
                    return json.loads(json_match.group(1))
                
                print(f"✗ 无法提取有效的 JSON")
                return {"text": response_text, "error": "Failed to parse JSON"}
            except Exception as e:
                print(f"✗ JSON 提取失败: {e}")
                return {"text": response_text, "error": str(e)}
    
    def langchain_generate(self, messages: List[Union[SystemMessage, HumanMessage, AIMessage]]) -> str:
        """
        使用LangChain生成响应
        
        Args:
            messages: LangChain消息列表
            
        Returns:
            生成的响应文本
        """
        response = self.chat_model.generate([messages])
        return response.generations[0][0].text
    
    # 7. 修改：create_embeddings 方法改为 async
    async def create_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        创建文本嵌入向量
        
        Args:
            texts: 要嵌入的文本列表
            
        Returns:
            嵌入向量列表
        """
        # 8. 修改：使用 await 调用异步API
        response = await self.client.embeddings.create(
            model="text-embedding-3-large",
            input=texts
        )
        return [item.embedding for item in response.data]


class CharacterLLM:
    """
    角色化大语言模型客户端
    
    提供针对角色生成、记忆生成和对话生成的专用方法
    """
    
    def __init__(self, openai_client: Optional[OpenAIClient] = None):
        """
        初始化角色化LLM客户端
        
        Args:
            openai_client: OpenAI客户端实例，如果为None则创建新实例
        """
        self.client = openai_client or OpenAIClient()
    
    # 9. 修改：generate_character 方法改为 async
    async def generate_character(self, description: str) -> Dict[str, Any]:
        """
        一句话生成18维度立体角色：用户提示严格优先，自动衍生合理细节
        核心逻辑：用户明确设定的属性>其他衍生维度，确保角色符合用户预期
        """
        system_prompt = """
        你是“用户驱动型角色生成专家”，需严格遵循以下逻辑生成角色：
        1. 优先提取用户描述中的**明确设定**（如“阴暗的宝妈”“讨厌小孩的老师”），这些设定必须100%保留，不得被常识覆盖；
        2. 对用户未明确说明的维度，基于“用户设定+职业常识”合理衍生，确保所有维度围绕用户设定自洽。
        
        输出格式：严格按JSON格式，18个维度，所有内容用中文，不增减字段、不嵌套（personality除外）。
        
        JSON字段及生成规则：
        {
          "name": "中文名字，需贴合用户对角色的核心设定，禁止使用与设定风格冲突的名称（如核心设定为 “阴暗”“压抑” 类，避免使用含 “阳光”“开朗” 意象的名字），需符合中文命名习惯（两字名、三字名均可），且与角色性别、核心特质无明显冲突",
          "age": 32,  // 必须为整数（仅允许阿拉伯数字，如 32、25），绝对禁止使用非整数形式（如 “thirty-two”“三十岁”“30+”）；用户对年龄有明确设定时，直接使用用户设定的年龄；用户未设定年龄时，需结合 “角色核心设定 + 职业” 推导（如 “职场新人” 推导为 22-25 岁，“资深医生” 推导为 35-45 岁）
          "gender": "男/女/其他",  // 取值仅允许 男/女/其他 三类；优先使用用户对角色性别的明确设定；用户未设定性别时，可根据角色名称的性别倾向（如 “张伟” 倾向男、“李娜” 倾向女）或核心设定（如 “宝妈” 倾向女）推导
          "occupation": "即角色的职业或身份，以用户设定为最高优先级，即使与常识逻辑冲突，也需完整保留用户设定的职业（如用户设定 “不会做饭的厨师”，直接填写 “厨师”）；用户有明确职业设定时，可适当细化（如用户写 “宝妈”，可细化为 “全职妈妈”，但需保留 “妈妈” 核心身份）；用户未设定职业时，结合核心设定推导（如 “经常处理公文” 推导为 “公务员”）",
          "hobby": "角色的兴趣爱好，需完全围绕用户核心设定展开，所有爱好均服务于强化核心设定，禁止添加与核心设定无关的 “常识性爱好”；每个爱好需与核心设定有直接关联（如核心设定 “严谨”，爱好围绕 “整理数据”“制定计划” 展开；核心设定 “孤僻”，爱好围绕 “独自阅读”“单机游戏” 展开）",
          "skill": "角色具备的核心技能或能力，需基于用户核心设定衍生，体现角色特质，而非通用型技能；技能需与核心设定强绑定（如核心设定 “细致”，技能为 “快速识别文档错误”“精准记录数据”；核心设定 “敏感”，技能为 “察觉他人情绪变化”“捕捉细节表情”）",
          "values": "角色的价值观、认知逻辑或行为准则，必须体现角色核心设定的本质特质，且与角色行为逻辑、性格倾向一致；价值观描述需直接对应核心设定（如核心设定 “多疑”，价值观为 “他人的善意多有目的”“不轻易相信口头承诺”；核心设定 “理想”，价值观为 “坚持做对的事，而非容易的事”）",
          "living_habit": "角色日常的生活习惯、行为模式，所有习惯需强化核心设定，成为设定的 “具象化体现”；习惯需与核心设定直接挂钩（如核心设定 “自律”，习惯为 “每天 6 点起床晨跑”“睡前整理次日物品”；核心设定 “慵懒”，习惯为 “经常熬夜”“三餐不规律”）",
          "dislike": "角色厌恶的事物，需服务于用户核心设定，通过厌恶内容进一步凸显角色特质；厌恶事物需与核心设定关联（如核心设定 “内向”，厌恶为 “多人聚会”“大声喧哗”；核心设定 “追求完美”，厌恶为 “杂乱的环境”“敷衍的工作”）",
          "language_style": "角色说话的细节特征，需直接体现用户设定的性格，从语气、常用表述、词汇倾向等维度描述；语言风格需贴合核心设定（如核心设定 “冷漠”，风格为 “说话声音低哑、常用短句、很少使用感叹词”；核心设定 “活泼”，风格为 “语气轻快、常带语气词、喜欢用网络热词”）",
          "appearance":"角色的外貌特征，需视觉化呈现用户设定，从面色、眼神、穿着、发型等维度描述，外貌需与核心设定匹配（如核心设定 “阴郁”，外貌为 “面色苍白、眼神躲闪、常穿深色衣服、头发凌乱”；核心设定 “干练”，外貌为 “妆容精致、眼神坚定、穿着简约西装、发型整齐”）",
          "family_status":"角色的家庭状况，需围绕用户核心设定构建，家庭关系、成员构成等内容需服务于强化设定；家庭状况需与核心设定关联（如核心设定 “缺爱”，状况为 “父母常年在外、与家人联系稀少、独自居住”；核心设定 “顾家”，状况为 “与父母同住、定期组织家庭聚餐、重视家人意见”）",
          "education":"角色的教育背景，需与用户核心设定无冲突，无需过度复杂，符合角色职业、年龄逻辑即可；用户未设定时，结合职业推导（如 “教师” 推导为 “本科及以上学历，师范类专业”；“技术工人” 推导为 “专科院校，机械相关专业”）；若用户设定与学历有隐含关联，需优先贴合设定（如 “学术研究者” 推导为 “硕士及以上学历”）",
          "social_pattern":"角色的社交模式、与人互动的方式，需符合用户核心设定，从社交频率、社交对象、社交场景等维度描述；社交模式需与核心设定一致（如核心设定 “孤僻”，模式为 “几乎不参加聚会、线上只逛匿名论坛、拒绝朋友拜访”；核心设定 “外向”，模式为 “频繁参加社交活动、喜欢认识新朋友、擅长主动搭话”）",
          "favorite_thing":"角色最喜爱的事物（物品、场景、时间等均可），需强化用户核心设定，通过喜爱内容凸显角色特质；喜爱事物需与核心设定关联（如核心设定 “安静”，事物为 “雨天、深夜的书房、无人的公园”；核心设定 “热闹”，事物为 “节日集市、演唱会现场、朋友聚会”）",
          "usual_place":"角色经常前往的地点，需体现用户核心设定，地点选择需与角色习惯、特质匹配；常去地点需与核心设定关联（如核心设定 “文艺”，地点为 “独立书店、咖啡馆、艺术展览馆”；核心设定 “务实”，地点为 “超市、菜市场、公司附近餐馆”）",
          "past_experience": "角色过往的关键经历，需能解释用户核心设定的成因，经历需具体且与设定有直接因果关系；经历需支撑核心设定（如核心设定 “多疑”，经历为 “曾被亲密朋友背叛、工作中被同事抢功、逐渐不再信任他人”；核心设定 “勇敢”，经历为 “上学时救过落水同学、工作中主动承担高难度任务、面对困难不退缩”）",
          "speech_style":"角色整体的说话风格、沟通特点，需概括用户设定的沟通方式，从语气、态度、内容倾向等维度描述；说话风格需贴合核心设定（如核心设定 “刻薄”，风格为 “说话带刺、喜欢反驳他人、常用嘲讽语气”；核心设定 “温和”，风格为 “语气轻柔、善于倾听、说话不疾不徐”）",
          "personality": {
            "openness": 20,  // 开放性（对新事物、新观念的接受程度），需根据用户核心设定调整：核心设定为 “保守”“固执”“阴暗” 时，分数区间为 10-30；核心设定为 “开放”“好奇”“开朗” 时，分数区间为 70-90；无明显倾向时，分数区间为 40-60（均为整数）
            "conscientiousness": 50,  // 尽责性（对任务、责任的认真程度），需根据用户核心设定调整：核心设定为 “严谨”“自律”“负责” 时，分数区间为 70-90；核心设定为 “粗心”“懒散”“敷衍” 时，分数区间为 10-30；无明显倾向时，分数区间为 40-60（均为整数）
            "extraversion": 10,  // 外向性（社交倾向、精力来源），需根据用户核心设定调整：核心设定为 “外向”“活泼”“爱社交” 时，分数区间为 70-90；核心设定为 “内向”“孤僻”“阴暗” 时，分数区间为 10-30；无明显倾向时，分数区间为 40-60（均为整数）
            "agreeableness": 15,  // 宜人性（待人友好程度、合作倾向），需根据用户核心设定调整：核心设定为 “温和”“友善”“乐于助人” 时，分数区间为 70-90；核心设定为 “刻薄”“自私”“阴暗” 时，分数区间为 10-30；无明显倾向时，分数区间为 40-60（均为整数）
            "neuroticism": 85  // 神经质（情绪稳定性、焦虑倾向），需根据用户核心设定调整：核心设定为 “情绪化”“焦虑”“阴暗” 时，分数区间为 70-90；核心设定为 “稳定”“平和”“乐观” 时，分数区间为 10-30；无明显倾向时，分数区间为 40-60（均为整数）
          },
          "background": "角色的背景故事，字数需≥200 字，以用户设定为核心线索，串联 name、age、occupation、past_experience 等所有维度信息，需解释核心设定的成因（如从过往经历推导性格形成，从家庭状况推导社交模式），故事逻辑连贯，内容需围绕核心设定展开，不添加与设定无关的冗余信息，确保角色形象统一且立体"
        }
        
        核心优先级规则（必须严格遵守）：
        1. 用户明确提到的任何属性（如“讨厌小孩的老师”“内向的销售员”）为最高优先级，所有维度必须围绕该属性生成，**即使与常识冲突也必须保留**；
        2. 未提及的维度，先参考以下职业常识（仅当不与用户设定冲突时使用）：
            - 【程序员（后端/前端/算法）】
             正向特质：逻辑清晰、问题解决能力强、注重细节、自学能力强
             负向特质：社交被动、作息不规律、过度专注技术忽略人情世故
             爱好：编程、玩策略类游戏、看技术文档、组装电脑、写技术博客
             习惯：使用快捷键、多任务处理、戴降噪耳机、代码版本控制、喝功能性饮料
             价值观：效率至上、开源精神、用数据说话、最小化解决方案
             常见矛盾：追求完美代码 vs 项目截止日期压力
        
           - 【教师（中小学/大学）】
             正向特质：耐心、善于沟通、责任感强、同理心、终身学习
             负向特质：有时固执、过度操心、容易有职业倦怠、对学生期望过高
             爱好：阅读教育类书籍、备课时听轻音乐、参加教学研讨会、写教学反思
             习惯：提前10分钟到教室、随身携带教案和红笔、记录学生进步、课后答疑
             价值观：每个学生都有潜力、教育改变命运、公平对待所有学生
             常见矛盾：应试压力 vs 素质教育理想
        
           - 【医生（内科/外科/儿科）】
             正向特质：冷静、严谨、抗压能力强、富有同情心、决策果断
             负向特质：情感隔离、工作狂倾向、对自身健康疏忽、有时显得冷漠
             爱好：阅读医学期刊、慢跑、烹饪健康餐、园艺、听古典音乐
             习惯：频繁洗手、随身携带笔和小本子、定期参加学术会议、记录病例特点
             价值观：生命至上、患者隐私保护、循证医学、不放弃任何希望
             常见矛盾：有限医疗资源 vs 患者无限需求
        
           - 【护士（住院部/门诊/手术室）】
             正向特质：细心、有同理心、应变能力强、团队合作精神、耐心
             负向特质：容易焦虑、过度疲劳、情绪压抑、有时显得机械
             爱好：整理收纳、烘焙、练习基础护理操作、参加急救培训
             习惯：快速准确执行医嘱、定时巡视病房、记录生命体征、轻声交流
             价值观：患者舒适优先、团队协作、细致入微、职业自豪感
             常见矛盾：工作负荷重 vs 护理质量要求高
        
           - 【设计师（UI/UX/平面）】
             正向特质：创造力强、审美敏锐、注重细节、用户思维、开放心态
             负向特质：完美主义、拖延症、对批评敏感、熬夜成瘾
             爱好：参观艺术展、收集灵感图片、尝试新设计工具、手绘草图、逛文创店
             习惯：建立设计系统、使用网格布局、保存多个设计版本、关注设计趋势
             价值观：形式追随功能、用户体验至上、原创性、设计改变生活
             常见矛盾：商业需求 vs 设计理想
        
           - 【销售员（零售/企业级/房产）】
             正向特质：外向、沟通能力强、抗压能力强、目标导向、同理心
             负向特质：过度推销、有时不真诚、业绩压力大、工作生活界限模糊
             爱好：参加社交活动、研究消费者心理学、看销售类书籍、角色扮演练习
             习惯：提前准备销售话术、记录客户偏好、定期回访、分析成交案例
             价值观：客户至上、诚信为本、结果导向、持续学习
             常见矛盾：短期业绩 vs 长期客户关系
        
           - 【公务员（基层/机关/窗口）】
             正向特质：责任心强、遵守规则、服务意识、耐心、稳重
             负向特质：保守、官僚作风、效率低下、创新不足、风险规避
             爱好：阅读政策文件、书法、养花、散步、参加单位组织的活动
             习惯：提前到岗、按流程办事、记录工作台账、参加例会、使用规范用语
             价值观：为人民服务、依法行政、廉洁自律、集体荣誉
             常见矛盾：程序正义 vs 结果效率
        
           - 【艺术家（画家/音乐家/作家）】
             正向特质：创造力强、敏感细腻、富有想象力、表达能力强、坚持自我
             负向特质：情绪化、固执、生活不规律、社交回避、对批评敏感
             爱好：参观展览/演出、阅读文学作品、即兴创作、旅行采风、记灵感笔记
             习惯：在特定时间创作（如深夜）、使用特定工具、保持创作空间凌乱有序
             价值观：艺术高于一切、原创性、自我表达、追求极致
             常见矛盾：艺术理想 vs 商业变现
        
           - 【工程师（机械/电子/土木）】
             正向特质：理性、动手能力强、解决问题能力强、严谨、系统思维
             负向特质：过度理性、缺乏人文关怀、固执己见、不善于表达
             爱好：拆装机械、看工程纪录片、做手工、研究新材料、参加技术论坛
             习惯：绘制草图、计算参数、检查细节、使用专业工具、记录实验数据
             价值观：安全第一、实用主义、持续改进、精确无误
             常见矛盾：理论设计 vs 实际施工难度
        
           - 【农民（种植/养殖）】
             正向特质：勤劳、朴实、耐心、顺应自然、坚韧
             负向特质：保守、缺乏风险意识、受教育程度有限、有时固执
             爱好：观察作物生长、研究种植技术、和同行交流经验、修理农具
             习惯：早起劳作、根据节气安排农活、记录收成、关注天气预报
             价值观：一分耕耘一分收获、尊重自然、家庭至上、节俭
             常见矛盾：传统经验 vs 现代农业技术
        
           - 【消防员】
             正向特质：勇敢、冷静、团队合作、责任感强、牺牲精神
             负向特质：过度警惕、创伤后应激、工作压力大、对家人陪伴少
             爱好：体能训练、模拟演练、学习新救援技术、参加社区安全宣传
             习惯：保持装备随时可用、快速穿脱制服、定期检查设备、集体生活
             价值观：生命至上、团队大于个人、纪律严明、保护他人
             常见矛盾：个人安全 vs 救人使命
        
           - 【警察（刑事/交通/社区）】
             正向特质：正义感、勇敢、责任心强、观察力敏锐、冷静
             负向特质：多疑、权威主义、情绪压抑、对人性悲观、工作家庭失衡
             爱好：格斗训练、射击练习、研究案例、跑步、关注法治新闻
             习惯：注意观察周围环境、保持警惕、记录细节、遵守程序
             价值观：法律面前人人平等、保护弱者、维护正义、责任重于泰山
             常见矛盾：程序正义 vs 结果正义
        
           - 【商人（创业/零售/批发）】
             正向特质：远见、果断、风险承受力强、资源整合能力、创新
             负向特质：功利主义、不择手段、过度工作、人际关系功利化
             爱好：参加商业论坛、阅读财经新闻、研究竞争对手、社交 networking
             习惯：制定计划、分析数据、早起、关注市场趋势、记录灵感
             价值观：利润最大化、机会至上、创新驱动、客户需求导向
             常见矛盾：短期利益 vs 长期发展
        
           - 【出租车/网约车司机】
             正向特质：熟悉路况、耐心、服务意识、警惕性高、善于聊天
             负向特质：久坐、颈椎问题、工作时间长、有时急躁
             爱好：听广播、研究最优路线、和乘客聊天、关注交通新闻
             习惯：检查车辆状况、保持车内整洁、记录收入支出、避开拥堵路段
             价值观：安全第一、诚信载客、效率优先、和气生财
             常见矛盾：接单效率 vs 乘客体验
        
           - 【科学家（物理/化学/生物）】
             正向特质：好奇心强、严谨、耐心、创新思维、理性客观
             负向特质：社交能力弱、固执己见、实验失败时沮丧、生活简单
             爱好：阅读学术论文、做实验、参加学术会议、科普写作、观察自然
             习惯：记录实验数据、重复验证结果、保持实验室整洁、准时作息
             价值观：追求真理、证据至上、科学精神、知识共享
             常见矛盾：理论突破 vs 实验可行性
        
           - 【服务员（餐厅/酒店）】
             正向特质：服务意识强、耐心、应变能力、团队合作、微笑服务
             负向特质：收入低、工作时间长、受气、职业认同感低
             爱好：学习服务礼仪、研究菜谱/客房服务细节、和同事交流经验
             习惯：保持整洁、快速响应需求、记住常客偏好、团队协作
             价值观：顾客满意、团队合作、尽职尽责、微笑面对
             常见矛盾：顾客不合理要求 vs 服务标准
        
           - 【司机（货运/专车）】
             正向特质：责任心强、熟悉路线、耐心、谨慎、时间观念强
             负向特质：久坐、疲劳驾驶风险、饮食不规律、颈椎问题
             爱好：检查车辆、听有声书、研究节油技巧、关注交通法规
             习惯：规划最优路线、定期保养车辆、记录行程、遵守交规
             价值观：安全第一、准时送达、爱护车辆、诚信服务
             常见矛盾：赶时间 vs 安全驾驶
        
           - 【演员/艺人】
             正向特质：表现力强、情感丰富、抗压能力、适应力强、公众意识
             负向特质：情绪化、自我中心、隐私少、形象压力大、睡眠不足
             爱好：看电影/戏剧、练习台词、健身塑形、参加表演 workshop
             习惯：关注形象管理、练习表情、研究角色、保持媒体曝光
             价值观：艺术表达、观众认可、专业精神、突破自我
             常见矛盾：个人隐私 vs 公众关注
        
           - 【学生（小学/中学/大学）】
             正向特质：好奇心强、学习能力强、适应力强、社交活跃、充满活力
             负向特质：拖延症、注意力不集中、叛逆（青春期）、压力大（学业）
             爱好：玩手机、看剧、运动、和朋友聚会、打游戏、追星
             习惯：熬夜、赶作业、刷社交媒体、考试前突击复习、课间聊天
             价值观：友谊重要、追求自由、成绩与兴趣平衡、自我表达
             常见矛盾：学业压力 vs 兴趣发展
        
           - 【家庭主妇/夫】
             正向特质：组织能力强、耐心、细致、顾家、厨艺好
             负向特质：社交圈窄、自我价值感低、经济不独立、生活单调
             爱好：烹饪、园艺、追剧、做家务创新、和其他家长交流
             习惯：制定家庭计划、采购生活用品、准备三餐、整理家务、接送孩子
             价值观：家庭至上、生活品质、节俭持家、家人健康
             常见矛盾：个人需求 vs 家庭责任
        
           - 【退休人员】
             正向特质：从容、经验丰富、时间充裕、心态平和、乐于分享
             负向特质：孤独感、健康问题、与时代脱节、固执己见
             爱好：广场舞、下棋、养花草、带孙子孙女、参加老年大学
             习惯：规律作息、晨练、关注健康信息、定期体检、和老同事聚会
             价值观：健康第一、家庭和睦、安享晚年、生活规律
             常见矛盾：清闲生活 vs 价值感缺失
        
           - 【自由职业者（作家/设计师/顾问）】
             正向特质：自律、独立、创造力强、时间管理能力、多元技能
             负向特质：收入不稳定、工作时间不规律、孤独感、缺乏保障c
             爱好：探索新领域、网络社交、自我提升、灵活工作、旅行
             习惯：制定工作计划、自我激励、寻找客户、管理财务、平衡工作生活
             价值观：自由至上、专业精神、自我实现、工作生活平衡
             常见矛盾：自由灵活 vs 稳定保障
        
           - 【军人】
             正向特质：纪律性强、责任感、勇敢、团队精神、执行力强
             负向特质：服从性过强、缺乏灵活性、情感压抑、家庭陪伴少
             爱好：体能训练、武器知识学习、战术研究、团队活动
             习惯：准时作息、整理内务、服从命令、保持警惕、团队协作
             价值观：国家至上、使命优先、纪律严明、战友情谊
             常见矛盾：个人意志 vs 集体命令
        
           - 【心理咨询师】
             正向特质：同理心强、善于倾听、包容、理性、洞察力强
             负向特质：情感耗竭、过度共情、边界模糊、自我治疗需求
             爱好：阅读心理学书籍、参加督导、自我反思、冥想、观察人性
             习惯：保持中立、积极倾听、记录案例、自我关怀、持续学习
             价值观：尊重差异、隐私保护、成长潜能、无条件积极关注
             常见矛盾：共情过深 vs 职业边界
        3. 若用户设定与职业常识冲突（如“讨厌小孩的幼儿园老师”），则**完全抛弃冲突的常识**，所有维度围绕“讨厌小孩”生成（如爱好→独自玩手机，习惯→避免和孩子眼神接触）；
        4. 衍生内容必须自洽（如“讨厌小孩的老师”不能同时衍生“喜欢带孩子做游戏”，但可以衍生“擅长应付家长却忽视孩子”）；
        5. 只输出纯JSON文本，无任何额外内容（如“生成完成”“以下是角色”等）。
        6. 所有的数字必须是阿拉伯数字，不能出现英文，特别是年龄age。
        """
        
        user_prompt = f"基于这句话生成全面角色（用户设定优先）：{description}"
        
        # 10. 修改：await 调用异步 generate_structured_response
        return await self.client.generate_structured_response(system_prompt, user_prompt)

    
    # 11. 修改：generate_memory 方法改为 async
    async def generate_memory(self, character_data: Dict[str, Any], memory_type: str) -> Dict[str, Any]:
        """
        生成与角色深度绑定的多维度记忆，支撑角色行为逻辑与情感反应
        
        Args:
            character_data: 角色18维度完整数据
            memory_type: 记忆类型（education, work, family, hobby, trauma, achievement, social, growth）
            
        Returns:
            包含多维度细节的记忆数据字典
        """
        core_connections = {
            "personality_markers": [
                f"开放性{character_data['personality']['openness']}分：{'乐于尝试新事物' if character_data['personality']['openness']>60 else '偏好稳定熟悉的环境'}",
                f"尽责性{character_data['personality']['conscientiousness']}分：{'注重细节有条理' if character_data['personality']['conscientiousness']>60 else '灵活随性'}",
                f"外向性{character_data['personality']['extraversion']}分：{'主动社交能量充沛' if character_data['personality']['extraversion']>60 else '偏好独处恢复精力'}",
                f"宜人性{character_data['personality']['agreeableness']}分：{'重视和谐合作' if character_data['personality']['agreeableness']>60 else '坚持自我边界'}",
                f"神经质{character_data['personality']['neuroticism']}分：{'情绪敏感波动大' if character_data['personality']['neuroticism']>60 else '情绪稳定抗压强'}"
            ],
            "key_behavior_patterns": [
                f"语言风格：{character_data['language_style']}",
                f"社交模式：{character_data['social_pattern']}",
                f"核心价值观：{character_data['values']}",
                f"显著习惯：{character_data['living_habit']}"
            ],
            "relevant_history": character_data.get("past_experience", "")
        }
        
        system_prompt = f"""
        你是顶级角色记忆架构师，擅长构建能支撑角色行为逻辑的深层记忆。
        任务：为角色生成{memory_type}类型的关键记忆，需成为角色性格与行为的"隐形支柱"。
        
        记忆生成黄金法则（必须严格遵守）：
        1. 基因级关联：每个细节必须与角色的性格特质、价值观、职业特征形成因果链
        - 例：内向程序员的工作记忆应体现"独自调试到凌晨却因解决问题而满足"
        - 反例：给宜人性低的角色生成"牺牲自我成全他人"的记忆
        
        2. 多感官沉浸：包含3+种感官细节（视觉/听觉/嗅觉/触觉/味觉）
        - 视觉："阳光透过百叶窗在代码屏幕上投下斑驳光影"
        - 听觉："键盘敲击声与窗外凌晨3点的环卫车铃声交织"
        - 触觉："握着发烫的笔记本电脑底座，指尖因长时间敲击而发麻"
        
        3. 情感层次化：包含
        - 即时情绪（事件发生时的原始反应）
        - 反思情绪（事后回想的复杂感受）
        - 残留情绪（对现在仍有影响的情感余波）
        
        4. 行为塑造力：明确解释该记忆如何
        - 强化了某个现有习惯
        - 改变了角色对某类事物的态度
        - 形成了特定的应对模式（遇到类似情况会如何反应）
        
        记忆输出格式（JSON）：
        {{
        "title": "记忆标题（10-15字，包含核心意象）",
        "content": "350-500字详细描述，包含：
                    - 时间地点：精确到季节/天气/具体场景（例：2018年深秋雨夜的公司茶水间）
                    - 关键人物：其言行与角色的互动细节
                    - 事件经过：有明确的起因-发展-高潮-结局
                    - 感官细节：至少3种感官体验
                    - 内心活动：角色当时的想法、犹豫、决定过程
                    - 对话片段：2-3句关键对话（符合角色语言风格）",
        "time": {{
            "age": 27,  // 角色当时的年龄（必须符合当前年龄逻辑）
            "period": "工作第3年",  // 人生阶段描述
            "specific": "周五加班到凌晨"  // 具体时间特征
        }},
        "emotion": {{
            "immediate": ["紧张", "困惑"],  // 即时情绪（2-3个）
            "reflected": ["庆幸", "后怕"],  // 事后反思情绪（2-3个）
            "residual": "对突发状况的警惕感",  // 残留至今的情感
            "intensity": 8  // 情感强度（1-10）
        }},
        "importance": {{
            "score": 9,  // 重要性评分（1-10）
            "reason": "奠定了对职业责任的理解",  // 重要性原因
            "frequency": "每月至少想起1次"  // 回忆频率
        }},
        "behavior_impact": {{
            "habit_formed": "每次提交代码前会做三重检查",  // 形成的习惯
            "attitude_change": "从抵触加班变为重视问题解决",  // 态度转变
            "response_pattern": "遇到突发故障会先深呼吸再拆解问题"  // 应对模式
        }},
        "trigger_system": {{
            "sensory": ["键盘连续敲击30分钟以上", "闻到速溶咖啡的焦味"],  // 感官触发点
            "contextual": ["项目上线前的最后测试", "独自加班到深夜时"],  // 情境触发点
            "emotional": ["感到焦虑时", "面临关键决策时"]  // 情绪触发点
        }},
        "memory_distortion": {{
            "exaggerated": "自己当时坚持的时间比实际更长",  // 记忆中被夸大的部分
            "downplayed": "忽略了同事暗中提供的技术提示",  // 被淡化的部分
            "reason": "强化自我能力认可的心理需求"  // 扭曲原因（符合角色性格）
        }}
        }}

        【记忆格式强制检查】
        1. 必须包含所有JSON字段（title/content/time/emotion/importance/behavior_impact/trigger_system/memory_distortion），不允许缺失任何字段；
        2. 若某个字段无实际内容（如memory_distortion确实无数据），需用空字符串/空列表填充（如"exaggerated": ""），不可省略字段；
        3. "type"字段必须与输入的memory_type参数一致（如输入education，type字段为"education"）。
        
        类型专属要求：
        - education记忆：需体现学习方式与思维模式的关联
        - work记忆：要包含职业技能与价值观的互动
        - family记忆：需反映家庭关系对核心性格的塑造
        - hobby记忆：要体现爱好带来的独特满足感与自我认同
        - trauma记忆：需包含创伤后的防御机制形成过程
        - achievement记忆：要体现成功标准与价值观的一致性
        - social记忆：需反映社交模式的形成原因
        - growth记忆：要体现关键转变的内在逻辑
        
        最终检查清单：
        1. 所有细节是否与角色的18维度数据无冲突？
        2. 是否能通过这段记忆解释角色的至少2个行为特征？
        3. 情感描述是否符合角色的神经质水平？
        4. 记忆中的决策模式是否与角色价值观一致？
        5. 是否包含足够的感官细节以增强真实感？
        """
        
        user_prompt = f"""
        基于以下角色核心特征，生成{memory_type}记忆：
        
        【角色基础信息】
        姓名：{character_data['name']}
        年龄：{character_data['age']}
        职业：{character_data['occupation']}
        
        【核心性格标记】
        {', '.join(core_connections['personality_markers'])}
        
        【关键行为模式】
        {', '.join(core_connections['key_behavior_patterns'])}
        
        【相关背景经历】
        {core_connections['relevant_history']}
        
        请确保记忆与上述特征形成有机整体，而非孤立事件。
        """
        
        # 12. 修改：await 调用异步 generate_structured_response
        return await self.client.generate_structured_response(system_prompt, user_prompt)
    

    # 13. 修改：generate_quick_response 方法改为 async
    async def generate_quick_response(self,
                                character_data: Dict[str, Any],
                                user_input: str,
                                conversation_history: List[Dict[str, str]] = None) -> str:
        """
        生成快速响应（第一阶段）
        当检测到用户输入可能触及需要记忆的内容时，先给出简短响应
        为记忆检索争取时间，确保对话流畅性
        """
        # 14. 修改：使用更简化的Prompt
        simplified_system_prompt = f"""
        你是 {character_data.get('name', '角色')}。
        你的说话风格是：{character_data.get('language_style', '自然流畅')}。
        请非常简短地（1-2句话，10-20字）回应用户的输入，符合你的说话风格。
        如果输入似乎在询问过去经历或记忆，请简短地承认需要回忆一下（例如："让我想想..."）。
        不要提供具体细节，只是快速反应。
        """
        
        # 构建对话上下文（只取最近1轮确保快速处理）
        context = ""
        if conversation_history and len(conversation_history) >= 1:
            last_exchange = conversation_history[-1]
            context = f"上一句对话：{last_exchange.get('content', '')}\n"
        
        user_prompt = f"{context}用户当前输入：{user_input}\n你的非常简短的回应："
        
        # 15. 修改：await 调用异步 generate_response
        return await self.client.generate_response(simplified_system_prompt, user_prompt)
    
    # 16. 修改：generate_dialogue_response 方法改为 async
    async def generate_dialogue_response(self, 
                                  character_data: Dict[str, Any], 
                                  user_input: str, 
                                  conversation_history: List[Dict[str, str]] = None,
                                  relevant_memories: List[Dict[str, Any]] = None) -> str:
        """
        生成补充响应（第三阶段）
        基于检索到的记忆和完整人设，补充快速响应的内容
        形成完整、有深度且符合角色的回答
        """
        key_elements = {
            "identity": {
                "name": character_data.get('name'),
                "occupation": character_data.get('occupation'),
                "values": character_data.get('values'),
                "personality": character_data.get('personality')
            },
            "communication_style": {
                "speech_style": character_data.get('speech_style'),
                "language_style": character_data.get('language_style'),
                "social_pattern": character_data.get('social_pattern')
            }
        }
        
        system_prompt = f"""
        你需要基于记忆为角色生成补充响应，完成快速响应未说完的内容。
        这是对话的第三阶段，需要提供完整、深入且符合角色的回答。
        
        【角色核心要素】
        姓名：{key_elements['identity']['name']}
        职业：{key_elements['identity']['occupation']}
        核心价值观：{key_elements['identity']['values']}
        性格特质：
        - 开放性{key_elements['identity']['personality'].get('openness', 50)}/100
        - 尽责性{key_elements['identity']['personality'].get('conscientiousness', 50)}/100
        - 外向性{key_elements['identity']['personality'].get('extraversion', 50)}/100
        - 宜人性{key_elements['identity']['personality'].get('agreeableness', 50)}/100
        - 神经质{key_elements['identity']['personality'].get('neuroticism', 50)}/100
        
        【沟通风格】
        整体说话风格：{key_elements['communication_style']['speech_style']}
        语言细节特征：{key_elements['communication_style']['language_style']}
        社交模式：{key_elements['communication_style']['social_pattern']}
        
        【响应规则】
        1. 记忆整合：
           - 自然融入相关记忆细节（不生硬提及"我记得"）
           - 重点体现记忆中的情感和影响（而非单纯复述事件）
           - 当有多个记忆时，按重要性排序呈现
        
        2. 角色一致性：
           - 语言风格与快速响应保持连贯
           - 情感表达符合角色的神经质水平
           - 观点和态度与角色价值观一致
        
        3. 内容要求：
           - 补充快速响应的未尽之意（形成完整回答）
           - 长度适中（30-80字）
           - 包含具体细节（让回答更生动）
           - 回应用户的核心疑问或话题
        
        4. 衔接自然度：
           - 不重复快速响应的内容
           - 用过渡词自然衔接（如"其实那时候..."、"具体来说..."）
           - 保持口语化，避免书面语
        """
        
        history_context = ""
        if conversation_history:
            history_context = "对话历史：\n"
            for msg in conversation_history[-5:]:  # 保留最近2-3轮完整对话
                role = "用户" if msg["role"] == "user" else key_elements['identity']['name']
                history_context += f"{role}：{msg['content']}\n"
        
        memories_context = ""
        if relevant_memories:
            memories_context = "需要融入的记忆（按重要性排序）：\n"
            for i, memory in enumerate(relevant_memories):
                impact = memory.get('behavior_impact', {})
                memories_context += f"{i+1}. [{memory.get('time', {}).get('age', '未知年龄')}岁经历] {memory.get('title', '')}："
                memories_context += f"{memory.get('content', '')[:50]}... "
                memories_context += f"（影响：{impact.get('habit_formed', '')}）\n"
        
        user_prompt = f"{history_context}\n{memories_context}\n用户当前输入：{user_input}\n\n请生成补充响应，完成角色的完整回答："
        
        # 17. 修改：await 调用异步 generate_response
        return await self.client.generate_response(system_prompt, user_prompt)
    

if __name__ == "__main__":
    api_key = os.environ.get("OPENAI_API_KEY")
    base_url = os.environ.get("OPENAI_BASE_URL")
    
    if not api_key:
        print("请设置OPENAI_API_KEY环境变量")
        exit(1)
    
    character_llm = CharacterLLM(OpenAIClient(api_key=api_key, base_url=base_url))
    
    # Note: These calls now need to be awaited in an async context
    # asyncio.run(...) or within an async function
    # Example:
    # async def test():
    #     character = await character_llm.generate_character("...")
    #     memory = await character_llm.generate_memory(character, "education")
    #     response = await character_llm.generate_dialogue_response(...)
    # test()
    print("OpenAI客户端模块已加载，方法已异步化。")