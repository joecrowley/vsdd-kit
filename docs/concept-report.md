Elevating Spec-Driven Development in Flutter: Integrating LLM-Generated Diagrams and Archival Workflows within OpenSpec

The integration of Large Language Models (LLMs) into software engineering has initiated a paradigm shift from ad-hoc code generation—often pejoratively termed "vibe coding"—to structured, intent-based engineering. Spec-Driven Development (SDD) frameworks, with OpenSpec at the forefront, formalize this process by establishing a rigorous specification layer between human intent and artificial intelligence execution. For development teams operating within the Flutter and Dart ecosystems, which frequently span mobile clients, web applications, and backend infrastructure, the purely textual nature of traditional SDD presents a distinct limitation. Complex state transitions within Riverpod, asynchronous isolate communication, and intricate GoRouter navigation paths demand visual representation to be fully comprehended.

This report provides an exhaustive architectural blueprint for extending the OpenSpec framework to seamlessly support LLM-generated Mermaid diagrams. It details the mechanisms for generating sequence, timing, and flow diagrams, establishing "Before and After" state visualizations, and managing the storage, update, and archival lifecycle of these visual artifacts. Furthermore, it explores the configuration of the underlying multi-agent systems via AGENTS.md and custom schema definitions, ensuring the system remains token-efficient. The analysis is designed to serve as both a comprehensive implementation guide for engineering leadership and a foundational narrative for presenting this paradigm shift to a large development organization.

The Paradigm of Spec-Driven Development and the Visual Gap

To effectively integrate visual diagrams into OpenSpec, it is imperative to first deconstruct the philosophy of the framework itself. OpenSpec operates on the dual principles of the "living specification" and "delta tracking".

Unlike conventional documentation tools or frameworks like GitHub Spec Kit that generate disposable, feature-isolated documents, OpenSpec maintains a central source of truth. This source of truth, typically located in an openspec/specs/ directory, represents the entirety of the system's current behavior and requirements. When a developer initiates a modification, the framework creates a localized change directory containing a proposal, design documents, and "delta specs." These delta specs explicitly categorize requirements into ADDED, MODIFIED, and REMOVED sections, forcing the AI and the developer to reason about the exact scope of the change. Upon completion, an archive operation intelligently merges these deltas back into the main living specification while permanently storing the historical record of the change.

A critical vulnerability in traditional software documentation, however, is "diagram drift." This phenomenon occurs when architectural diagrams become stale the moment a pull request alters the underlying codebase, rendering the documentation untrustworthy and obsolete. While text-based specifications can be incrementally updated via OpenSpec's delta tracking, manual diagramming tools rely entirely on human memory and effort for synchronization.

By utilizing LLMs to generate text-based diagramming languages such as Mermaid, organizations can transition to a "diagrams-as-code" methodology. Because Mermaid is defined via plain, declarative text, it integrates flawlessly into the OpenSpec delta-tracking lifecycle. If a pull request modifies an infrastructure flow or a Flutter state transition, the LLM can simultaneously update the Mermaid syntax within the delta spec, ensuring the visual representation remains tightly coupled to the implementation.

Architectural Strategy: Storage, Updates, and Historical Relevance

A core requirement of an advanced SDD pipeline is determining precisely where visual artifacts are stored, how they are updated, and how their historical context is preserved. Integrating "Before and After" diagrams requires a careful and deliberate orchestration of the OpenSpec file structure to ensure documentation remains relevant without overwhelming the developer.

The system must map diagram artifacts to the three distinct lifecycles of the OpenSpec framework: the current state (Source of Truth), the proposed state (Delta), and the historical record (Archive).

The Source of Truth represents the system as it currently exists in production. These artifacts are stored in the openspec/specs/[domain]/ directory, where domains correspond to bounded contexts such as auth/, payments/, or navigation/. Within these domain folders, a dedicated diagrams.md file houses the current, canonical Mermaid diagrams for the system. For a Flutter application, this might include the global Riverpod state machine, the GoRouter navigation tree, and the backend gRPC communication flow. These diagrams represent the "Before" state when a new feature is initiated.

