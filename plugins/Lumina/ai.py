import asyncio
import base64
import io
import logging
import re
import time

import alicebot.bot
from PIL import Image, PngImagePlugin
from alicebot import MessageEvent
from alicebot.adapter.cqhttp import CQHTTPMessageSegment
from langchain_openai import ChatOpenAI
import os
import json
from pathlib import Path
import requests

from plugins.Lumina.utils import convert_message, generate_random_string
from plugins.Lumina.tables import express_summon_data
import webuiapi


class LuminaChatApi:
    def __init__(self, model='deepseek-chat', prompt=None, context_win=4096, **kwargs):
        self.prompt = prompt
        self.deepseek_api_key = os.getenv('DEEPSEEK_API_KEY')
        self.model = model

        # DeepSeek大模型API配置
        self.llm = ChatOpenAI(
            temperature=0.95,
            model="deepseek-chat",
            openai_api_key=self.deepseek_api_key,
            openai_api_base="https://api.deepseek.com"
        )

        self.message = [{"role": "system", "content": prompt}]

    async def invoke(self, input):
        input = str(input)

        try:
            self.message.append({"role": "user", "content": input})
            response = await self.llm.ainvoke(self.message)
        except json.JSONDecodeError as e:
            print(f"本次对话无法连接到deepseek-chat")
            self.message.pop()
            return {"respond": "呜喵……网络信号好像被小老鼠咬断啦！(｡•́︿•̀｡) 猫娘正在努力用爪爪修复连接……请稍等一下下喵～", "error": e}

        try:
            ans = response.content
            ans = re.search(r'```json([\s\S]*)```', ans, re.M | re.I).group(1)
            respond = json.loads(ans)
        except AttributeError as e:
            print(f"输出非json串: {response.content}")
            self.message.append({"role": "assistant", "content": response.content})
            return {"respond": response.content, "error": e}
        except json.JSONDecodeError as e:
            print(f"解析失败: {response.content}")
            return {"respond": "喵喵喵？ฅ(´•ω•`ฅ) 猫娘核心突然过热……尾巴短路啦！(>_<) 请、请用小鱼干轻轻戳戳屏幕重启喵——！", "error": e}
        else:
            self.message.append({"role": "assistant", "content": respond["respond"]})
            return respond

    async def chat(self, event: MessageEvent):
        input_message = convert_message(event.message)

        output = await self.invoke({'messages': input_message,
                                    "sender_id": event.sender.user_id,
                                    "sender_name": event.sender.card
                                    if event.sender.card != ""
                                    else event.sender.nickname})
        if "express" in output:
            print(f"表情值：{output['express_value']}，正在准备发送表情：{output['express']}")
            msg = await send_express(output["express"])
            await event.reply(msg)

        await event.reply(output["respond"])


async def send_express(name):
    # 获取插件目录路径
    plugin_dir = Path(__file__).parent

    # 构建安全路径
    safe_path = (plugin_dir / "expresses" / f"{name}.png").resolve()

    # 验证文件是否存在
    if not safe_path.exists():
        # 进入生成流程
        # task = generate_random_string(15)
        # url = "http://127.0.0.1:7860/queue/join?__theme=dark"
        #
        # data = express_summon_data_for_old
        # data["data"][0] = f"task({task})"
        # data["data"][1] += f"({name}:1.2)"
        #
        # try:
        #     # 发送 POST 请求
        #     response = requests.post(
        #         url,
        #         json=data,
        #         timeout=5
        #     )
        #
        #     print(f"session_hash: {data['session_hash']}")
        #     print(f"响应内容: {response.text}")
        pass
        # 进入sd-webui生成流程
        print(f"开始生成表情图片文件：{safe_path.name}")
        try:
            url = "http://127.0.0.1:7860"
            payload = express_summon_data
            payload["prompt"] += f"({name}:1.2)"
            response = requests.post(url=f'{url}/sdapi/v1/txt2img', json=payload)

            r = response.json()
            for i in r['images']:
                image = Image.open(io.BytesIO(base64.b64decode(i.split(",", 1)[0])))

            image.save(safe_path)

        except requests.exceptions.ConnectionError:
            print("无法连接到sdweb-ui服务，请检查端口和地址")

    # 发送
    msg = CQHTTPMessageSegment.image(str(safe_path))
    return msg


if __name__ == "__main__":
    asyncio.run(send_express("no"))
