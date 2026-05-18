import os
import time
import json
import requests
import streamlit as st
import streamlit.components.v1 as components
from openai import AzureOpenAI
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
# Azure Cosmos DB 라이브러리 추가
from azure.cosmos import CosmosClient, PartitionKey
from azure.core.exceptions import AzureError

# 1. 페이지 레이아웃 및 제목 설정
st.set_page_config(page_title="FinAssist 금융 자문 에이전트", page_icon="💬", layout="wide")
st.title("FinAssist 금융/세무 전문 에이전트 (LTM 지원)")
st.caption("Azure OpenAI Agent + Azure AI Search 독립형 구성 & Azure Cosmos DB LTM 장기기억 연동")

def log_to_chrome_console(tag: str, message: str, level: str = "log"):
    safe_msg = json.dumps(f"[{tag}] {message}")
    components.html(f"<script>console.{level}({safe_msg});</script>", height=0, width=0)

# 2. 전역 환경 변수 로드
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_SEARCH_ENDPOINT = os.getenv("AZURE_SEARCH_ENDPOINT")
AZURE_SEARCH_INDEX = os.getenv("AZURE_SEARCH_INDEX")
AZURE_SEARCH_KEY = os.getenv("AZURE_SEARCH_KEY")

# Cosmos DB 연결 정보 (계정 URL은 finassist-ltm-db 기반으로 환경 변수 처리 권장)
COSMOS_ENDPOINT = os.getenv("AZURE_COSMOS_ENDPOINT")
COSMOS_DB_NAME = "financial-chatbot-db"
COSMOS_CONTAINER_NAME = "customer-memory"

# 3. Azure OpenAI & Cosmos DB 클라이언트 초기화 (DefaultAzureCredential 사용)
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

@st.cache_resource
def get_cosmos_container():
    try:
        # 기존에 완벽히 인증에 성공했던 OpenAI용 토큰을 그대로 셰어링합니다.
        local_token = os.getenv("COSMOS_BEARER_TOKEN")

        if local_token:
            class TokenCredentialStub:
                def get_token(self, *scopes, **kwargs):
                    return type('Token', (object,), {
                        "token": local_token,
                        "expires_on": int(time.time()) + 3600
                    })()
            
            client = CosmosClient(COSMOS_ENDPOINT, credential=TokenCredentialStub())
        else:
            credential = DefaultAzureCredential()
            client = CosmosClient(COSMOS_ENDPOINT, credential=credential)

        database = client.get_database_client(COSMOS_DB_NAME)
        container = database.get_container_client(COSMOS_CONTAINER_NAME)
        
        # ⚠️ 만약 토넌트 스코프 문제로 거부 반응이 일어나면 아래 검증 줄을 잠시 주석 처리하세요.
        container.read()
        return container

    except Exception as e:
        st.error(f"Cosmos DB 초기화 실패: {e}")
        return None

client = get_openai_client()
cosmos_container = get_cosmos_container()

# [LTM 구현] Cosmos DB 장기 기억 관리 함수
def load_user_memory(customer_identifier: str) -> dict:
    """
    고객 식별자 기준으로 LTM 프로필 로드

    지원 입력:
    - customerId: 예) CUST0001
    - name: 예) 이준호

    Cosmos DB 구조:
    - id: C001
    - customerId: CUST0001   # Partition Key
    - name: 이준호
    """
    if not cosmos_container:
        return {
            "memories": [],
            "summary": "기억 데이터베이스 연결이 불가능합니다."
        }

    try:
        identifier = customer_identifier.strip()

        # 1. customerId로 들어온 경우, Partition Key 기반 Query
        if identifier.upper().startswith("CUST"):
            query = """
            SELECT TOP 1 * 
            FROM c 
            WHERE c.customerId = @customerId
            """
            parameters = [
                {"name": "@customerId", "value": identifier}
            ]

        # 2. 고객명으로 들어온 경우, name 기준 Cross Partition Query
        else:
            query = """
            SELECT TOP 1 * 
            FROM c 
            WHERE c.name = @name
            """
            parameters = [
                {"name": "@name", "value": identifier}
            ]

        items = list(cosmos_container.query_items(
            query=query,
            parameters=parameters,
            enable_cross_partition_query=True
        ))

        if not items:
            return {
                "id": identifier,
                "customerId": identifier,
                "name": identifier,
                "memories": [],
                "summary": "첫 방문 고객입니다."
            }

        item = items[0]

        # 기존 json 구조를 챗봇이 쓰기 쉬운 summary 형태로 보강
        item["summary"] = item.get("conversationSummary", "")
        item["memories"] = item.get("notes", [])

        return item

    except Exception as e:
        log_to_chrome_console("COSMOS_READ_ERR", str(e), level="error")
        return {
            "id": customer_identifier,
            "customerId": customer_identifier,
            "name": customer_identifier,
            "memories": [],
            "summary": "메모리를 가져오지 못했습니다."
        }