When a new workflow is triggered via the /opsx:new command, an isolated active change directory is created, typically at openspec/changes/[feature-name]/. Within this workspace, the AI agent is instructed to read the Source of Truth and generate two sets of diagrams within the active design artifact. The first is the "Before Diagram," which is a direct snapshot of the relevant architecture prior to the change. The second is the "After Diagram," representing the proposed visual state incorporating the new feature or infrastructure modification. These files exist as interim, highly localized documents that allow engineers to visually review the architectural impact before a single line of Dart code is written.

To facilitate parallel development without merge conflicts, this active change process can be combined with Git WorkTrees. Git WorkTrees allow developers to check out multiple branches simultaneously in separate directories. By isolating each /opsx:new change in its own worktree alongside the main branch, multiple feature developments can proceed concurrently. Each isolated environment maintains its own "Before and After" state, which is independently verified before merging.

The final phase of the lifecycle is the Historical Archive. Upon executing the /opsx:archive command, the framework finalizes the change. The "After" Mermaid syntax from the active change directory is intelligently merged into the main openspec/specs/[domain]/diagrams.md file, overwriting the outdated sections and becoming the new Source of Truth. Simultaneously, the entire active change folder—including the OpenSpec proposal, the original "Before" diagram, the delta specs, the design document, and the rationale—is moved to an immutable archive directory, formatted as openspec/changes/archive/[date]-[feature-name]/.

This specific architecture guarantees that the root specifications remain relevant, accurate, and uncluttered, while the archive/ directory serves as an append-only ledger. Future developers, or the AI agents themselves, can traverse this archive to visually understand exactly how and why a system's architecture evolved over time, preserving institutional memory.

Customizing the OpenSpec Schema for Visual Artifacts

To enforce the generation of Mermaid diagrams and integrate them into the lifecycle, the default OpenSpec workflow must be fundamentally modified. OpenSpec relies on Directed Acyclic Graphs (DAGs) defined in schema files to determine the exact order, dependencies, and requirements of generated artifacts. The default spec-driven schema follows a strict linear pipeline: proposal -> specs -> design -> tasks.

To natively support visual generation, an organization must define a custom schema. This involves creating or modifying the openspec/config.yaml file to set a new default schema and define a custom artifact graph. This customization allows the injection of project-specific context—such as defining the tech stack as Flutter, Riverpod, and GoRouter—directly into the AI's prompt for every artifact.

The implementation requires extending the configuration to define a custom artifact lifecycle. Using the command openspec schema fork spec-driven visual-driven, a team can create a new localized schema that modifies the DAG to prioritize diagrams.

Table 1: Custom Schema Artifact Definitions for Visual SDD

Artifact ID	File Generated	Dependencies	LLM Instruction Purpose & Context
proposal	proposal.md	None	Elicit intent, scope, and explicitly identify affected Flutter/Dart domains.
diagrams	diagrams.md	[proposal]	Generate Mermaid sequenceDiagram, stateDiagram-v2, or flowchart explicitly detailing the Before and After states.
specs	specs/	[diagrams]	Generate ADDED/MODIFIED/REMOVED text requirements mapped directly to the visual nodes established in the diagrams.
design	design.md	[specs]	Document structural architectural decisions, API contracts, and database migrations.
tasks	tasks.md	[design]	Generate actionable, check-boxed implementation steps for the AI coder agent.

By strategically placing the diagrams artifact before specs and design, the LLM is forced to visually reason about the system's state transitions and data flows before attempting to write granular code-level requirements. This constraint significantly reduces hallucination and logical contradictions during the subsequent coding phase. Research into structure-guided code generation, such as the StructGen framework, demonstrates that employing UML or similar diagrams as structural guidance before code generation increases LLM accuracy and requirement adherence by 9.4% to 37.3%.

