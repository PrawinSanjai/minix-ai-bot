def get_llm_output_schema(module: str):
    schema = None
    if not module:
        return schema