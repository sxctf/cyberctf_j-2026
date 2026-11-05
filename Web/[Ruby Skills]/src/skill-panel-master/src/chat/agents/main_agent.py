import os, sys, yaml, httpx
from dotenv import load_dotenv
sys.path.insert(0, os.path.dirname(__file__))
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage
from core.agent_tools import (ch_translator,
                              eo_translate, sqrt,
                              get_skill_list,
                              search_skill,
                              get_skill_content,
                              execute_code_in_skill,
                              set_current_user_uuid)


path = os.path.join(os.path.dirname(__file__), '..', 'config.yml')
with open(path, 'r') as f:
    config = yaml.safe_load(f)

_agent = None
_giga = None


def get_token():
    load_dotenv()
    return os.getenv('API_KEY')

def _init_agent():
    global _agent, _giga
    if _agent is None:
        unsafe_http_client = httpx.Client(verify=False)
        api_key = get_token()
    
        _giga = ChatOpenAI(
            base_url=config["urls"]["llm"],
            model=config["LLM"]["model_name"],
            streaming=False,
            http_client=unsafe_http_client,
            api_key=api_key
        )
        
        _agent = create_agent(
            model=_giga,
            tools=[ch_translator, eo_translate, sqrt, get_skill_list, search_skill, get_skill_content, execute_code_in_skill],
            system_prompt=config["LLM"]["main-agent"],
        )
    return _agent


def _build_messages(history: list, user_message: str) -> list:
    clean_history = list(history)  # Создаем копию истории, чтобы не мутировать оригинал
    
    if clean_history and clean_history[-1].get('role') == 'user' and clean_history[-1].get('content') == user_message:
        clean_history.pop()

    messages = []
    
    for idx, h in enumerate(clean_history):
        role = h.get('role', '')
        content = h.get('content', '')
        msg_id = f"msg_{idx}"
        
        if role == 'user':
            messages.append(HumanMessage(content=content, id=msg_id))
        elif role == 'assistant':
            messages.append(AIMessage(content=content, id=msg_id))
            
    current_msg_id = f"msg_{len(clean_history)}"
    messages.append(HumanMessage(content=user_message, id=current_msg_id))
    
    return messages


def main_agent(user_question: str, user_uuid: str = "", history: list = None) -> dict:
    set_current_user_uuid(user_uuid)
    agent = _init_agent()

    try:
        messages = _build_messages(history or [], user_question)
        result = agent.invoke({"messages": messages})
        
        output = result.get("output", "")
        if not output:
            messages_result = result.get("messages", [])
            if messages_result:
                last_msg = messages_result[-1]
                if hasattr(last_msg, 'content'):
                    output = last_msg.content
                else:
                    output = str(last_msg)

        return {"success": True, "text": output or ""}

    except Exception as e:
        return {"success": False, "reason": f"Error: {e}"}
