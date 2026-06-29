# Title: F1 Rule & Penalty Interpreter (PM1 Proposal)

## Team members: Hrishi Kabra & Ayush Bhatia

### Problem statement & user:
Formula 1 penalties and steward decisions are often difficult for fans to understand. This is supposed to help fans understand the FIA regulations and why a penalty was given.
Target users would be Formula 1 fans.

### What problem are you solving, and for whom?
Helping F1 fans understand the complex FIA regulations and reasons as to why penalties are given during a race.

### Why AI / LLM?
Need to interpret FIA regulations which are long, cross-referenced, and not user-friendly to go through. AI can translate these complex regulations into plain English for fans and people interested in the sport.

### Why is an LLM-based system appropriate here?
LLMs are effective at summarizing and explaining complex legal documents. Paired with RAG, they can generate explanations grounded in the documents and reduce hallucination.

### Example interactions:
- User: "Why was this incident given a 5-second penalty instead of a drive-through?" → Explains the relevant FIA regulation section and the criteria for time penalties, with a citation.
- User: "Why was this incident penalized, but a similar one last race was not?" → Compares the steward decisions and references relevant regulations.
- User: "What penalties usually apply for unsafe pit release?" → Summarizes the regulation on unsafe releases and lists typical penalties with citations.

### Possible data sources:
FIA Formula One Sporting Regulations, FIA Steward Decision Documents, public race penalty summaries.
- https://www.fia.com/regulation/category/110
- https://www.fia.com/documents/championships/fia-formula-one-world-championship-14/season/season-2025-2071

### Initial risks / concerns:
- Hallucination of rule numbers or penalties
- Speculation about driver intent or steward reasoning
- Incomplete coverage — won't answer when documents aren't present

---

*The v1 Colab/Gradio prototype lives in `AI_Engineering_Project.ipynb`. The v2 deployed,
evaluated, agentic system is documented in the top-level `README.md`.*
