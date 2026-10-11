from app.config import Settings
from app.llm.assistant import DEFAULT_SYSTEM_PROMPT, load_system_prompt


def test_prompt_file_is_loaded_and_business_name_filled(tmp_path):
    prompt = tmp_path / "system_prompt.md"
    prompt.write_text("You help {business} customers. JSON looks like {\"a\": 1}.\n", encoding="utf-8")
    settings = Settings(system_prompt_file=str(prompt), business_name="Sharma Sweets")
    assert load_system_prompt(settings) == 'You help Sharma Sweets customers. JSON looks like {"a": 1}.'


def test_missing_prompt_file_falls_back_to_default(tmp_path):
    settings = Settings(system_prompt_file=str(tmp_path / "nope.md"), business_name="Acme")
    assert load_system_prompt(settings) == DEFAULT_SYSTEM_PROMPT.replace("{business}", "Acme")


def test_repo_default_prompt_file_exists():
    assert "{business}" in open("prompts/system_prompt.md", encoding="utf-8").read()
