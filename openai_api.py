import time
import requests
from dataclasses import dataclass

version = "1.0.0"

def log(message, level="INFO"):
    print(f"[{level}] {message}")

@dataclass
class OpenAIConfig:
    api_key: str
    base_url: str
    model1: str = "gpt-4o"
    prompt: str = "你是一个有帮助的AI助手。"

class OpenAIAPI:
    """
    OpenAI 标准接口封装类 (Chat Completions API)
    适配接口：/v1/chat/completions
    适配认证：Authorization: Bearer <API_KEY>
    """

    def __init__(self, config: OpenAIConfig):
        self.config = config
        self.current_model = config.model1
        self.api_key = config.api_key
        self.base_url = config.base_url.rstrip('/')

    def chat(self, message, model=None, prompt=None, history=None):
        if model is None:
            model = self.current_model
        if prompt is None:
            prompt = self.config.prompt

        # OpenAI 标准请求头
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": f"weixin-clawbot-openai/{version}"
        }

        # 构建 OpenAI 消息结构 (system 提示词作为 messages 的第一项)
        messages = []
        if prompt:
            messages.append({"role": "system", "content": prompt})
        
        if history:
            for h in history:
                # 兼容 bot.py 的历史格式：'self' 为 assistant，其他为 user
                role = "assistant" if h.get('attr') == 'self' else "user"
                messages.append({"role": role, "content": h.get('content', '')})
        
        messages.append({"role": "user", "content": message})

        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0.7,
        }

        api_endpoint = f"{self.base_url}/v1/chat/completions"
        
        # 梯度重试机制
        retry_delays = [2, 4, 8, 16, 32]
        max_retries = 5
        last_error = None

        for attempt in range(max_retries + 1):
            try:
                response = requests.post(api_endpoint, headers=headers, json=payload, timeout=60)
                response.raise_for_status()
                response.encoding = 'utf-8'
                response_data = response.json()

                # 解析 OpenAI 响应格式
                result = response_data['choices'][0]['message']['content']

                if attempt > 0:
                    log(message=f"OpenAI 第 {attempt} 次重试成功：{result[:50]}...")
                else:
                    log(message=f"OpenAI 返回成功：{result[:50]}...")
                return result

            except Exception as e:
                last_error = e
                if attempt < max_retries:
                    delay = retry_delays[attempt]
                    log(level="WARNING", message=f"OpenAI 接口第 {attempt + 1} 次失败（{type(e).__name__}），{delay}s 后重试...")
                    time.sleep(delay)
                else:
                    log(level="ERROR", message=f"OpenAI 已重试 {max_retries} 次，最终失败: {last_error}")

        return "AI接口暂时不可用，请稍后再试"
