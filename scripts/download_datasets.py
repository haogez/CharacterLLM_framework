#!/usr/bin/env python3
"""
数据集下载脚本

下载并处理PersonaHub数据集，用于角色生成和记忆生成。
"""

import os
import json
import argparse
from pathlib import Path
from typing import Dict, List, Any

from datasets import load_dataset
from tqdm import tqdm

def download_personahub(output_dir: str, sample_size: int = 1000) -> None:
    """
    下载PersonaHub数据集
    
    Args:
        output_dir: 输出目录
        sample_size: 样本大小
    """
    print(f"下载PersonaHub数据集 (样本大小: {sample_size})...")
    
    # 创建输出目录
    os.makedirs(output_dir, exist_ok=True)
    
    # 下载数据集
    dataset = load_dataset("proj-persona/PersonaHub",name="persona", split="train")
    
    # 获取样本
    if sample_size > 0 and sample_size < len(dataset):
        dataset = dataset.select(range(sample_size))
    
    # 保存数据集
    personas = []
    for item in tqdm(dataset, desc="处理数据"):
        persona = {
            "name": item.get("name", ""),
            "age": item.get("age", 30),
            "gender": item.get("gender", ""),
            "occupation": item.get("occupation", ""),
            "background": item.get("background", ""),
            "personality": {
                "openness": item.get("openness", 50),
                "conscientiousness": item.get("conscientiousness", 50),
                "extraversion": item.get("extraversion", 50),
                "agreeableness": item.get("agreeableness", 50),
                "neuroticism": item.get("neuroticism", 50)
            },
            "values": item.get("values", []),
            "speech_style": item.get("speech_style", "")
        }
        personas.append(persona)
    
    # 保存为JSON文件
    output_file = os.path.join(output_dir, "personahub.json")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(personas, f, ensure_ascii=False, indent=2)
    
    print(f"数据集已保存到 {output_file}")
    print(f"共 {len(personas)} 个角色")

def download_perltqa(output_dir: str, sample_size: int = 1000) -> None:
    """
    下载PerLTQA数据集（个人长期记忆问答数据集）
    
    Args:
        output_dir: 输出目录
        sample_size: 样本大小
    """
    print(f"下载PerLTQA数据集 (样本大小: {sample_size})...")
    
    # 创建输出目录
    os.makedirs(output_dir, exist_ok=True)
    
    try:
        # 下载数据集
        dataset = load_dataset("allenai/perltqa", split="train")
        
        # 获取样本
        if sample_size > 0 and sample_size < len(dataset):
            dataset = dataset.select(range(sample_size))
        
        # 保存数据集
        memories = []
        for item in tqdm(dataset, desc="处理数据"):
            memory = {
                "question": item.get("question", ""),
                "answer": item.get("answer", ""),
                "context": item.get("context", ""),
                "type": item.get("type", "general")
            }
            memories.append(memory)
        
        # 保存为JSON文件
        output_file = os.path.join(output_dir, "perltqa.json")
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(memories, f, ensure_ascii=False, indent=2)
        
        print(f"数据集已保存到 {output_file}")
        print(f"共 {len(memories)} 条记忆")
    except Exception as e:
        print(f"下载PerLTQA数据集失败: {str(e)}")
        print("使用模拟数据代替...")
        
        # 创建模拟数据
        memories = []
        memory_types = ["education", "work", "family", "hobby", "trauma", "achievement"]
        
        for i in range(sample_size):
            memory_type = memory_types[i % len(memory_types)]
            memory = {
                "question": f"你能告诉我关于你的{memory_type}经历吗？",
                "answer": f"这是一个关于{memory_type}的模拟记忆。",
                "context": f"这是一个{memory_type}相关的上下文。",
                "type": memory_type
            }
            memories.append(memory)
        
        # 保存为JSON文件
        output_file = os.path.join(output_dir, "perltqa_mock.json")
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(memories, f, ensure_ascii=False, indent=2)
        
        print(f"模拟数据已保存到 {output_file}")
        print(f"共 {len(memories)} 条记忆")

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="下载并处理数据集")
    parser.add_argument("--output-dir", type=str, default="../data", help="输出目录")
    parser.add_argument("--sample-size", type=int, default=1000, help="样本大小")
    args = parser.parse_args()
    
    # 获取脚本所在目录
    script_dir = Path(__file__).parent.absolute()
    
    # 解析输出目录
    if args.output_dir.startswith("/"):
        output_dir = args.output_dir
    else:
        output_dir = os.path.join(script_dir, args.output_dir)
    
    # 创建输出目录
    os.makedirs(output_dir, exist_ok=True)
    
    # 下载数据集
    download_personahub(os.path.join(output_dir, "personas"), args.sample_size)
    download_perltqa(os.path.join(output_dir, "memories"), args.sample_size)

if __name__ == "__main__":
    main()
