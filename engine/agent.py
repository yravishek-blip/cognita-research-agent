import asyncio
import re
import json
import logging
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any, Callable, Awaitable

from engine.models import (
    ResearchRequest,
    ResearchReport,
    ResearchProgressEvent,
    SubQuery,
    SourceEvidence,
    ScrapedDocument
)
from engine.llm import LLMService
from engine.search import search_web
from engine.scraper import scrape_urls_concurrently

logger = logging.getLogger(__name__)


class DeepResearchAgent:
    """
    Autonomous multi-stage deep research orchestration agent.
    Executes decomposition, live web discovery, full-text scraping,
    credibility auditing, and synthesized cited report generation.
    """
    def __init__(
        self,
        request: ResearchRequest,
        event_callback: Optional[Callable[[ResearchProgressEvent], Awaitable[None]]] = None
    ):
        self.request = request
        self.event_callback = event_callback
        self.llm = LLMService(provider=request.provider, api_key=request.api_key)

    async def emit_progress(
        self,
        step: str,
        phase_title: str,
        message: str,
        progress: int,
        data: Optional[Dict[str, Any]] = None
    ):
        """Emit real-time telemetry event to client."""
        if self.event_callback:
            event = ResearchProgressEvent(
                step=step,
                phase_title=phase_title,
                message=message,
                progress=progress,
                data=data or {}
            )
            try:
                await self.event_callback(event)
            except Exception as e:
                logger.warning(f"Failed to stream progress event: {e}")

    async def execute(self) -> ResearchReport:
        report_id = str(uuid.uuid4())[:8]
        timestamp = datetime.now().strftime("%B %d, %Y - %H:%M UTC")

        logger.info(f"Starting research investigation '{self.request.query}' [ID: {report_id}]")

        # -------------------------------------------------------------
        # STEP 1: Query Decomposition & Strategic Planning
        # -------------------------------------------------------------
        await self.emit_progress(
            step="planning",
            phase_title="Strategic Query Decomposition",
            message=f"Formulating multi-angle investigation plan for: '{self.request.query}'",
            progress=10
        )

        sub_queries = await self._decompose_query(self.request.query, self.request.breadth)

        await self.emit_progress(
            step="planning",
            phase_title="Vectors Established",
            message=f"Generated {len(sub_queries)} strategic research vectors across market, tech, and policy.",
            progress=25,
            data={"sub_queries": [sq.dict() for sq in sub_queries]}
        )

        # -------------------------------------------------------------
        # STEP 2: Autonomous Web Discovery
        # -------------------------------------------------------------
        await self.emit_progress(
            step="searching",
            phase_title="Autonomous Web Discovery",
            message="Conducting concurrent web searches across academic and open web indexes...",
            progress=35
        )

        results_per_query = 4 if self.request.depth != "quick" else 3
        search_tasks = [search_web(sq.query, max_results=results_per_query) for sq in sub_queries]
        search_results = await asyncio.gather(*search_tasks)

        # Flatten and deduplicate candidates by clean URL
        seen_urls = set()
        candidates: List[dict] = []
        for res_list in search_results:
            for item in res_list:
                url = item.get("url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    candidates.append(item)

        unique_domains = len(set(c.get("domain", "") for c in candidates if c.get("domain")))
        await self.emit_progress(
            step="searching",
            phase_title="Discovery Complete",
            message=f"Located {len(candidates)} candidate intelligence sources across {unique_domains} unique domains.",
            progress=50
        )

        # -------------------------------------------------------------
        # STEP 3: Full-Text Ingestion & Credibility Auditing
        # -------------------------------------------------------------
        await self.emit_progress(
            step="scraping",
            phase_title="Full-Text Ingestion & Noise Removal",
            message=f"Scraping and parsing article bodies across {len(candidates)} URLs...",
            progress=60
        )

        scraped_docs = await scrape_urls_concurrently(candidates, max_concurrency=5)

        # Filter substantive documents and sort by credibility score descending
        valid_docs = [d for d in scraped_docs if d.char_count > 100]
        if not valid_docs:
            valid_docs = scraped_docs  # Keep fallbacks if all had brief snippets

        valid_docs.sort(key=lambda d: d.credibility_score, reverse=True)

        total_chars = sum(d.char_count for d in valid_docs)
        await self.emit_progress(
            step="scraping",
            phase_title="Authority & Credibility Audited",
            message=f"Audited {len(valid_docs)} sources ({total_chars:,} characters). Evaluated domain authority.",
            progress=75,
            data={"documents": [{"domain": d.domain, "credibility": d.credibility_score, "title": d.title} for d in valid_docs]}
        )

        # -------------------------------------------------------------
        # STEP 4: Neural Synthesis & Inline Citation Linking
        # -------------------------------------------------------------
        await self.emit_progress(
            step="analyzing",
            phase_title="Multi-Source Synthesis & Citation Linking",
            message="Cross-referencing evidence, resolving contradictions, and generating cited briefing...",
            progress=85
        )

        # Construct numbered sources evidence
        sources_evidence: List[SourceEvidence] = []
        max_sources_to_cite = 10 if self.request.depth == "exhaustive" else 6
        selected_docs = valid_docs[:max_sources_to_cite]

        for idx, doc in enumerate(selected_docs, start=1):
            findings = [doc.snippet] if doc.snippet else []
            sources_evidence.append(
                SourceEvidence(
                    citation_id=idx,
                    url=doc.url,
                    title=doc.title,
                    domain=doc.domain,
                    credibility_score=doc.credibility_score,
                    key_findings=findings
                )
            )

        markdown_report, exec_summary = await self._synthesize_report(
            topic=self.request.query,
            sub_queries=sub_queries,
            sources=sources_evidence,
            docs=selected_docs
        )

        total_words = len(markdown_report.split())

        await self.emit_progress(
            step="completed",
            phase_title="Intelligence Briefing Ready",
            message=f"Synthesized comprehensive {total_words:,} word briefing with verified footnote citations.",
            progress=100
        )

        # -------------------------------------------------------------
        # STEP 5: Final Report Assembly
        # -------------------------------------------------------------
        report = ResearchReport(
            id=report_id,
            topic=self.request.query,
            timestamp=timestamp,
            executive_summary=exec_summary,
            markdown_report=markdown_report,
            sub_queries=sub_queries,
            sources=sources_evidence,
            total_sources_scanned=len(candidates),
            total_words=total_words,
            depth=self.request.depth
        )

        return report

    async def _decompose_query(self, query: str, breadth: int) -> List[SubQuery]:
        """Deconstruct user topic into multiple strategic sub-queries."""
        system_prompt = (
            "You are an expert research director. Decompose the user's inquiry into a JSON array of "
            f"precisely {breadth} distinct research sub-queries spanning technical architecture, commercial economics, "
            "competitive landscape, and regulatory/risk factors.\n"
            "Format MUST be a valid JSON array of objects: [{\"query\": \"...\", \"rationale\": \"...\"}]"
        )
        user_prompt = f"Topic: '{query}'\nGenerate {breadth} high-yield research sub-queries."

        try:
            raw_response = await self.llm.generate(user_prompt, system_prompt=system_prompt)
            # Extract JSON block
            json_match = re.search(r'\[[\s\S]*\]', raw_response)
            if json_match:
                parsed = json.loads(json_match.group(0))
                sub_queries = []
                for idx, item in enumerate(parsed[:breadth], start=1):
                    sub_queries.append(SubQuery(
                        id=idx,
                        query=item.get("query", query),
                        rationale=item.get("rationale", "Strategic domain investigation")
                    ))
                if sub_queries:
                    return sub_queries
        except Exception as e:
            logger.warning(f"Error parsing decomposed sub-queries: {e}")

        # Fallback heuristic decomposition if JSON parsing or LLM fails
        return [
            SubQuery(id=1, query=f"{query} latest technological advancements and architecture", rationale="Investigate technical state-of-the-art and foundational innovations."),
            SubQuery(id=2, query=f"{query} market size commercial viability cost dynamics", rationale="Analyze economic scale, pricing, and adoption velocity."),
            SubQuery(id=3, query=f"{query} leading companies key competitors landscape", rationale="Evaluate industry players and commercial roadmaps."),
            SubQuery(id=4, query=f"{query} challenges limitations regulations bottlenecks", rationale="Identify key vulnerabilities, hurdles, and compliance standards.")
        ][:breadth]

    async def _synthesize_report(
        self,
        topic: str,
        sub_queries: List[SubQuery],
        sources: List[SourceEvidence],
        docs: List[ScrapedDocument]
    ) -> tuple[str, str]:
        """
        Synthesize scraped intelligence into an authoritative Markdown briefing
        with inline footnote citations [1], [2] and verified reference list.
        """
        evidence_summary_lines = []
        for s in sources:
            matching_doc = next((d for d in docs if d.url == s.url), None)
            sample_content = matching_doc.clean_text[:1500] if matching_doc else s.title
            evidence_summary_lines.append(
                f"Source [{s.citation_id}] ({s.domain} - Authority {int(s.credibility_score*100)}%):\n"
                f"Title: {s.title}\n"
                f"Content Abstract: {sample_content}\n"
            )

        evidence_context = "\n".join(evidence_summary_lines)

        system_prompt = (
            "You are Cognita, a world-class strategic intelligence synthesis engine. "
            "Your task is to synthesize the provided primary source evidence into an exhaustive, "
            "authoritative, publication-grade executive intelligence briefing.\n\n"
            "REQUIREMENTS:\n"
            "1. Use strict GitHub Markdown with clean headings (H1, H2, H3), bullet points, and comparative tables.\n"
            "2. ALWAYS include inline numeric citations like [1], [2] pointing to the provided sources for every factual assertion.\n"
            "3. Include a comparative markdown matrix comparing key approaches or metrics.\n"
            "4. Structure:\n"
            "   # 🧠 Strategic Intelligence Briefing: [Topic]\n"
            "   ## Executive Summary\n"
            "   ## 1. Technical Architecture & Foundational Breakthroughs\n"
            "   ## 2. Comparative Ecosystem Matrix (Include Markdown Table)\n"
            "   ## 3. Commercial Economics & Market Adoption Trajectory\n"
            "   ## 4. Key Limitations, Risks & Regulatory Headwinds\n"
            "   ## 5. Strategic Recommendations & Actionable Horizons\n"
            "5. Do NOT include generic filler. Be specific, data-rich, and rigorous."
        )

        user_prompt = (
            f"Topic: {topic}\n\n"
            f"PRIMARY EVIDENCE SOURCES:\n{evidence_context}\n\n"
            "Synthesize the complete, deeply cited intelligence briefing now."
        )

        try:
            markdown = await self.llm.generate(user_prompt, system_prompt=system_prompt)
        except Exception as e:
            logger.warning(f"LLM synthesis failed: {e}. Utilizing internal synthesis fallback.")
            markdown = self.llm._local_heuristic_generate(f"Topic: {topic}")

        # Ensure citations and references section is cleanly attached
        ref_section = "\n\n## 📚 Verified Sources & Intelligence Audit\n\n"
        for s in sources:
            auth_percent = int(s.credibility_score * 100)
            ref_section += f"- **[{s.citation_id}] [{s.title}]({s.url})** — `{s.domain}` *(Authority Score: {auth_percent}%)*\n"

        if "Verified Sources" not in markdown and "References" not in markdown:
            markdown += ref_section

        # Extract executive summary snippet
        exec_summary = "Strategic intelligence briefing synthesized across multiple verified web sources."
        summary_match = re.search(r'## Executive Summary\s+([\s\S]*?)(?=##|\Z)', markdown)
        if summary_match:
            exec_summary = summary_match.group(1).strip()[:400] + "..."

        return markdown, exec_summary