The templates associated with this custom schema must provide explicit, unyielding instructions to the LLM. The markdown template for the diagrams.md artifact must mandate the inclusion of specific headers, such as ## Before State and ## After State, followed by Mermaid code blocks. It should also include advisory preferences, dictating that sequence diagrams must be used for navigation flows and state diagrams must be used for Riverpod transitions.

Governing Multi-Agent Context via AGENTS.md

As organizations integrate sophisticated AI coding assistants—whether Claude Code, Cursor, or GitHub Copilot—into the OpenSpec workflow, governing the behavior of these agents becomes a critical engineering challenge. The AGENTS.md file is an open specification and a cross-tool standard that acts as a machine-readable README, providing explicit context, boundaries, and formatting rules to the LLM.

However, LLMs possess finite context windows, and there is a documented performance degradation when these windows are polluted with excessive or irrelevant instructions. Overloading the AGENTS.md file with exhaustive Mermaid syntax rules, Flutter boilerplate, and architectural treatises degrades reasoning performance, increases token costs, and leads to instruction hallucination. Studies on agent performance indicate that auto-generated or overly verbose context files can actually reduce task success while increasing token costs by up to 23%. Furthermore, tools like OpenAI's Codex enforce a strict 32 KiB size limit on AGENTS.md, silently truncating any overflow.

To support complex Mermaid diagram generation without polluting the global context, the AGENTS.md file must utilize a strategy known as "progressive disclosure". Rather than pasting all syntax rules into the root document, the root AGENTS.md should serve as a lightweight index that dynamically routes the agent to domain-specific skill files based on the task at hand.

The root file should remain under 150 lines—ideally between 30 and 50 lines for high efficiency—and contain only universally applicable project invariants. For a full-stack Dart and Flutter ecosystem utilizing OpenSpec and Mermaid, the structure should begin with a single-sentence project description that acts as a role-based prompt. This is followed by explicit commands instructing the agent to strictly follow the /opsx lifecycle commands and respect delta tracking.

The core of the progressive disclosure strategy is the orientation table. This markdown table acts as a directory, instructing the agent on where to fetch additional context when a specific domain is triggered.

Table 2: Agent Orientation and Progressive Disclosure Routing

Engineering Domain	Trigger Condition	Target Document to Read
Diagram Generation	When drafting diagrams.md or analyzing architecture	docs/MERMAID_RULES.md
State Management	When implementing or testing Riverpod providers	docs/RIVERPOD_RULES.md
Navigation Routing	When implementing GoRouter navigation paths	docs/ROUTING_RULES.md
Backend Infrastructure	When modifying server APIs or database schemas	docs/INFRA_RULES.md

This hierarchical approach ensures that the agent only loads the extensive Mermaid syntax constraints when it is actively tasked with generating a diagram. Once it moves to the tasks.md or implementation phase, it drops the Mermaid context and loads the Riverpod or GoRouter context, thereby preserving its vital attention budget for the actual coding tasks.

Mitigating LLM Hallucination in Diagram Syntax

Empirical research into LLM capabilities, specifically the MermaidSeqBench evaluation, reveals critical limitations in how language models handle diagramming syntax. While modern models (such as Qwen 2.5, Llama 3.1, and GPT-4 variants) are proficient at generating standard Mermaid structure, they frequently struggle with complex control flows, activation handling, and specific participant stereotyping. LLMs often generate invalid syntax that fails to render, leading to broken documentation and failing CI pipelines.

To aggressively mitigate this, the dynamically loaded docs/MERMAID_RULES.md file must explicitly restrict the LLM to verified syntax subsets and provide strict formatting guardrails. The instructions must mandate the avoidance of unsupported characters, requiring the agent to strictly encapsulate node labels in quotes to prevent parser crashes. Furthermore, it must enforce explicit activation mapping; the LLM must be instructed to use the activate and deactivate keywords rather than the shorthand +/- syntax in sequence diagrams, as explicit commands result in higher parsing success rates and logical consistency. Finally, mandatory layout directions must be enforced for flowcharts (e.g., explicitly declaring flowchart TD or flowchart LR) to prevent rendering anomalies and ensure visual consistency across the archival record.

