def get_llm_input_prompt(module: str):
    prompt = None
    if not module:
        return prompt
    
    module = module.lower()

    if module == "":
        prompt = ""
    return prompt