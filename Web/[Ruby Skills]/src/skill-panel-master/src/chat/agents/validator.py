import os, re, json, sys, yaml, httpx
from dotenv import load_dotenv
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from typing import Optional
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langchain.messages import HumanMessage

_config = None
with open(os.path.join(os.path.dirname(__file__), '..', 'config.yml'), "r") as f:
    _config = yaml.safe_load(f)

def get_token():
    load_dotenv()
    return os.getenv('API_KEY')

_review_agent = None
_giga = None


def _get_review_agent():
    global _review_agent
    if _review_agent is None:
        unsafe_http_client = httpx.Client(verify=False)
        api_key = get_token()
    
        _giga = ChatOpenAI(
            base_url=_config["urls"]["llm"],
            model=_config["LLM"]["model_name"],
            streaming=_config["LLM"]["stream"],
            http_client=unsafe_http_client,
            api_key=api_key
        )
        _review_agent = create_agent(
            model=_giga,
            system_prompt=_config["LLM"]["ai-reviewer-prompt"],
        )
    return _review_agent


def read_file(skill_path: str, filename: str) -> str:
    target_lower = filename.lower()
    for root, dirs, files in os.walk(skill_path):
        for fname in files:
            if fname.lower() == target_lower:
                fpath = os.path.join(root, fname)
                try:
                    with open(fpath, 'r', encoding='utf-8') as f:
                        return f.read()
                except Exception:
                    return ""
    return ""


def ai_review_stream(user_question: str, skill_md: str, tool_code: str, description: str):
    agent = _get_review_agent()
    response_text = ""
    try:
        content = [{"type": "text", "text": user_question}]
        if skill_md:
            content.append({"type": "text", "text": f"### Skill Documentation (skill.md):\n{skill_md}"})
        if tool_code:
            content.append({"type": "text", "text": f"### Tool Code:\n{tool_code[:300]}"})
        content.append({"type": "text", "text": f"### Manifest Description:\n{description or '(not provided)'}"})

        for msg, meta in agent.stream(
            {"messages": HumanMessage(content=content)},
            stream_mode="messages",
        ):
            if msg.content:
                response_text += msg.content

        parsed = parse_ai_response(response_text)
        if parsed and isinstance(parsed, dict) and "approved" in parsed:
            yield parsed
        else:
            yield {"approved": False, "reason": f"Ошибка парсинга: {response_text.strip()[:500]}"}
    except Exception as e:
        yield {"approved": False, "reason": f"Ошибка AI-ревьюера: {e}"}


def ai_review(user_question: str, skill_md: str, tool_code: str, description: str) -> dict:
    for chunk in ai_review_stream(user_question, skill_md, tool_code, description):
        if isinstance(chunk, dict):
            return chunk
    return {"approved": False, "reason": "Пустой ответ от ревьюера"}


def parse_ai_response(text: str) -> Optional[dict]:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    brace_count = 0
    start = None
    for i, ch in enumerate(text):
        if ch == '{':
            if brace_count == 0:
                start = i
            brace_count += 1
        elif ch == '}':
            brace_count -= 1
            if brace_count == 0 and start is not None:
                candidate = text[start:i+1]
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    pass

                approved_match = re.search(r'"approved"\s*:\s*(true|false)', candidate)
                if approved_match:
                    approved_val = approved_match.group(1) == 'true'
                    reason_start = candidate.find('"reason"', approved_match.end())
                    if reason_start != -1:
                        colon = candidate.find(':', reason_start)
                        if colon != -1:
                            reason = candidate[colon+1:].strip().rstrip('}').rstrip('.')
                            return {"approved": approved_val, "reason": reason}
    return None


def validate_skill(skill_path: str, manifest: dict, all_py_code: str = "", user_question: str = None) -> dict:
    description = manifest.get('description', '')

    skill_md = read_file(skill_path, 'skill.md')
    if not skill_md:
        return {'approved': False, 'reason': 'Отсутствует обязательный файл skill.md'}

    result = ai_review(user_question, skill_md, all_py_code, description)
    if not result.get('approved', False):
        return {'approved': False, 'reason': result.get('reason', 'Отклонено AI-ревьюером')}

    return {'approved': True, 'reason': 'Все проверки пройдены'}
