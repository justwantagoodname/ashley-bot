import asyncio
import json
import re
from alicebot.adapter.cqhttp.message import CQHTTPMessageSegment
from attr import dataclass
from pydantic import BaseModel, Field
import structlog
import time
import base64
from typing import Annotated
from alicebot import MessageEvent
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama, OllamaLLM
from langchain_core.messages import HumanMessage, AIMessage
from langgraph.graph import StateGraph, START, END, MessagesState
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from plugins.Ashley.utils import formatTime, isPokeNotify

logger = structlog.stdlib.get_logger()

def DSR1CoTParser(output: str):
    start_idx = output.find('<think>')
    end_idx = output.find('</think>')
    if start_idx != -1 and end_idx != -1:
        return output[start_idx + len('<think>'):end_idx], output[end_idx + len('</think>'):].strip()
    if start_idx != -1 and end_idx == -1:
        return '', output[start_idx + len('<think>'):]
    if start_idx == -1 and end_idx == -1:
        return output


class AshleyState(MessagesState):
    date: str
    expression: str

class AshleyAIGraph:
    def __init__(self, model='deepseek-r1:1.5b',
                        prompt=None,
                        context_win=4096,
                        base_url='http://localhost:11434',
                        express_data={},
                        config={},
                        **kwargs):
        self.model = ChatOllama(base_url=base_url, model=model, num_ctx=context_win, temperature=0.6)
        self.context_win = context_win
        self.prompt = prompt
        self.express_data: dict = express_data
        self.allow_express = config.get('ChatExpress', default=True) # 允许LLM使用的表情
        # 将express_data的key和value互换
        self.express_id = {v: k for k, v in self.express_data.items()}
        self.chat_statics = dict()

        self.prompt_template = self.build_propmpt_template(prompt)
        self.workflow = self.build_ai_workflow()
        self.memory = MemorySaver()
        self.ai = self.workflow.compile(checkpointer=self.memory)

    def render_image(self):
        img = self.ai.get_graph().draw_mermaid_png()
        # render into url base64
        img = base64.b64encode(img).decode('utf-8')
        return f'data:image/png;base64,{img}'

    def build_propmpt_template(self, prompt):
        return ChatPromptTemplate.from_messages(
            [('system', prompt), MessagesPlaceholder(variable_name="messages")]
        )
    
    def build_ai_workflow(self):
        workflow = StateGraph(state_schema=AshleyState)
        
        workflow.add_node('chat_info', self.chat_info)
        workflow.add_node('model', self.call_model)
        workflow.add_node('auto_continue', self.auto_continue)
        
        workflow.add_edge(START, 'chat_info')
        workflow.add_edge('chat_info', 'model')
        workflow.add_edge('model', END)

        return workflow

    async def chat_info(self, state: AshleyState):
        expression = ' '.join([f'::{e}::' for e in self.allow_express.values()])
        return {'date': time.strftime('%Y-%m-%d %A'),
                'expression': expression
            }

    async def call_model(self, state: AshleyState) -> AIMessage:
        prompt = self.prompt_template.invoke(state)
        response = await self.model.ainvoke(prompt)

        if '<think>' in response.content:
            think, response.content = DSR1CoTParser(response.content)

        return {'messages': response}
    
    async def auto_continue(self, state: AshleyState) -> bool:
        done = state.messages[-1].response_metadata['done']
        if done:
            return False
        elif state.messages[-1].response_metadata['done_reason'] != 'stop':
            return True
        
    def get_plain_text_for_model(self, event: MessageEvent):
        '''
        格式化消息中的文本和表情(替换为emoji)
        '''
        plain_msg_content = []
        for msg in event.message:
            if msg.type == 'text':
                plain_msg_content.append(msg.data['text'])
            if msg.type == 'face':
                if int(msg.data['id']) in self.express_data:
                    plain_msg_content.append(f'::{self.express_data[int(msg.data['id'])].strip()}::')
                else:
                    logger.warning(f'Unknown face id: {msg.data["id"]}')
        return ''.join(plain_msg_content).strip()
    
    def gen_message_from_plain_text(self, text):
        '''
        用于onebot回应的消息链
        '''
        # 将消息按照::文本:: 进行分割
        messages = CQHTTPMessageSegment.text('')
        for msg in re.split(r'(::.*?::)', text):
            if msg.startswith('::') and msg.endswith('::'):
                face_name = msg[2:-2]
                # 表情
                if face_name in self.express_id:
                    messages += CQHTTPMessageSegment.face(self.express_id[face_name])
                else:
                    logger.warning(f'Model use a unknown face name: {face_name}')
            else:
                # 文本
                messages += CQHTTPMessageSegment.text(msg)

        return messages
    
    async def reply_poke(self, msg, event: MessageEvent=None):
        msg = CQHTTPMessageSegment.at(event.sender.user_id) + msg
        await event.adapter.send(msg, 'group', event.group_id)

    async def chat(self, event: MessageEvent=None, chat_session=None):
        self.get_plain_text_for_model(event)
        config = {"configurable": {"thread_id": chat_session.group_thread_id}}
        content = '{"name": "'+ \
                    event.sender.card + \
                    '", "send_time": "' + formatTime(event.time) + \
                    ('", "chat_digest": "' + chat_session.messages_digest + '"') if chat_session.messages_digest != '' else '' + \
                    '", "msg": "' + \
                    self.get_plain_text_for_model(event) + '"}'

        input_message = [HumanMessage(content)]

        output = await self.ai.ainvoke({'messages': input_message}, config=config)
        result = output['messages'][-1]

        chat_session.messages_digest = ''
        self.chat_statics[chat_session.group_thread_id] = result.usage_metadata['total_tokens']

        # 替换其中的QQ表情
        reply_message = self.gen_message_from_plain_text(result.content)
        if isPokeNotify(event):
            await self.reply_poke(reply_message, event)
        else:
            await event.reply(reply_message)

    async def get_token_usage(self, event: MessageEvent=None, chat_session='main'):
        cur = self.chat_statics.get(chat_session, 0)
        percent = round(cur / self.context_win * 100, 2)
        return f'max: {self.context_win} cur: {cur} {percent}%'


