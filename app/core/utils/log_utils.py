# app/core/utils/log_utils.py
"""
日志工具函数模块
提供统一的日志格式化函数。
"""

def log_section_start(title: str, char: str = "="):
    """打印分隔线开始的标题"""
    print(f"\n{char*80}", flush=True) # 添加 flush=True
    print(f" {title} ".center(80, char), flush=True) # 添加 flush=True
    print(f"{char*80}", flush=True) # 添加 flush=True

def log_section_end(char: str = "="):
    """打印分隔线结束"""
    print(f"{char*80}\n", flush=True) # 添加 flush=True

def log_info(message: str, indent: int = 0):
    """打印信息日志"""
    print("  " * indent + f"ℹ️  {message}", flush=True) # 添加 flush=True

def log_success(message: str, indent: int = 0):
    """打印成功日志"""
    print("  " * indent + f"✅ {message}", flush=True) # 添加 flush=True

def log_warning(message: str, indent: int = 0):
    """打印警告日志"""
    print("  " * indent + f"⚠️  {message}", flush=True) # 添加 flush=True

def log_error(message: str, indent: int = 0):
    """打印错误日志"""
    print("  " * indent + f"❌ {message}", flush=True) # 添加 flush=True

def log_debug(message: str, indent: int = 0):
    """打印调试日志（可选，生产环境可关闭）"""
    print("  " * indent + f"🔍 {message}", flush=True) # 添加 flush=True

# ... (其余函数也类似修改) ...

def log_character_creation(char_id: str, char_name: str, gen_time: float):
    """专门打印角色创建完成日志"""
    log_section_start(f"角色 [{char_name}] (ID: {char_id}) 创建完成", "=")
    log_success(f"角色生成耗时: {gen_time:.2f} 秒")
    log_section_end("=")

def log_memory_generation_summary(char_id: str, char_name: str, self_memories: int, other_memories: int, total_time: float):
    """专门打印记忆生成摘要日志"""
    log_section_start(f"角色 [{char_name}] (ID: {char_id}) 记忆生成摘要", "=")
    log_success(f"自关系记忆数: {self_memories}")
    log_success(f"其他关系记忆数: {other_memories}")
    log_info(f"记忆生成+存储耗时: {total_time:.2f} 秒")
    log_section_end("=")

def log_chat_start(character_id: str, user_input: str):
    """打印对话开始日志"""
    log_section_start("开始处理对话请求", "-")
    log_info(f"角色ID: {character_id}")
    log_info(f"用户输入: {user_input}")
    log_section_end("-")

def log_chat_response(response_type: str, character_id: str, user_input: str, content: str, timestamp: float, memory_count: int = 0):
    """打印对话响应日志"""
    log_section_start(f"{response_type.upper()} 响应发送", "-")
    log_info(f"角色ID: {character_id}")
    log_info(f"用户输入: {user_input}")
    log_info(f"响应内容: {content[:150]}{'...' if len(content) > 150 else ''}")
    log_info(f"耗时: {timestamp:.2f}秒")
    if memory_count > 0:
        log_info(f"关联记忆数: {memory_count}")
    log_section_end("-")

def log_chat_complete(character_id: str, user_input: str, total_time: float, response_count: int):
    """打印对话完成日志"""
    log_section_start("对话响应完成", "=")
    log_info(f"角色ID: {character_id}")
    log_info(f"用户输入: {user_input}")
    log_info(f"总耗时: {total_time:.2f}秒")
    log_info(f"发送响应数: {response_count}")
    log_section_end("=")