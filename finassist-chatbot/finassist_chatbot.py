import os
import time
import json
import requests
import streamlit as st
import streamlit.components.v1 as components
from openai import AzureOpenAI
from azure.identity import DefaultAzureCredential, get_bearer_token_provider

# 1. 페이지 레이아웃 및 제목 설정
st.set_page_config(page_title="FinAssist 금융 자문 에이전트", page_icon="💬")
st.title("FinAssist 금융/세무 전문 에이전트")
st.caption("Azure OpenAI Agent (Tools) + Azure AI Search 독립형 구성")

def log_to_chrome_console(tag: str, message: str, level: str = "log"):
    safe_msg = json.dumps(f"[{tag}] {message}")
    components.html(f"<script>console.{level}({safe_msg});</script>", height=0, width=0)

# 2. 전역 환경 변수 로드
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_SEARCH_ENDPOINT = os.getenv("AZURE_SEARCH_ENDPOINT")
AZURE_SEARCH_INDEX = os.getenv("AZURE_SEARCH_INDEX")
AZURE_SEARCH_KEY = os.getenv("AZURE_SEARCH_KEY")

# 3. Azure OpenAI 클라이언트 초기화
@st.cache_resource
def get_openai_client():
    local_token = os.getenv("AZURE_BEARER_TOKEN")
    if local_token:
        token_provider = lambda: local_token
    else:
        credential = DefaultAzureCredential()
        token_provider = get_bearer_token_provider(credential, "https://cognitiveservices.azure.com/.default")
    return AzureOpenAI(
        azure_endpoint=AZURE_OPENAI_ENDPOINT,
        azure_ad_token_provider=token_provider,
        api_key="managed-identity-auth-no-key-required",
        api_version="2024-05-01-preview"
    )

client = get_openai_client()

# [에이전트 툴] snippet 필드를 읽도록 수정한 함수
def search_knowledge_base(query: str) -> str:
    headers = {
        "Content-Type": "application/json",
        "api-key": AZURE_SEARCH_KEY
    }
    url = f"{AZURE_SEARCH_ENDPOINT}/indexes/{AZURE_SEARCH_INDEX}/docs/search?api-version=2024-05-01-Preview"
    
    payload = {
        "search": query,
        "top": 3
    }
    
    log_to_chrome_console("AI_SEARCH_REQ", f"호출 URL: {url} | 쿼리: {query}")
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        
        if response.status_code == 200:
            results = response.json().get("value", [])
            documents = []
            for doc in results:
                # 분석된 로그에 기반하여 'snippet' 필드에서 텍스트를 우선 추출합니다.
                text_content = doc.get("snippet") or doc.get("content") or doc.get("chunk") or ""
                if text_content:
                    documents.append(text_content)
                    
            log_to_chrome_console("AI_SEARCH_RES", f"성공: {len(documents)}개의 문서 가공 완료.")
            return "\n\n--- 검색된 문서 분할 ---\n\n".join(documents) if documents else "관련 문서를 찾지 못했습니다. 다른 키워드로 다시 검색하세요."
        else:
            return f"검색 리소스 응답 에러 상태코드: {response.status_code}"
            
    except Exception as e:
        return f"검색 연동 엔진 런타임 예외 발생: {str(e)}"

# 4. 에이전트 및 스레드 세션 관리
if "agent" not in st.session_state:
    # 에이전트가 쿼리를 너무 길게 조합하지 못하도록 지침(Instructions)을 더 엄격하게 제한합니다.
    st.session_state.agent = client.beta.assistants.create(
        name="FinAssist-Agent",
        instructions="""당신은 금융/세무 전문 자문 에이전트입니다. 
사용자의 질문에 답하기 위해 제공된 search_knowledge_base 툴을 사용하여 정보를 검색해야 합니다.
[중요] search_knowledge_base를 호출할 때 query 인자값은 문장 형태나 긴 단어 조합이 아닌, '정기예금 중도해지'처럼 핵심 단어 1~2개만 요약한 핵심 키워드(단어 형태)로만 전달하세요.
반드시 검색된 문서의 내용에만 기반하여 답변하고, 없는 정보는 지어내지 마세요.""",
        model="gpt-5.4",
        tools=[{
            "type": "function",
            "function": {
                "name": "search_knowledge_base",
                # 3: 툴 설명에도 키워드 위주로 검색하라는 가이드를 주입합니다.
                "description": "금융/세무 자문 데이터베이스에서 정보를 검색합니다. 인자값 query에는 반드시 '중도해지', '정기예금'과 같이 공백으로 구분된 1~2개의 핵심 명사 키워드만 넣으십시오.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "검색할 핵심 단어 1~2개 (예: '정기예금 중도해지')"}
                    },
                    "required": ["query"]
                }
            }
        }]
    )

if "thread" not in st.session_state:
    st.session_state.thread = client.beta.threads.create()

if "ui_messages" not in st.session_state:
    st.session_state.ui_messages = []

for msg in st.session_state.ui_messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# 5. 사용자 입력 및 에이전트 실행 컨트롤러
if user_input := st.chat_input("금융 또는 세무 관련 질문을 입력하세요..."):
    st.session_state.ui_messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant"):
        with st.spinner("에이전트가 생각하고 도구를 실행하는 중..."):
            try:
                client.beta.threads.messages.create(
                    thread_id=st.session_state.thread.id,
                    role="user",
                    content=user_input
                )

                run = client.beta.threads.runs.create(
                    thread_id=st.session_state.thread.id,
                    assistant_id=st.session_state.agent.id
                )

                # 에이전트 상태 추적 루프
                retry_count = 0
                while run.status in ["queued", "in_progress", "requires_action"]:
                    time.sleep(0.5)
                    run = client.beta.threads.runs.retrieve(thread_id=st.session_state.thread.id, run_id=run.id)

                    if run.status == "requires_action":
                        tool_outputs = []
                        for tool_call in run.required_action.submit_tool_outputs.tool_calls:
                            if tool_call.function.name == "search_knowledge_base":
                                arguments = json.loads(tool_call.function.arguments)
                                search_result = search_knowledge_base(query=arguments.get("query"))
                                
                                tool_outputs.append({
                                    "tool_call_id": tool_call.id,
                                    "output": search_result
                                })
                        
                        run = client.beta.threads.runs.submit_tool_outputs(
                            thread_id=st.session_state.thread.id,
                            run_id=run.id,
                            tool_outputs=tool_outputs
                        )
                        
                        # 무한루프 방지 안전장치 추가 (동일한 런에서 툴 호출이 5회 이상 반복되면 끊음)
                        retry_count += 1
                        if retry_count > 5:
                            client.beta.threads.runs.cancel(thread_id=st.session_state.thread.id, run_id=run.id)
                            st.error("에이전트가 적절한 검색 키워드를 찾지 못해 답변 생성을 중단했습니다. 질문을 조금 더 구체적인 키워드로 입력해 보세요.")
                            break

                if run.status == "completed":
                    messages = client.beta.threads.messages.list(thread_id=st.session_state.thread.id)
                    assistant_response = messages.data[0].content[0].text.value
                    st.markdown(assistant_response)
                    st.session_state.ui_messages.append({"role": "assistant", "content": assistant_response})
                elif run.status != "cancelled":
                    st.error(f"에이전트 실행이 비정상 종료되었습니다: {run.status}")

            except Exception as e:
                log_to_chrome_console("APP_EXCEPTION", str(e), level="error")
                st.error(f"에이전트 답변 생성 중 오류가 발생했습니다: {e}")