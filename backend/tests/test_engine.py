"""The guardrail engine screens two kinds of text: user prompts and retrieved documents."""

from app.guardrail import engine, llm_judge


async def test_documents_may_mention_passwords_but_prompts_asking_for_them_may_not():
    text = "Never share your password with anyone, including the IT team."
    as_prompt = await engine.classify(text, source="prompt")
    as_document = await engine.classify(text, source="document")
    assert as_prompt["verdict"] == "UNSAFE"
    assert as_document["verdict"] == "SAFE"      # only a signal for the judge


async def test_documents_are_judged_with_the_document_rubric(fake_llm):
    await llm_judge.judge("Some page text.", source="document")
    assert fake_llm[-1][0] == llm_judge._SYSTEM["document"]
