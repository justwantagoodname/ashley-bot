import asyncio
import time
import base64
from typing import Annotated
from alicebot import MessageEvent
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, AIMessage
from langgraph.graph import StateGraph, START, END, MessagesState
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

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

class AshleyAIGraph:
    def __init__(self, model='deepseek-r1:1.5b', prompt=None, context_win=4096, **kwargs):
        self.model = ChatOllama(model=model, num_ctx=context_win)
        self.context_win = context_win
        self.prompt = prompt
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
        
        workflow.add_node('current_date', self.current_date)
        workflow.add_node('model', self.call_model)
        workflow.add_node('auto_continue', self.auto_continue)
        
        workflow.add_edge(START, 'current_date')
        workflow.add_edge('current_date', 'model')
        workflow.add_edge('model', END)

        return workflow

    async def current_date(self, state: AshleyState) -> str:
        return {'date': time.strftime('%Y-%m-%d %A')}

    async def call_model(self, state: AshleyState) -> AIMessage:
        prompt = self.prompt_template.invoke(state)
        response = await self.model.ainvoke(prompt)
        think, response.content = DSR1CoTParser(response.content)
        return {'messages': response}
    
    async def auto_continue(self, state: AshleyState) -> bool:
        done = state.messages[-1].response_metadata['done']
        if done:
            return False
        elif state.messages[-1].response_metadata['done_reason'] != 'stop':
            return True

    async def chat(self, event: MessageEvent=None, chat_session='main'):
        config = {"configurable": {"thread_id": chat_session}}
        input_message = [HumanMessage(f'<name>{event.sender.card}</name><msg>{event.get_plain_text()}</msg>')]

        output = await self.ai.ainvoke({'messages': input_message}, config=config)
        result = output['messages'][-1]
        self.chat_statics[chat_session] = result.usage_metadata['total_tokens']
        await event.reply(result.content)

    async def get_token_usage(self, event: MessageEvent=None, chat_session='main'):
        cur = self.chat_statics.get(chat_session, 0)
        percent = round(cur / self.context_win * 100, 2)
        return f'max: {self.context_win} cur: {cur} {percent}%'


'''
Debug codes.
'''

async def run_app(input_message):
    model = ChatOllama(model="deepseek-r1:1.5b")

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

    workflow.add_edge(START, 'model')
    workflow.add_node('model', call_model)

    memory = MemorySaver()
    app = workflow.compile(checkpointer=memory)


    async def call_model(state: MessagesState) -> AIMessage:
        prompt = prompt_template.invoke(state)
        response = await model.ainvoke(prompt)
        think, response.content = DSR1CoTParser(response.content)
        return {'messages': response}
    
    config = {"configurable": {"thread_id": "abc123"}}
    input_message = [HumanMessage(input_message)]
    output = await app.ainvoke({'messages': input_message}, config=config)
    output['messages'][-1].pretty_print()


async def main():
    await run_app('记住我的名字是Alice')
    await run_app('你好，你记得我名字吗？')

if __name__ == '__main__':
    asyncio.run(main())