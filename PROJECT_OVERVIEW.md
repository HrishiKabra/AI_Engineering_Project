# Title: F1 Rule & Penalty Interpreter

## Team members: Hrishi Kabra & Ayush Bhatia

### Problem statement & user: 
    Formula 1 penalties and steward decisions are often difficult for fans to understand. This is supposed to help fans understand the FIA regulations and why a penalty was given. 
    Target users would be Formula 1 fans

### What problem are you solving, and for whom?
    Helping F1 fans understand the complex FIA regulations and reasons as to why penalties are given during a race

### Why AI / LLM?
    Need to interpret FIA regulations which are long, cross-references, and not user-friendly to go through.
    AI can translate these complex regulations into plain-english for fans, and people who are just interested in the sport to understand. 

### Why is an LLM-based system appropriate here?
    LLMs are effective when it comes to summarizing and explaining these complex legal documents. They can help interpret these. 
    When paired with RAG as well, they can generate explanations from the document and reduce hallucination

### Example interactions:
    User: “Why was this incident given a 5-second penalty instead of a drive-through?”
    Response: Explains the relevant FIA regulation section and outlines criteria for time penalties and cites the relevant rule.

    User: “Why was this incident penalized, but a similar one last race was not?”
    Response: would compare the steward decisions, show differences such as lasting advantage, and would reference relevant regulations.

    User: “What penalties usually apply for unsafe pit release?”
    Response: Summarizes the regulation relating to unsafe releases and lists typical penalties with citations.

### Possible data sources:
    FIA Formula One Sporting Regulations, FIA Steward Decision Documents, Public Race Penalty Summaries and Incident Reports

    https://www.fia.com/regulation/category/110
    https://www.fia.com/documents/championships/fia-formula-one-world-championship-14/season/season-2025-2071

### Initial risks / concerns:
    Hallucination of rule numbers or penalties
    Speculations about drivers intent or steward reasoning
    Incomplete coverage - wont answer when some documents aren’t there