Modeling Flutter, Dart, and Infrastructure with Mermaid

The specific types of diagrams generated by the LLM must align precisely with the architectural patterns prevalent in the target ecosystem. Flutter, Dart, and associated backend infrastructures have distinct paradigms that map exceptionally well to specific Mermaid diagram types. Instructing the agent on which diagram to use for which scenario is a cornerstone of the visual SDD implementation.

In a mobile client, user journeys, navigation flows, and deep-link resolutions are inherently sequential. Sequence diagrams (sequenceDiagram) are the optimal format for modeling GoRouter navigation events. When instructing the LLM to map a GoRouter flow, the agent can represent the human user as an actor, the UI layer and individual screens as a participant, and the router itself as a distinct control entity. The diagram visually maps deep-link interception, redirection logic—such as authentication checks or paywall barriers—and the final page rendering.

Furthermore, the concept of timing, which is critical in modern applications, can be effectively modeled within these sequence diagrams. While Mermaid does not have a native, highly specific "timing diagram" class, timing can be rigorously represented via sequence activation bars that visualize thread memory occupation, combined with descriptive time-blocks or Note directives. Dart's inherent asynchronous nature—specifically the use of Isolates for heavy, non-blocking computation—can be accurately modeled using Mermaid's asynchronous message syntax (-) or --)). The LLM can map the main thread spawning an Isolate, waiting for a prolonged computation, and receiving the asynchronous message payload, providing developers with a clear view of potential race conditions.

State management frameworks like Riverpod and BLoC dictate the reactive nature of Flutter applications. These architectures, particularly when utilizing exhaustive pattern matching, are essentially finite state machines. Therefore, the LLM should be instructed to generate state diagrams (stateDiagram-v2) to visualize the transitions of an AsyncValue in Riverpod or state emissions in BLoC. A generated state diagram can map the initial Loading state, the transition to Data upon a successful repository fetch, and the various fallback paths to an Error state, capturing retry mechanisms and alternate paths. By enforcing this visual generation before code implementation, the developer and the AI align on all possible UI permutations, effectively eliminating unhandled edge cases before they are codified.

For developers managing backend infrastructure or full-stack Dart applications utilizing frameworks like Dart Frog, system topologies and database schemas must be meticulously documented. Mermaid flowcharts (flowchart TD) can render robust system architectures, displaying how mobile clients interface with edge gateways, load balancers, microservices, and databases. Entity-Relationship (ER) diagrams (erDiagram) generated by the LLM can document database schemas, capturing primary keys, foreign keys, and complex relationship cardinalities prior to the LLM writing SQL migrations or Object-Relational Mapping (ORM) models.

Rendering, Validation, and CI/CD Integration

LLM-generated text, regardless of the prompt engineering applied, requires strict automated validation to ensure syntactic correctness. A broken Mermaid diagram embedded in an OpenSpec archive degrades the quality of the documentation and undermines the trust in the SDD process. Therefore, a robust Continuous Integration (CI) pipeline must be established to parse, validate, and definitively render the diagrams into visual assets.

Historically, the standard tool for converting Mermaid markdown into static SVG or PNG images was mermaid-cli (frequently executed as mmdc). However, this tool relies on an embedded instance of Node.js and a headless Chromium browser (Puppeteer) to calculate text dimensions via browser APIs. This architecture introduces severe performance bottlenecks. Spinning up a headless browser incurs a massive cold start penalty of approximately 2,000 to 3,000 milliseconds per diagram. In a repository utilizing OpenSpec, where dozens or hundreds of diagrams might exist across historical archives and current specifications, running mermaid-cli in a GitHub Actions pipeline can escalate build times from seconds to tens of minutes, crippling deployment velocity.

To solve this critical infrastructure problem, engineering teams must transition to native Rust-based renderers, specifically tools like mmdr. Rust-based parsers completely eliminate the heavy browser dependency, parsing the Mermaid syntax natively and rendering directly to SVG format.

Table 3: Rendering Performance Benchmark in CI Environments

