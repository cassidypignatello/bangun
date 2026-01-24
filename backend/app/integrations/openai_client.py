"""
OpenAI GPT-4o-mini client with prompt caching for BOM generation
"""

import json
from functools import lru_cache

from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import get_settings
from app.utils.resilience import with_circuit_breaker

# System prompt as constant for OpenAI prompt caching
# This will be cached by OpenAI when sent consistently
SYSTEM_PROMPT = """You are an expert construction cost estimator specializing in Bali, Indonesia.

Your task is to generate a detailed Bill of Materials (BOM) for construction and renovation projects.

Guidelines:
1. Break down projects into specific materials with realistic quantities
2. Use standard Indonesian construction units (m2, pcs, kg, liter, etc.)
3. Consider Bali-specific climate, regulations, and construction practices
4. Include all necessary materials: structural, finishing, electrical, plumbing
5. Be comprehensive but avoid redundancy

CRITICAL - Material Naming Rules (BILINGUAL OUTPUT REQUIRED):
1. material_name: INDONESIAN product names for Tokopedia marketplace search
   - Use common brand names or generic Indonesian terms (e.g., "Semen Tiga Roda" not "Portland Cement Type I")
   - Keep names SHORT (2-4 words maximum) - avoid long technical descriptions
   - Use Indonesian spelling: "keramik" not "ceramic", "besi" not "iron", "pipa" not "pipe"
   - Include size/spec ONLY if commonly searched (e.g., "Besi Beton 10mm")
   - GOOD: "Semen 50kg", "Keramik 40x40", "Besi Beton 12mm", "Cat Tembok Dulux"
   - BAD: "Campuran Beton 25 MPa", "Membran Waterproofing Bitumen 1mm"

2. english_name: ENGLISH translation for international users
   - Clear, descriptive English name that explains what the material is
   - Include specifications that help users understand the product
   - GOOD: "Cement 50kg Bag", "Ceramic Floor Tiles 40x40cm", "Steel Rebar 12mm", "Wall Paint (Dulux)"

Output Format:
Return a JSON array of materials with this structure:
[
  {
    "material_name": "Keramik 40x40",
    "english_name": "Ceramic Floor Tiles 40x40cm",
    "quantity": 25.0,
    "unit": "m2",
    "category": "finishing",
    "notes": "For bathroom flooring"
  }
]

Categories: structural, finishing, electrical, plumbing, hvac, landscaping, fixtures, miscellaneous
"""


@lru_cache
def get_openai_client() -> AsyncOpenAI:
    """
    Get singleton OpenAI client instance

    Returns:
        AsyncOpenAI: Configured OpenAI client
    """
    settings = get_settings()
    return AsyncOpenAI(api_key=settings.openai_api_key)


@with_circuit_breaker("openai")
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
async def generate_bom(project_input: dict) -> list[dict]:
    """
    Generate Bill of Materials using GPT-4o-mini with prompt caching

    Uses consistent SYSTEM_PROMPT for caching optimization.
    Retries with exponential backoff on failures.

    Args:
        project_input: Project details (type, description, images, location)

    Returns:
        list[dict]: Generated BOM items

    Raises:
        Exception: If generation fails after retries
    """
    client = get_openai_client()

    # Build user prompt from project input (simplified - description is the primary input)
    user_prompt = f"""Generate a Bill of Materials for this Bali construction/renovation project:

{project_input['description']}
"""

    if project_input.get("images"):
        user_prompt += f"\n(Reference images provided: {len(project_input['images'])})"

    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},  # Cached constant
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.7,
            max_tokens=2000,
        )

        content = response.choices[0].message.content
        if not content:
            raise ValueError("Empty response from OpenAI")

        # Parse JSON response
        result = json.loads(content)

        # Handle both direct array and wrapped responses
        if isinstance(result, dict) and "materials" in result:
            return result["materials"]
        elif isinstance(result, list):
            return result
        else:
            raise ValueError(f"Unexpected response format: {type(result)}")

    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON response from OpenAI: {e}")
    except Exception as e:
        raise Exception(f"BOM generation failed: {e}")


async def enhance_material_description(material_name: str, context: str = "") -> str:
    """
    Enhance material name for better marketplace matching

    Args:
        material_name: Original material name
        context: Additional context about the material

    Returns:
        str: Enhanced material description for searching
    """
    client = get_openai_client()

    prompt = f"""Convert this construction material into a Tokopedia search term that Indonesian shoppers actually use.

Material: {material_name}
{f'Context: {context}' if context else ''}

Rules:
- Use Indonesian words (keramik, semen, besi, pipa, cat)
- Maximum 3-4 words
- Include brand if common (Dulux, Tiga Roda, Wavin)
- Include size only if essential (40x40, 12mm, 4 inch)
- Remove technical specs (MPa, PSI, Grade A)
- Remove English words

Examples:
- "Campuran Beton 25 MPa" → "Semen 50kg"
- "Membran Waterproofing Bitumen" → "Waterproofing"
- "Ceramic Tiles 40x40cm Grade A" → "Keramik 40x40"
- "PVC Pipe 4 inch Schedule 40" → "Pipa PVC 4 inch"

Return ONLY the search term, nothing else."""

    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=30,
        )

        enhanced = response.choices[0].message.content
        return enhanced.strip().strip('"').strip("'") if enhanced else material_name

    except Exception:
        # Fallback to simplified name
        return _simplify_material_name(material_name)


def _simplify_material_name(name: str) -> str:
    """
    Simple fallback to extract core material name without API call.

    Removes common technical terms and keeps just the base material.
    """
    # Common technical terms to remove
    remove_terms = [
        "grade a", "grade b", "grade c", "type i", "type ii",
        "mpa", "psi", "mm", "cm", "meter", "kg", "liter",
        "premium", "standard", "heavy duty", "high quality",
        "professional", "industrial", "commercial",
    ]

    # Indonesian translations for common English terms
    translations = {
        "cement": "semen",
        "concrete": "beton",
        "ceramic": "keramik",
        "tile": "keramik",
        "tiles": "keramik",
        "iron": "besi",
        "steel": "baja",
        "pipe": "pipa",
        "paint": "cat",
        "wood": "kayu",
        "sand": "pasir",
        "gravel": "kerikil",
        "brick": "batu bata",
        "glass": "kaca",
        "door": "pintu",
        "window": "jendela",
        "roof": "atap",
        "floor": "lantai",
        "wall": "dinding",
        "waterproofing": "waterproofing",
        "membrane": "membran",
    }

    result = name.lower()

    # Remove technical terms
    for term in remove_terms:
        result = result.replace(term, "")

    # Translate common English words
    for eng, ind in translations.items():
        result = result.replace(eng, ind)

    # Clean up extra spaces and return
    return " ".join(result.split())[:50]  # Max 50 chars
