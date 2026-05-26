import torch
import asyncio
import time
import threading
import os
from transformers import AutoModelForCausalLM, AutoTokenizer
from typing import List, Dict
from .config import LOCAL_MODEL_PATH, LORA_ADAPTER_PATH, USE_LORA

# 尝试导入 peft，用于加载 LoRA 适配器
try:
    from peft import PeftModel
    PEFT_AVAILABLE = True
except ImportError:
    PEFT_AVAILABLE = False
    print("警告: peft 库未安装，无法加载 LoRA 适配器。如需使用 LoRA，请执行: pip install peft")

# 全局模型缓存
_model = None
_tokenizer = None

# 线程锁 → 保证同一时间只有一次推理（防止 CUDA 崩溃）
_generate_lock = threading.Lock()

# 线程池执行器（可选，使用默认的 None 即可让 run_in_executor 自动分配）
_sync_executor = None


def load_model():
    """加载基础模型与分词器，并自动加载 LoRA 适配器（如果配置启用）"""
    global _model, _tokenizer
    if _model is None:
        model_path = os.path.abspath(LOCAL_MODEL_PATH)
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"模型路径不存在: {model_path}")
        print(f"加载基础模型: {model_path}")

        # 加载分词器
        _tokenizer = AutoTokenizer.from_pretrained(
            model_path,
            trust_remote_code=True,
            padding_side="left",
            local_files_only=True
        )
        if _tokenizer.pad_token is None:
            _tokenizer.pad_token = _tokenizer.eos_token

        # 设备自动选择
        if torch.cuda.is_available():
            device = "cuda"
            dtype = torch.float16
        else:
            device = "cpu"
            dtype = torch.float32

        # 加载基础模型
        _model = AutoModelForCausalLM.from_pretrained(
            model_path,
            torch_dtype=dtype,
            device_map="auto" if device == "cuda" else None,
            trust_remote_code=True,
            local_files_only=True
        )

        if device == "cpu":
            _model = _model.to(device)

        # ---------- 加载 LoRA 适配器 ----------
        if USE_LORA and LORA_ADAPTER_PATH and os.path.exists(LORA_ADAPTER_PATH):
            if not PEFT_AVAILABLE:
                raise ImportError("需要安装 peft 库才能加载 LoRA: pip install peft")
            print(f"正在加载 LoRA 适配器: {LORA_ADAPTER_PATH}")
            _model = PeftModel.from_pretrained(_model, LORA_ADAPTER_PATH)
            # 可选：合并 LoRA 权重以提升推理速度（会增加显存占用但提速）
            # _model = _model.merge_and_unload()
            print("LoRA 适配器加载完成")
        else:
            if USE_LORA:
                print(f"LoRA 路径不存在或未配置，跳过加载。路径: {LORA_ADAPTER_PATH}")
            else:
                print("未启用 LoRA，使用基础模型进行推理")
        # ------------------------------------

        print(f"模型加载完成，设备: {_model.device}")

    return _model, _tokenizer


def build_prompt(messages: List[Dict[str, str]]) -> str:
    """构建对话模板（兼容 tokenizer 的 chat_template，失败则回退到简单拼接）"""
    try:
        return _tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True
        )
    except Exception:
        prompt = ""
        for msg in messages:
            if msg["role"] == "system":
                prompt += f"System: {msg['content']}\n"
            elif msg["role"] == "user":
                prompt += f"User: {msg['content']}\n"
            else:
                prompt += f"Assistant: {msg['content']}\n"
        prompt += "Assistant: "
        return prompt


async def generate_response(
    messages,
    temperature=0.7,
    max_new_tokens=1024,
    top_p=0.9
):
    """
    异步生成回复，在线程池中运行同步推理，不阻塞事件循环。
    返回 (answer_text, elapsed_time_seconds)
    """
    model, tokenizer = load_model()
    prompt = build_prompt(messages)
    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)

    def _sync_infer():
        start = time.time()
        with _generate_lock:  # 防止多推理线程同时执行 CUDA 操作
            with torch.inference_mode():
                outputs = model.generate(
                    **inputs,
                    max_new_tokens=max_new_tokens,
                    temperature=temperature,
                    do_sample=temperature > 0,
                    top_p=top_p,
                    pad_token_id=tokenizer.pad_token_id,
                    eos_token_id=tokenizer.eos_token_id,
                    use_cache=True,
                    num_beams=1
                )
        # 解码输出（仅新生成的 token）
        generated = outputs[0][inputs.input_ids.shape[1]:].cpu()
        answer = tokenizer.decode(generated, skip_special_tokens=True)
        return answer.strip(), time.time() - start

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _sync_infer)