Performance Metric	mermaid-cli (Node/Puppeteer)	mmdr (Native Rust)	Net Performance Delta
Cold Start Overhead	~2,500 ms	~3 ms	800x - 1000x Faster
Memory Footprint	~300+ MB	~15 MB	95% Reduction in RAM
System Dependencies	Node.js, npm, Chromium	None (Standalone Binary)	High Portability
CI Build Time (50 Diagrams)	~2.5 Minutes	< 1 Second	Instantaneous Execution

Data synthesized from comparative benchmarking of native Rust rendering versus browser-based Puppeteer rendering.

By integrating mmdr into the CI/CD pipeline, the system can instantaneously iterate through every markdown file in the openspec/specs/ and openspec/changes/ directories, validating syntax and generating static visual assets without throttling developer velocity.

In addition to rendering, the pipeline should implement automated syntax linting as a strict quality gate. Tools such as @a24z/mermaid-parser or mermaid-sonar can be integrated into GitHub Actions to execute rapid syntax checking and complexity analysis on every pull request. If the LLM generates an invalid "After" diagram during the OpenSpec workflow, the CI pipeline will block the merge, prompting the developer to instruct the agent to correct the syntax before the change is permitted to enter the immutable archive.

Implementation Guide and Presentation Narrative

Introducing a visually augmented, LLM-assisted OpenSpec workflow to a large engineering organization requires more than just technical integration; it requires a structured change management strategy and a compelling narrative to drive adoption among developers accustomed to rapid, unstructured coding.

Structuring the Presentation for a Large Dev Group

When delivering a presentation to a large development group, the narrative arc must directly address developer pain points before introducing the structured solution. The presentation should be organized into three distinct phases:

The Hook: The Hidden Cost of Vibe Coding
Begin by highlighting the relatable frustrations of ad-hoc LLM interactions. Demonstrate the phenomenon of "intent drift," where the AI forgets initial architectural constraints by the 20th prompt due to context window saturation. Emphasize the historical reality that manual architecture diagrams are essentially obsolete within hours of being drawn, leading to an environment where documentation is inherently untrustworthy. Frame the problem not as a lack of effort, but as a failure of tooling.

The Mechanism: OpenSpec Delta Tracking and Visual SDD
Introduce OpenSpec not merely as a prompt generator, but as a rigorous state machine for architectural intent. Explain the power of delta tracking—the ability to manage only what is explicitly ADDED, MODIFIED, or REMOVED against a verified source of truth, rather than generating massive, disposable documents. Unveil the custom schema that forces the LLM to generate Mermaid diagrams before writing code, anchoring the AI to a visual representation of the system.

The Live Demonstration: The Visual Upgrade
Execute a live, end-to-end demonstration to prove the system's efficacy.
First, run the /opsx:new command to initialize an isolated change directory for a realistic scenario, such as adding a new authentication flow.
Second, run the custom /opsx:continue command to generate the proposal.md and the diagrams.md.
Third, display the instantly rendered Mermaid output in the IDE, highlighting the stark contrast between the "Before" state of the existing GoRouter logic and the "After" state incorporating the new authentication interceptor.
Conclude the demonstration by running /opsx:archive to show how the "After" diagram seamlessly merges into the living specification, while the entire proposal and rationalization are permanently recorded in the system's historical archive.

The Phased Implementation Rollout Plan

Actual implementation across a large team should not be a synchronized global switch, which invites friction and rejection. A phased rollout minimizes disruption and builds institutional confidence.

Phase 1: Infrastructure and Tooling (Weeks 1-2)
Integrate the custom OpenSpec openspec.config.yaml and the new visual schema definitions into the central repository. Implement the baseline AGENTS.md and establish the progressive disclosure hierarchy by creating the docs/MERMAID_RULES.md files. Concurrently, DevOps must establish the CI/CD pipeline using the Rust-based mmdr renderer and linting tools to ensure the infrastructure is ready to process automated diagrams.

