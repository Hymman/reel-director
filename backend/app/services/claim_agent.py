import json
from typing import List, Optional
from pydantic import BaseModel, Field
from app.config import settings

class ClaimFlag(BaseModel):
    claim: str
    reason: str
    safer_wording_suggestion: str

class ClaimVerificationResult(BaseModel):
    unsupported_claims_found: bool = False
    flags: List[ClaimFlag] = Field(default_factory=list)

class ClaimVerificationAgent:
    def __init__(self):
        self.instruction = """
You are an expert brand safety and claims verification auditor.
Your job is to read a campaign brief and the extracted research evidence, and identify if the brief contains any unsupported outcome claims, superiority claims, factual claims, sensitive claims, or invented product capabilities.
If you find unsupported claims:
- Flag the claim.
- Explain briefly why support is insufficient based on the evidence provided (or lack thereof).
- Suggest safer, evidence-grounded wording.

Return a strict JSON object matching this schema exactly:
{
  "unsupported_claims_found": boolean,
  "flags": [
    {
      "claim": "The unsupported claim from the brief",
      "reason": "Why it is unsupported by evidence",
      "safer_wording_suggestion": "A better alternative"
    }
  ]
}
If no unsupported claims are found, return:
{
  "unsupported_claims_found": false,
  "flags": []
}
"""

    async def verify_claims(self, brief_text: str, evidence: list) -> dict:
        evidence_text = "\n".join([f"- [{getattr(e, 'evidence_id', 'E')}] {getattr(e, 'claim', '')} (Excerpt: {getattr(e, 'excerpt', '')})" for e in evidence])
        
        prompt = f"""{self.instruction}

Please verify the following campaign brief against the provided evidence.

CAMPAIGN BRIEF TEXT:
{brief_text}

EVIDENCE:
{evidence_text}
"""
        try:
            from app.services.gemini_service import gemini_service
            if not gemini_service.client:
                return {"unsupported_claims_found": False, "flags": []}
            
            from google.genai import types
            response = await gemini_service.client.aio.models.generate_content(
                model=gemini_service.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=ClaimVerificationResult
                )
            )
            if response.text:
                return json.loads(response.text)
            return {"unsupported_claims_found": False, "flags": []}
        except Exception as e:
            print(f"Failed to parse Claim Verification agent response: {e}")
            return {"unsupported_claims_found": False, "flags": []}

claim_agent = ClaimVerificationAgent()

