import ast
import argparse
from os import name
from pathlib import Path
from fastapi import FastAPI
from importlib import import_module
from langchain.prompts import PromptTemplate
# from langchain_community.llms import Ollama
from langchain.output_parsers import StructuredOutputParser, ResponseSchema
from langchain_core.runnables import RunnableSequence
from langchain_ollama import OllamaLLM
# Configuration
OLLAMA_MODEL = "mistral"
TEST_OUTPUT_DIR = "tests"
TEST_FILE_NAME = "test_endpoints.py"

def get_fastapi_app(app_path:str, app_name:str) -> FastAPI:
    """Import the FastAPI app from the specified module"""
    try:
        module= import_module(app_path.replace("/",".").replace("\\",".").rstrip(".py"))
        app = getattr(module,app_name, None)
        if not isinstance(app,FastAPI):
            raise ValueError(f"{app_name} is not FastAPI instance")
        return app
    except Exception as e:
        raise Exception(f"Failed to load FastAPI instance")

def get_endpoint_details(app: FastAPI):
    """Extract the endpoint details from the FastAPI app"""
    endpoints =[]
    for route in app.routes:
        if hasattr(route, "methods") and hasattr(route, "path") :
            endpoints.append({
                "path": route.path,
                "method": route.methods,
                "name":route.name,
                "response_model": str(getattr(route,"response_model",None)),
                "body_field": str(getattr(route, "body_field", None))
            })
    return endpoints

def create_prompt_template():
    """ Create a Langachain prompt template for test case generation"""    
    response_schemas = [
        ResponseSchema(name="test_code", description="Generated pytest test case code ", type="string")
    ]    
    output_parser = StructuredOutputParser.from_response_schemas(response_schemas)
    format_instructions = output_parser.get_format_instructions()
    prompt_template = PromptTemplate(
        input_variables=["path","method","name","response_model","body_field"],
        template="""
        Generate a pytest unit test case for a FastAPI endpoint with the following details:
        - Path: {path}
        - Method: {method}
        - Name: {name}
        - Response Model: {response_model}
        - Request Body (optional if present): {body_field}

        The test should: 
        - Use `pytest` and `httpx.AsyncClient` for async HTTP requests
        - Include `@pytest.mark.asyncio` for async tests.
        - tests for: 
            - Successful response (Status code 200 for ok and 201 for created field or other appropriate responses)
            - Invalid Input(e.g, Status code 422 for invalid data)
            - Edge Cases (e.g mising parameteres or invalid types).
        - Use the `TestClient` from `fastapi.testclient`
        - Be properly formatted and concise
        - The code should look like it is written by a principal software engineer with 20 years of experience

        Return the response in the follwing format:
        {{output_parser.get_format_instructions()}}  

        Example test case:
        ```python 
        @pytest.mark.asyncio
        async def test_endpoint_name(client: TestClient):
            async with httpx.AsyncClient(app=client.app, base_url="http://test") as async_client:
            response = await async_client.get("/path")
            assert response.status_code == 200
            assert response.json() == {{expected_response}}
        ```  
        """,
        partial_variables={"output_parser.get_format_instructions()": format_instructions}
    )
    return prompt_template, output_parser

def generated_test_case(endpoint: dict, llm,prompt_template :PromptTemplate,output_parser:StructuredOutputParser ):
    """Generate testcase using Langchain and Local LLM"""
    chain = RunnableSequence(prompt_template | llm | output_parser)
    try:
        result = chain.invoke({
            "path":endpoint["path"],
            "method":",".join(endpoint["method"]),
            "name": endpoint["name"],
            "response_model": endpoint["response_model"],
            "body_field": endpoint["body_field"]
        })
        return result.get("test_code",f"# Error: No test code generated for {endpoint['path']}")
    except Exception as e:
        return f"# Error generating test case for {endpoint['path']}: {str(e)}"


def generate_test(app_path: str,app_name:str,out_dir: str= TEST_OUTPUT_DIR):
    """Generate UTs for endpoints in the fastAPI"""
    llm = OllamaLLM(model="mistral")
    prompt_template, out_parser = create_prompt_template()
    Path(out_dir).mkdir(exist_ok=True)
    output_file = Path(out_dir) / TEST_FILE_NAME
    app = get_fastapi_app(app_path,app_name)
    endpoints = get_endpoint_details(app)
    with open(output_file, "w") as f:
        f.write("from fastapi.testclient import TestClient\n")
        f.write("import pytest\n")
        f.write("import httpx\n\n")
        f.write(f"from {app_path.replace('/', '.').rstrip('.py')} import {app_name}\n\n")
        f.write("client = TestClient(app)\n\n")

        for endpoint in endpoints:
            test_code = generated_test_case(endpoint, llm, prompt_template, out_parser)
            f.write(test_code + "\n\n")

        print(f"Tests written to {output_file}")

def main():
    """Main function to run the agent."""
    parser = argparse.ArgumentParser(description="Generate unit tests for FastAPI endpoints using LangChain")
    parser.add_argument("--app-path", default="main", help="Path to FastAPI app module (e.g., 'app/main')")
    parser.add_argument("--app-name", default="app", help="Name of the FastAPI app instance")
    parser.add_argument("--output-dir", default=TEST_OUTPUT_DIR, help="Output directory for test files")
    args = parser.parse_args()

    generate_test(args.app_path, args.app_name, args.output_dir)


if __name__ == "__main__":
    main()      
