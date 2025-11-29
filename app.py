# app.py
import asyncio
import json
from typing import Optional
from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel
import httpx
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

# Replace with your secret (or load from env)
EXPECTED_SECRET = "change_me_to_your_secret"

app = FastAPI(title="TDS LLM Analysis - Project2 Endpoint")

class QuizRequest(BaseModel):
    email: str
    secret: str
    url: str

@app.post("/project2")
async def project2(req: Request):
    # Validate JSON and shape
    try:
        payload = await req.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    try:
        q = QuizRequest(**payload)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid payload: {e}")

    if q.secret != EXPECTED_SECRET:
        raise HTTPException(status_code=403, detail="Invalid secret")

    # Immediately acknowledge with 200 (you can include a status message)
    # Note: we still must process the task (solve quiz) within 3 minutes.
    # Process in background but we must still finish work now: we'll run it inline.
    result = await solve_quiz_and_submit(q.email, q.secret, q.url)
    return {"status": "ok", "result": result}

async def solve_quiz_and_submit(email: str, secret: str, url: str) -> dict:
    """
    Open the quiz URL in a headless browser (Playwright), parse the task,
    compute the answer, and POST to the submit URL as instructed by the quiz page.
    You must implement the page-specific parsing logic (example below).
    """
    timeout_seconds = 170  # safety: must finish under 180s (3 minutes)
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(args=["--no-sandbox"], headless=True)
            context = await browser.new_context()
            page = await context.new_page()
            await page.goto(url, wait_until="networkidle", timeout=60_000)  # 60s for initial load

            # Example: many quiz pages put the payload in pre or specific element
            # Modify the selectors / parsing for the actual quizzes you get
            # Try common patterns: innerText of #result, <pre>, body text, instructions, or base64 strings

            # Wait for a specific element or a short pause to allow JS to render
            await asyncio.sleep(1)  # small pause (adjust as needed)

            # Example fetch of any <pre> that contains a JSON payload
            content = await page.locator("pre").all_inner_texts()
            text = "\n".join(content) if content else await page.content()

            # TODO: Parse `text` to extract task details: what to compute, and the submit URL.
            # The quiz pages will vary. Below is a naive example for pages that embed JSON inside <pre>.
            parsed = None
            submit_url = None
            answer_payload = None

            try:
                # attempt to find JSON block inside page text
                import re
                json_texts = re.findall(r"\{[\s\S]*\}", text)
                for jt in json_texts:
                    try:
                        parsed = json.loads(jt)
                        break
                    except Exception:
                        continue
            except Exception:
                parsed = None

            # Sample logic for the sample problem in spec (you must adapt)
            # If parsed contains {"url": "...", "secret":"...", "answer": ...} or instruction, do the work.
            if parsed:
                # Example: the quiz asks to download a file at parsed["url"], compute sum of a column
                # Implement your data-fetching and computation logic here:
                # e.g., fetch parsed["url"], read PDF/table, compute answer
                # After computing the correct `answer_value`, prepare the payload below.
                pass

            # Fallback: try to find a submit URL in page (commonly inside forms or anchor)
            # This is a best-effort extraction. Update selector heuristics per actual quizzes.
            # Look for forms:
            form_action = await page.locator("form").get_attribute("action") if await page.locator("form").count() else None
            if form_action:
                submit_url = form_action
            else:
                # Look for obvious text that has "submit" or example.com/submit
                import re
                matches = re.findall(r"https?://[^\s'\"<>]+/submit[^\s'\"<>]*", text)
                if matches:
                    submit_url = matches[0]

            if not submit_url:
                # If the page instructs a specific endpoint via text, you'll need to parse it.
                # If not found, return an informative failure response.
                await browser.close()
                return {"ok": False, "reason": "submit_url_not_found", "page_snapshot": text[:2000]}

            # For demo/testing, let's create a dummy answer (replace with real computed result)
            answer_payload = {
                "email": email,
                "secret": secret,
                "url": url,
                "answer": "REPLACE_WITH_COMPUTED_ANSWER"
            }

            # Post the answer to the submit_url provided on the quiz page
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(submit_url, json=answer_payload)
                try:
                    resp_json = resp.json()
                except Exception:
                    resp_json = {"status_code": resp.status_code, "text": resp.text[:2000]}
            await browser.close()
            return {"ok": True, "submit_response": resp_json}
    except PlaywrightTimeoutError as e:
        return {"ok": False, "reason": "playwright_timeout", "detail": str(e)}
    except Exception as e:
        return {"ok": False, "reason": "exception", "detail": str(e)}