def save_user_memory(customer_id: str, new_user_msg: str, new_assistant_msg: str):
    """대화가 이루어질 때마다 Cosmos DB에 최신 상태와 대화 요약을 업데이트"""
    if not cosmos_container:
        return
    
    # 1. 기존 메모리 로드
    memory_data = load_user_memory(customer_id)
    
    # 2. 새로운 대화 이력 추가
    memory_data["memories"].append({
        "timestamp": time.time(),
        "user": new_user_msg,
        "assistant": new_assistant_msg
    })
    
    # 3. GPT를 활용한 점진적 요약(Memory Consolidation) 업데이트
    # 최근 5개의 대화 요약을 누적 유지하거나, 하나의 요약본을 계속 업데이트하도록 유도합니다.
    try:
        recent_context = "\n".join([f"유저: {m['user']}\n에이전트: {m['assistant']}" for m in memory_data["memories"][-3:]])
        summary_prompt = f"""다음은 고객({customer_id})의 기존 대화 요약과 최근 대화 이력입니다. 
이 정보를 바탕으로 고객의 투자 성향, 질문 성향, 재무적 특이사항이나 관심사를 요약하여 하나의 종합 문단으로 갱신해 주세요.

[기존 요약]: {memory_data.get('summary', '없음')}
[최근 대화]:
{recent_context}

종합 요약(한국어):"""
        
        response = client.chat.completions.create(
            model="gpt-5.4", # 또는 사용중인 다른 chat 모델 배포명
            messages=[{"role": "user", "content": summary_prompt}],
            temperature=0.3
        )
        memory_data["summary"] = response.choices[0].message.content.strip()
    except Exception as e:
        log_to_chrome_console("MEMORY_SUMMARY_ERR", str(e), level="error")
        # LLM 요약 실패 시 데이터 보존을 위해 과거 대화 텍스트 기반 기록 유지
        memory_data["summary"] = memory_data.get("summary", "요약 갱신 실패")

    # 4. Cosmos DB에 덮어쓰기 (Upsert)
    try:
        cosmos_container.upsert_item(body=memory_data)
        log_to_chrome_console("COSMOS_UPSERT", f"고객 {customer_id}의 LTM 데이터가 성공적으로 저장되었습니다.")
    except Exception as e:
        log_to_chrome_console("COSMOS_WRITE_ERR", str(e), level="error")

# [에이전트 툴] AI Search 연동 함수
def search_knowledge_base(query: str) -> str:
    headers = {
        "Content-Type": "application/json",
        "api-key": AZURE_SEARCH_KEY
    }
    url = f"{AZURE_SEARCH_ENDPOINT}/indexes/{AZURE_SEARCH_INDEX}/docs/search?api-version=2024-05-01-Preview"
    payload = {"search": query, "top": 3}
    
    log_to_chrome_console("AI_SEARCH_REQ", f"호출 URL: {url} | 쿼리: {query}")
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        if response.status_code == 200:
            results = response.json().get("value", [])
            documents = []
            for doc in results:
                text_content = doc.get("snippet") or doc.get("content") or doc.get("chunk") or ""
                if text_content:
                    documents.append(text_content)
            log_to_chrome_console("AI_SEARCH_RES", f"성공: {len(documents)}개의 문서 가공 완료.")
            return "\n\n--- 검색된 문서 분할 ---\n\n".join(documents) if documents else "관련 문서를 찾지 못했습니다."
        else:
            return f"검색 리소스 응답 에러 상태코드: {response.status_code}"
    except Exception as e:
        return f"검색 연동 엔진 런타임 예외 발생: {str(e)}"

