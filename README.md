# Azure AI Workshop

## Microsoft Foundry 프로젝트 구성

Microsoft Foundry 프로젝트를 생성하고 `gpt-5.4` 모델을 배포한 뒤, 금융 상담 지원용 `FinAssistAI` 에이전트를 구성합니다.

- Korea Central 리전에 `ai-workshop-rg` 리소스 그룹 및 Foundry 프로젝트 생성
- `gpt-5.4` 모델 배포 후 `FinAssistAI` 에이전트 생성
- 금융 상담 직원 지원 목적의 에이전트 지침 구성
- 정기예금, 글로벌 테크 성장 펀드, IRP 상담 시나리오 기반 테스트
- `products.json`, `policy_docs.json`, `faq.json`, `advisor_guide.json` 파일 업로드 기반 RAG 구성

---

## Foundry IQ RAG 구성

Azure AI Search와 Blob Storage를 기반으로 Foundry IQ 지식 원본과 지식 기반을 구성하고, `FinAssistAI` 에이전트에 연결합니다.

- `text-embedding-3-large` 임베딩 모델 배포
- Azure AI Search 및 Blob Storage 기반 데이터 원본 구성
- Blob 컨테이너에 금융 상품, 약관, FAQ, 상담 가이드 데이터 업로드
- AI Search, Storage, Foundry 간 Managed Identity 및 RBAC 권한 설정
- Foundry IQ 지식 원본·지식 기반 생성 후 `FinAssistAI` 에이전트에 연결

---

## Container Apps에 챗봇 배포

Microsoft Foundry에서 구성한 `FinAssistAI` 에이전트와 Foundry IQ 기반 RAG 구성을 실제 챗봇 애플리케이션으로 배포합니다.  
챗봇 UI가 포함된 컨테이너 이미지를 Azure Container Registry에 등록하고, Azure Container Apps를 통해 서버리스 컨테이너 환경에서 실행합니다.

- Azure Container Registry 생성 및 챗봇 컨테이너 이미지 등록
- `finassist-chatbot` 이미지를 기반으로 Container Apps 생성
- 외부 접속을 위한 Ingress 설정 및 애플리케이션 URL 확인
- Azure OpenAI, Azure AI Search 연동을 위한 환경 변수 구성
- Container Apps의 Managed Identity 활성화
- Foundry 프로젝트 접근을 위한 `Cognitive Services 사용자` 권한 부여
- 배포된 챗봇 UI에서 금융 상담 RAG 시나리오 테스트

### 5. Long-term Memory 구성

Long-term Memory(LTM) 기반 사용자 메모리 저장 및 개인화 챗봇 구성

- Azure Cosmos DB 기반 사용자별 대화 이력 저장
- GPT 기반 Conversation Summary 및 Memory Consolidation 구현
- Azure Container Apps Managed Identity 기반 Cosmos DB 인증 구성
- Cosmos DB Native RBAC 기반 Data Access 제어
- 이전 대화 Context 기반 Personalized Response 구현
- 금융 상담 시나리오 기반 장기 메모리 챗봇 구성