# Azure AI Workshop

## 2. Microsoft Foundry 프로젝트 구성

Microsoft Foundry 프로젝트를 생성하고 `gpt-5.4` 모델을 배포한 뒤, 금융 상담 지원용 `FinAssistAI` 에이전트를 구성합니다.

- Korea Central 리전에 `ai-workshop-rg` 리소스 그룹 및 Foundry 프로젝트 생성
- `gpt-5.4` 모델 배포 후 `FinAssistAI` 에이전트 생성
- 금융 상담 직원 지원 목적의 에이전트 지침 구성
- 정기예금, 글로벌 테크 성장 펀드, IRP 상담 시나리오 기반 테스트
- `products.json`, `policy_docs.json`, `faq.json`, `advisor_guide.json` 파일 업로드 기반 RAG 구성

---

## 3. Foundry IQ RAG 구성

Azure AI Search와 Blob Storage를 기반으로 Foundry IQ 지식 원본과 지식 기반을 구성하고, `FinAssistAI` 에이전트에 연결합니다.

- `text-embedding-3-large` 임베딩 모델 배포
- Azure AI Search 및 Blob Storage 기반 데이터 원본 구성
- Blob 컨테이너에 금융 상품, 약관, FAQ, 상담 가이드 데이터 업로드
- AI Search, Storage, Foundry 간 Managed Identity 및 RBAC 권한 설정
- Foundry IQ 지식 원본·지식 기반 생성 후 `FinAssistAI` 에이전트에 연결