# 4. UI 사이드바 - 사용자 ID(Partition Key) 입력기 추가
with st.sidebar:
    st.header("⚙️ 사용자 및 LTM 설정")
    customer_id = st.text_input("고객 식별자 (CustomerId / PartitionKey)", value="VIP-CUSTOMER-01")
    
    if st.button("장기 기억(LTM) 초기화/조회"):
        with st.spinner("Cosmos DB에서 데이터를 조회하는 중..."):
            user_mem = load_user_memory(customer_id)
            st.success(f"'{customer_id}' 데이터 로드 완료")
            st.subheader("🤖 데이터베이스에 기록된 유저 성향 요약")
            st.info(user_mem.get("summary", "기록된 요약이 없습니다."))
            with st.expander("과거 전체 대화 로그 보기"):
                st.json(user_mem.get("memories", []))

# 5. 에이전트 및 스레드 세션 관리
if "agent" not in st.session_state:
    st.session_state.agent = client.beta.assistants.create(
        name="FinAssist-Agent",
        # [LTM 주입] Instructions에 과거 장기 기억 맥락을 동적으로 매핑하기 위해 원본 가이드를 세션에 저장
        instructions="""당신은 금융/세무 전문 자문 에이전트입니다. 
사용자의 질문에 답하기 위해 제공된 search_knowledge_base 툴을 사용하여 정보를 검색해야 합니다.
[중요] search_knowledge_base를 호출할 때 query 인자값은 핵심 단어 1~2개만 요약한 핵심 키워드로만 전달하세요.
반드시 검색된 문서의 내용에만 기반하여 답변하고, 없는 정보는 지어내지 마세요.""",
        model="gpt-5.4",
        tools=[{
            "type": "function",
            "function": {
                "name": "search_knowledge_base",
                "description": "금융/세무 데이터베이스 검색 툴. 인자값 query에는 1~2개의 핵심 명사 키워드만 넣으십시오.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "검색할 핵심 단어 1~2개"}
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

# 기존 화면 메시지 렌더링
for msg in st.session_state.ui_messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# 6. 사용자 입력 및 에이전트 실행 컨트롤러
if user_input := st.chat_input("금융 또는 세무 관련 질문을 입력하세요..."):
    st.session_state.ui_messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant"):
        with st.spinner("에이전트가 생각하고 장기 기억을 분석하는 중..."):
            try:
                # 6-1. 대화 직전 Cosmos DB에서 유저의 장기 기억(Summary)을 읽어옵니다.
                user_mem = load_user_memory(customer_id)
                                
                ltm_summary = user_mem.get("summary", "이 고객에 대한 이전 대화 정보가 존재하지 않습니다.")
                
                # 6-2. 에이전트 지침(Instructions)에 유저 장기 기억 컨텍스트를 동적으로 결합하여 업데이트(Modify) 합니다.
                dynamic_instruction = f"""{st.session_state.agent.instructions}

[중요 - 대상 고객 정보 (Cosmos DB LTM 기록)]:
{ltm_summary}
위 내용을 참고하여 고객의 상태나 성향에 맞춤화된 전문적인 뉘앙스로 답변을 작성하십시오."""
                
                client.beta.assistants.update(
                    assistant_id=st.session_state.agent.id,
                    instructions=dynamic_instruction
                )

                # Thread에 유저 메시지 생성 및 Run 구동
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
                        
                        retry_count += 1
                        if retry_count > 5:
                            client.beta.threads.runs.cancel(thread_id=st.session_state.thread.id, run_id=run.id)
                            st.error("에이전트가 적절한 검색 키워드를 찾지 못해 중단되었습니다.")
                            break

                if run.status == "completed":
                    messages = client.beta.threads.messages.list(thread_id=st.session_state.thread.id)
                    assistant_response = messages.data[0].content[0].text.value
                    st.markdown(assistant_response)
                    
                    # UI 세션 상태 업데이트
                    st.session_state.ui_messages.append({"role": "assistant", "content": assistant_response})
                    
                    # 6-3. [LTM 백그라운드 동기화] 새로운 대화 이력을 축적하고 요약을 자동 업데이트하여 Cosmos DB에 저장
                    save_user_memory(customer_id, user_input, assistant_response)
                    
                elif run.status != "cancelled":
                    st.error(f"에이전트 실행이 비정상 종료되었습니다: {run.status}")

            except Exception as e:
                log_to_chrome_console("APP_EXCEPTION", str(e), level="error")
                st.error(f"에이전트 답변 생성 중 오류가 발생했습니다: {e}")