Phase 2: Brownfield Baseline Generation (Weeks 3-4)
Before developers can write "Before and After" deltas, a baseline source of truth must exist. Task the LLM agents to autonomously crawl the existing Flutter and Dart codebase to generate the initial set of comprehensive "Before" diagrams and specifications, depositing them into the canonical openspec/specs/ directories. This establishes the foundation for all future delta tracking.

Phase 3: Pilot Team Adoption (Weeks 5-6)
Select a specific, high-velocity domain team (for example, the team handling payment infrastructure or core navigation) to utilize the /opsx commands exclusively for their upcoming sprint. During this phase, gather meticulous telemetry on token consumption, diagram accuracy, LLM parsing failures, and overall iteration speed. Refine the MERMAID_RULES.md based on the specific hallucination patterns observed during the pilot.

Phase 4: Full Organizational Enforcement (Week 7+)
Expand the workflow to the entire development group. Enforce the OpenSpec lifecycle via strict branch protection rules. Pull requests that bypass the opsx:archive command, fail to include a delta spec, or contain invalid Mermaid syntax in the diagrams.md artifact are automatically rejected by the CI pipeline, ensuring absolute compliance with the visual SDD methodology.

Advantages, Disadvantages, and Strategic Mitigations

Integrating LLM-generated visual artifacts into a strict SDD framework yields profound engineering benefits, though it is accompanied by inherent technical trade-offs that must be actively managed.

Distinct Advantages

The most immediate and impactful advantage is the total eradication of diagram drift. By irrevocably tying the visual representation directly to the implementation lifecycle through OpenSpec’s delta syncing, documentation remains permanently synchronized with the active codebase. This creates a high-trust environment for engineering teams.

Furthermore, visual SDD provides unparalleled cognitive offloading. Complex system logic, such as multi-layered BLoC patterns, nested GoRouter configurations, or concurrent Dart Isolates, is significantly easier for human reviewers to parse visually than through hundreds of lines of verbose text descriptions or raw code review.

The framework also transforms the archive/ directory into a highly traceable visual ledger of architectural evolution. When new engineers onboard onto the project, they can traverse a chronological history of how and why state management or routing paradigms shifted over time, complete with exact visualizations of the transitions at the moment they occurred.

Crucially, from an AI performance standpoint, forcing the LLM to generate the visual graph prior to writing code acts as a powerful logical constraint. The StructGen framework studies prove that when an LLM uses diagrams as structural guidance, its understanding of requirements deepens, increasing the determinism and accuracy of the resulting code by up to 37.3%. If the LLM cannot coherently map the state transitions in a Mermaid diagram, the human developer is immediately alerted that the subsequent code generation will likely be flawed, catching errors at the conceptual stage.

Disadvantages and Limitations

Despite the advantages, the system faces limitations regarding token overhead and context window saturation. Mermaid diagrams, while highly efficient compared to raw code, consume valuable tokens. In an environment where the agent must read the baseline diagram, generate a proposed diagram, and then write expansive delta text specifications, the token budget can become severely constrained. This leads to higher API costs and potential context eviction, where the agent "forgets" earlier instructions. The progressive disclosure strategy in AGENTS.md is the primary mitigation for this, but it requires constant curation.

Additionally, LLMs exhibit documented spatial reasoning deficits. As highlighted by the MermaidSeqBench evaluations, generating highly intricate, interconnected flowcharts with dozens of nodes may result in overlapping paths, illogical connections, or syntax errors that require manual human intervention to correct.

Finally, the framework introduces workflow friction. OpenSpec is a highly structured, unyielding system. It requires discipline. If a developer operating under time pressure reverts to unstructured "vibe coding" and bypasses the /opsx pipeline to implement a quick hotfix, the entire source-of-truth chain is broken, rendering the diagrams and specifications instantly obsolete. Strict CI enforcement is required to prevent this behavioral regression.

Future Trajectories and Further Uses

