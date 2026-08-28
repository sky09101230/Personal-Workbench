## ADDED Requirements

### Requirement: Literature-owned AI provider boundary
The system SHALL perform Literature AI requests through a Literature application service and replaceable provider port, with DeepSeek HTTP and credentials confined to Literature infrastructure.

#### Scenario: DeepSeek is configured
- **WHEN** a user triggers a Literature AI operation and the existing DeepSeek settings are configured
- **THEN** the backend sends the request without exposing credentials to the browser or importing News, Todo, or Activity code

#### Scenario: DeepSeek is not configured
- **WHEN** a user triggers a Literature AI operation without `DEEPSEEK_API_KEY`
- **THEN** the API returns a stable, understandable configuration error and sends no provider request

### Requirement: Versioned structured paper analyses
The system SHALL provide distinct, schema-validated AI Overview and Deep Read analyses and persist their paper id, analysis type, model, prompt version, content, and creation time.

#### Scenario: Generate Overview
- **WHEN** a user explicitly requests Overview for a paper with metadata or extractable context
- **THEN** the result contains the required Overview fields and records prompt version `overview_v1`

#### Scenario: Generate Deep Read
- **WHEN** a user explicitly requests Deep Read
- **THEN** the result uses the Deep Read schema and prompt `deep_read_v1` to analyze problem, method, assumptions, experiments, evidence, limitations, reproducibility, and unresolved questions

#### Scenario: Reuse persisted analysis
- **WHEN** an Overview or Deep Read already exists and the user has not requested regeneration
- **THEN** the backend returns the latest persisted analysis without another DeepSeek request

### Requirement: Page-level PDF context cache
The system SHALL extract normalized PDF text by page, persist page number and extractor version, and construct bounded representative contexts without OCR.

#### Scenario: Extract ordinary PDF
- **WHEN** a paper has an accessible PDF with a text layer
- **THEN** non-empty page text is cached and later requests reuse the cached pages

#### Scenario: Prefer the main paper over supplementary PDFs
- **WHEN** a paper has both a downloadable main PDF and filename-marked supplementary PDF attachments
- **THEN** the Reader and AI context use the main PDF by default

#### Scenario: Extract scanned PDF
- **WHEN** no PDF page contains extractable text
- **THEN** the system reports that PDF text extraction is unsupported and does not attempt OCR

#### Scenario: Build representative full-paper context
- **WHEN** Overview or Deep Read uses a long PDF
- **THEN** the context includes prioritized first, middle, and final pages within the task budget rather than only the first characters

### Requirement: Paper-bound Ask Paper conversations
The system SHALL persist conversations and messages under one paper and answer from bounded metadata, PDF chunks, and recent conversation context.

#### Scenario: Ask a supported question
- **WHEN** a user asks a question in a conversation bound to the current paper
- **THEN** lexical retrieval selects relevant chunks and the response separates paper evidence, AI interpretation, and uncertainty using `ask_paper_v1`

#### Scenario: Context is insufficient
- **WHEN** supplied paper context does not support an answer
- **THEN** the response states that the paper provides insufficient information instead of freely completing the claim

#### Scenario: Conversation belongs to another paper
- **WHEN** a conversation id is used under a different paper id
- **THEN** the API returns a resource-not-found error and does not disclose its messages

### Requirement: PDF selection actions
The system SHALL support explain, summarize, translate, and ask actions for selected PDF text using page-local neighboring context and optional user question.

#### Scenario: Explain a selection
- **WHEN** a user selects PDF text and chooses Explain
- **THEN** the request contains bounded selected and neighboring text, records `selection_explain_v1`, and does not include the full PDF

#### Scenario: Ask about a selection
- **WHEN** a user supplies a question with the Ask selection action
- **THEN** the result uses `selection_ask_v1` and remains grounded in the supplied selection context

#### Scenario: Selection request exceeds bounds
- **WHEN** selection or neighboring context exceeds the presentation contract limits
- **THEN** the API rejects the request before calling DeepSeek

### Requirement: Stable AI error handling
The system SHALL map provider, context, and resource failures to stable application errors without exposing raw provider content, stack traces, authorization headers, or API keys.

#### Scenario: Provider timeout or HTTP failure
- **WHEN** DeepSeek times out, rate limits, or returns a 4xx or 5xx response
- **THEN** the frontend receives an actionable stable error and can retry explicitly

#### Scenario: Provider returns invalid output
- **WHEN** DeepSeek returns malformed JSON or content that fails the expected schema
- **THEN** no invalid analysis or assistant message is persisted

### Requirement: Reader AI Assistant
The system SHALL add a collapsible AI Assistant to the existing PDF Reader with explicit triggers, loading, retry, error, copy, and Add to Notes controls.

#### Scenario: Open a paper
- **WHEN** the Reader loads a paper
- **THEN** it does not automatically call DeepSeek and it first displays any persisted Overview or Deep Read

#### Scenario: Select PDF text
- **WHEN** the rendered PDF text layer has a non-empty selection
- **THEN** the Reader exposes the four selection actions without blocking page navigation or PDF rendering