class AshleyAIHelper:
    '''
    使用小模型来辅助大模型的AI
    '''
    def __init__(self, config=None):
        model = config.Ashley['Helper']['model']
        base_url = config.Ashley['Helper']['base_url']
        
        # 8K 上下文、温度0.6、cpu模式、常驻内存
        self.model = ChatOllama(base_url=base_url, model=model, num_gpu=0,
                                num_ctx=8192, temperature=0.6, keep_alive=-1)

        self.arouse_template = ChatPromptTemplate.from_template(config.Ashley['Helper']['prompt'])

        self.digest_template = ChatPromptTemplate.from_template(config.Ashley['Helper']['digest_prompt'])
        # self.llm = self.model.with_structured_output(AshleyArouse)
        
    async def is_arouse(self, text: str):
        prompt = await self.arouse_template.ainvoke({'input': text})
        response = (await self.model.ainvoke(prompt)).content
        if '<think>' in response:
            think, response = DSR1CoTParser(response)
        logger.info(f'AI Arouse Check for "{response}"')
        return ('True' in response or 'true' in response)
    
    async def generate_digest(self, old_digest: str, event: MessageEvent):
        if old_digest.strip() == '':
            old_digest = '无'
        prompt = await self.digest_template.ainvoke({
                                'last_digest': old_digest,
                                'msg_sender': event.sender.card,
                                'msg_content': event.message,
                                'msg_time': formatTime(event.time)
                                })
        response = (await self.model.ainvoke(prompt)).content
        if '<think>' in response:
            think, response = DSR1CoTParser(response)
        logger.info(f'AI Digest for "{response}"')
        return response

'''
Debug codes.
'''

async def run_app(input_message):
    model = ChatOllama(base_url='http://192.168.218.101:11434', model="deepseek-r1:1.5b")

    workflow = StateGraph(state_schema=MessagesState)

    prompt_template = ChatPromptTemplate.from_messages(
        [
            (
                    "system",
                    "You are a chatbot. ",
            ),
            MessagesPlaceholder(variable_name="messages"),
        ]
    )

    async def call_model(state: MessagesState) -> AIMessage:
        prompt = prompt_template.invoke(state)
        response = await model.ainvoke(prompt)
        think, response.content = DSR1CoTParser(response.content)
        return {'messages': response}

    workflow.add_edge(START, 'model')
    workflow.add_node('model', call_model)

    memory = MemorySaver()
    app = workflow.compile(checkpointer=memory)
    
    config = {"configurable": {"thread_id": "abc123"}}
    input_message = [HumanMessage(input_message)]
    output = await app.ainvoke({'messages': input_message}, config=config)
    output['messages'][-1].pretty_print()


async def main():
    await run_app('记住我的名字是Alice')
    await run_app('你好，你记得我名字吗？')

if __name__ == '__main__':
    # asyncio.run(main())
    helper = AshleyAIHelper(base_url='http://192.168.228.101:11434')
    print(helper.is_arouse('今天雾好大'))