The fusion of Spec-Driven Development and automated visual generation establishes a foundation for highly advanced AI engineering applications. As Vision-Language Models (VLMs) become standard integration points, the validation loop can become entirely closed-circuit. An agent could theoretically observe a running Flutter application's UI transitions in a simulator, visually compare the runtime execution against the LLM-generated Mermaid state diagram stored in the OpenSpec archive, and automatically flag deviations between the design contract and the actual behavior.

Furthermore, as multi-agent orchestration platforms mature, distinct, specialized agents can be deployed within the OpenSpec DAG. A specialized "Architecture Agent" could focus entirely on crafting optimal Mermaid diagrams and negotiating the design document with the human developer. Once approved, it would hand off the validated visual graph to a separate "Coder Agent," which is restricted exclusively to writing Dart code based on the established visual constraints.

By mastering the integration of OpenSpec, Mermaid, and precise agent governance, organizations can transform their documentation from a lagging, disposable chore into an active, enforceable, and visually intuitive blueprint for continuous software evolution.




Sources used in the report
  OpenSpec vs GitHub Spec Kit: Same Problem, Different Philosophies

  OpenSpec Explained: Repo-Native Spec-Driven Development - CodeMySpec

  OpenSpec | Spec-Driven Development

  OpenSpec - Spec-Driven Development for AI Coding Assistants | Lightweight SDD Framework

  Standardize project context with AGENTS.md and Agent Skills - Red Hat Developer

  AGENTS.md — a simple, open format for guiding coding agents - GitHub

  AGENTS.md

  A Complete Guide To AGENTS.md - AI Hero

  AGENTS.md Spec (2026): Recommended Sections + AGENTS.md vs CLAUDE.md vs .cursorrules - Morph

  Customising OpenSpec workflow with schemas and config.yaml : r/SpecDrivenDevelopment

  OpenSpec/docs/customization.md at main - GitHub

  openspec-schema | Skills Marketplace - LobeHub

  openspec | Skills Marketplace - LobeHub

  openspec — AI agent skill - explainx.ai

  The Artifacts and Their Grammar | Trustable AI Interactions Engineering - Netspective Unified Process for Deterministic Software

  @a24z/mermaid-parser - npm

  Mermaid-Sonar - Diagram Complexity Analyzer - Entropic Drift

  CodeAtlas-Live - Visual Studio Marketplace

  tinh2/skills-hub-registry - GitHub

  Sequence diagrams - Mermaid AI

  Mermaid.js Sequence Diagram Syntax Guide - VPasCode

  Examples - Mermaid AI

  What syntax can I use to diagram as code with Mermaid? - Lucid Community

  Mermaid diagrams | Writerside Documentation - JetBrains

  Descriptive "time blocks" in sequence diagrams · Issue #4549 - GitHub

  MermaidSeqBench: An Evaluation Benchmark for LLM-to-Mermaid Sequence Diagram Generation - ResearchGate

  [Literature Review] MermaidSeqBench: An Evaluation Benchmark for LLM-to-Mermaid Sequence Diagram Generation - Moonlight

  MermaidSeqBench: An Evaluation Benchmark for NL-to-Mermaid Sequence Diagram Generation - arXiv

  Structure-guided function-level code generation with LLMs via UML activity diagrams - DOI

  History of Mermaid.js: Diagrams as Code to 85K Stars (2026) | Taskade Blog

  alexeygrigorev/merm: Pure Python Mermaid diagram renderer - GitHub

  GitHub - 1jehuang/mermaid-rs-renderer: A fast native Rust Mermaid diagram renderer. No browser required. 500-1000x faster than mermaid-cli.

  Mermaid Graph Renderer | Some Claude Skills | AI Know-How Used at Curiositech

  Top 10 Best Software Architecture Diagram Software of 2026

  Generate UML Diagrams from Source Code: Best Practices 2026 - DocuWriter.ai

  Blog - ArchitectureDiagram.ai

  nurgasemetey/github-stars

  nidana-bus-ref-arch-v0_11.md - GitHub

  sdegenaar/zenify: Complete state management for Flutter—hierarchical dependency injection, intelligent async caching, and offline-first resilience. Zero boilerplate, automatic cleanup - GitHub

  rpamis/comet: Comet: agent skill harness for turning ideas into evaluated workflows - GitHub

  Dark software factories: an evidence-led report on their abstraction layer, operation, guardrails, evidence, and limits (evidence through 14 August 2026) - GitHub Gist

  My wife kept nagging me so I built a harness to code for me instead. Won a hackathon with it. : r/ClaudeAI - Reddit

  Stop Vibe Coding. Start Building with OpenSpec. | by Abhinav Dobhal - Medium

  6 Best Spec-Driven Development Tools for AI Coding in 2026

  Sentry Skills | Agent Skills Library - Awesome MCP Servers

  Sequence diagrams - mermaid - UNPKG




Sources read but not used
  OpenSpec/docs/concepts.md at main - GitHub

  GitHub - Fission-AI/OpenSpec: Spec-driven development (SDD) for AI coding assistants.

  OpenSpec/docs/getting-started.md at main - GitHub

  Spec-Driven Development: GitHub Spec Kit & OpenSpec Explained - YouTube

  Spec-Driven Development in Practice: GitHub Spec Kit, OpenSpec, and GSD Compared

  openspec-proposal-creation — AI agent skill - explainx.ai

  How to write a good spec for AI agents - Addy Osmani

  Agents.md Guide for OpenAI Codex - Enhance AI Coding

  [Proposal]: Configurable specs path (`specsPath` in config.yaml) · Issue #664 · Fission-AI/OpenSpec - GitHub

  openspec/config.yaml · v0.14.12 · Andrej Rode / Tinymist · GitLab

  OpenSpec - Research

  agentic-awesome-skills/CATALOG.md at main - GitHub

  Skills Registry — Discover trusted skills for every AI agent - Truefoundry

  GitHub - irahardianto/awesome-agv: Comprehensive sets of standards and practices designed to elevate the capabilities of AI coding agents.

  All skills · AI Skill Safety Scoreboard

  Skill - Tags - prompts.chat

  ChatGPT - Title

  Topics - pub.dev

  Troubleshooting Common Development Errors | PDF | Microsoft Sql Server - Scribd

  AI + MCP - Structurizr

  Structurizr

  Why “as code”? - Structurizr

  C4 Model Architecture Explained: Practical Guide with Structurizr - Devōt

  MermaidSeqBench: An Evaluation Benchmark for NL-to-Mermaid Sequence Diagram Generation - arXiv

  MermaidSeqBench: An Evaluation Benchmark for NL-to-Mermaid Sequence Diagram Generation - arXiv

  StructEval: Benchmarking LLMs' Capabilities to Generate Structural Outputs | OpenReview

  Fine-Tuning Language Models for Enhanced Diagram Generation: A Deep Learning Approach - IJRASET

  Error Bars for Evals: Why Most Benchmark Differences Are Noise

  mmdr: A native Rust Mermaid renderer (500-1000x faster than mermaid-cli) - Reddit

  Tools and Skills for .NET 10: Get the career you want with good practices and patterns to design, debug, and test your solutions 2

  Artificial intelligence - Lib.rs

  How I built a YouTube slide renderer in Python — eight kinds, no

  awesome-stars/README.md at master - GitHub

  The-Useful-Code-Catalogue/README.md at master - GitHub

  learn-ai-native-dev/docs/harness.md at main · microsoft/learn-ai

  Configuration de Structurizr + MCP S... · LobeHub

  awesome-stars/README.md at main - GitHub

  starred-awesome/README.md at master - GitHub

  medy-gribkov/arcana: Universal AI development toolkit. 74 production-ready skills for every coding agent. Works with Claude Code, Cursor, Codex. - GitHub

  Каталог ИТ-специалистов | Подбор разработчиков и IT-специалистов - SkillStaff

  I Tested Three Spec-Driven AI Tools. Here's My Honest Take. - Ran the Builder

  Spec-Driven Development: Why Code is No Longer the Bottleneck




Thoughts
